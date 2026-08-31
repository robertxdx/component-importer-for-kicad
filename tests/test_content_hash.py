import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from component_importer.cad_zip_importer import import_cad_zip
from component_importer.content_hash import (
    canonical_sexpr_hash,
    canonicalize_sexpr,
    hash_footprint_file,
    hash_symbol_in_library,
    verify_component_hashes,
)


# Fixture s-expressions reused from the global-import test fixtures
SYMBOL_LIBRARY = """(kicad_symbol_lib
  (version 20231120)
  (generator "test")
  (symbol "TEST_PART"
    (property "Reference" "U" (at 0 2.54 0) (effects (font (size 1.27 1.27))))
    (property "Value" "TEST_PART" (at 0 0 0) (effects (font (size 1.27 1.27))))
    (symbol "TEST_PART_0_1"
      (rectangle (start -2.54 1.27) (end 2.54 -1.27)
        (stroke (width 0) (type default)) (fill (type background))))
    (symbol "TEST_PART_1_1"
      (pin input line (at -5.08 0 0) (length 2.54)
        (name "IN" (effects (font (size 1.27 1.27))))
        (number "1" (effects (font (size 1.27 1.27)))))))
)"""

FOOTPRINT = """(footprint "TEST_FP"
  (version 20240108)
  (generator "test")
  (model "old.step"
    (offset (xyz 0 0 0))
    (scale (xyz 1 1 1))
    (rotate (xyz 0 0 0)))
)"""


class CanonicalHashInvarianceTest(unittest.TestCase):
    def test_whitespace_and_indentation_invariant(self):
        packed = '(symbol "A" (pin (name "IN")) (property "Value" "X"))'
        spaced = """(symbol
                "A"
            (pin
                (name   "IN"))

            (property "Value"   "X")
        )"""
        self.assertEqual(
            canonical_sexpr_hash(packed),
            canonical_sexpr_hash(spaced),
        )

    def test_sibling_block_reordering_invariant(self):
        original = (
            '(symbol "A"'
            ' (property "Reference" "U")'
            ' (property "Value" "X")'
            ' (pin (name "IN")))'
        )
        reordered = (
            '(symbol "A"'
            ' (pin (name "IN"))'
            ' (property "Value" "X")'
            ' (property "Reference" "U"))'
        )
        self.assertEqual(
            canonical_sexpr_hash(original),
            canonical_sexpr_hash(reordered),
        )

    def test_parameter_reordering_within_block_invariant(self):
        original = "(effects (font (size 1 1)) hide)"
        reordered = "(effects hide (font (size 1 1)))"
        self.assertEqual(
            canonical_sexpr_hash(original),
            canonical_sexpr_hash(reordered),
        )

    def test_numeric_formatting_invariant(self):
        a = "(at 2.54 0 90)"
        b = "(at 2.540 0.0 90.00)"
        self.assertEqual(
            canonical_sexpr_hash(a),
            canonical_sexpr_hash(b),
        )

    def test_zero_variants_invariant(self):
        self.assertEqual(
            canonical_sexpr_hash("(x 0)"),
            canonical_sexpr_hash("(x 0.00)"),
        )
        self.assertEqual(
            canonical_sexpr_hash("(x 0.0)"),
            canonical_sexpr_hash("(x 0)"),
        )


class CanonicalHashSensitivityTest(unittest.TestCase):
    def test_pin_name_change_differs(self):
        original = '(pin input line (name "IN") (number "1"))'
        renamed = '(pin input line (name "OUT") (number "1"))'
        self.assertNotEqual(
            canonical_sexpr_hash(original),
            canonical_sexpr_hash(renamed),
        )

    def test_number_change_differs(self):
        original = "(at 2.54 0 0)"
        changed = "(at 2.55 0 0)"
        self.assertNotEqual(
            canonical_sexpr_hash(original),
            canonical_sexpr_hash(changed),
        )

    def test_adding_block_differs(self):
        original = '(symbol "A" (property "Value" "X"))'
        with_extra = '(symbol "A" (property "Value" "X") (property "Extra" "Y"))'
        self.assertNotEqual(
            canonical_sexpr_hash(original),
            canonical_sexpr_hash(with_extra),
        )

    def test_removing_block_differs(self):
        original = '(symbol "A" (property "Value" "X") (pin (name "IN")))'
        without = '(symbol "A" (property "Value" "X"))'
        self.assertNotEqual(
            canonical_sexpr_hash(original),
            canonical_sexpr_hash(without),
        )

    def test_quoted_numeric_string_not_normalized(self):
        # A quoted "2.540" must stay distinct from a quoted "2.54"
        self.assertNotEqual(
            canonical_sexpr_hash('(name "2.540")'),
            canonical_sexpr_hash('(name "2.54")'),
        )

    def test_head_atom_stays_in_place(self):
        # Different node types with the same children must not collide
        self.assertNotEqual(
            canonical_sexpr_hash("(start 1 2)"),
            canonical_sexpr_hash("(end 1 2)"),
        )


class RealSymbolDataTest(unittest.TestCase):
    def _write_library(self, directory: Path) -> Path:
        library_path = directory / "lib.kicad_sym"
        library_path.write_text(SYMBOL_LIBRARY, encoding="utf-8")
        return library_path

    def test_hash_symbol_from_fixture_library(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            library_path = self._write_library(Path(temp_dir))
            symbol_hash = hash_symbol_in_library(library_path, "TEST_PART")
            self.assertIsInstance(symbol_hash, str)
            self.assertEqual(len(symbol_hash), 64)

    def test_missing_symbol_returns_none(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            library_path = self._write_library(Path(temp_dir))
            self.assertIsNone(hash_symbol_in_library(library_path, "DOES_NOT_EXIST"))

    def test_missing_library_returns_none(self):
        self.assertIsNone(
            hash_symbol_in_library("/nonexistent/path/lib.kicad_sym", "TEST_PART")
        )

    def test_reformatting_symbol_keeps_hash(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            original = self._write_library(directory)
            original_hash = hash_symbol_in_library(original, "TEST_PART")

            # Same symbol, heavily reformatted whitespace
            reformatted = SYMBOL_LIBRARY.replace("\n", "\n\n").replace("  ", "    ")
            reformatted_path = directory / "reformatted.kicad_sym"
            reformatted_path.write_text(reformatted, encoding="utf-8")
            reformatted_hash = hash_symbol_in_library(reformatted_path, "TEST_PART")

            self.assertEqual(original_hash, reformatted_hash)

    def test_modifying_property_differs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            original = self._write_library(directory)
            original_hash = hash_symbol_in_library(original, "TEST_PART")

            modified = SYMBOL_LIBRARY.replace(
                '(property "Value" "TEST_PART"',
                '(property "Value" "CHANGED_PART"',
            )
            modified_path = directory / "modified.kicad_sym"
            modified_path.write_text(modified, encoding="utf-8")
            modified_hash = hash_symbol_in_library(modified_path, "TEST_PART")

            self.assertNotEqual(original_hash, modified_hash)


class EndToEndImportHashTest(unittest.TestCase):
    def _create_zip(self, zip_path: Path) -> None:
        with ZipFile(zip_path, "w") as archive:
            archive.writestr("TEST_PART.kicad_sym", SYMBOL_LIBRARY)
            archive.writestr("TEST_FP.kicad_mod", FOOTPRINT)
            archive.writestr("TEST_FP.step", "STEP MODEL")

    def _run_import(self, root: Path) -> dict:
        zip_path = root / "part.zip"
        self._create_zip(zip_path)
        project_root = root / "project"
        return import_cad_zip(
            zip_path=zip_path,
            project_root=project_root,
            library_name="My_Parts",
            part_name="TEST_PART",
            update_library_tables=False,
            symbol_style=None,
        )

    def test_metadata_contains_hashes_and_verifies_match(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)
            result = self._run_import(root)

            metadata_path = Path(result["metadata"])
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

            # Hash keys are present and populated
            self.assertIn("symbol_hash", metadata)
            self.assertIn("footprint_hashes", metadata)
            self.assertIsInstance(metadata["symbol_hash"], str)
            self.assertEqual(len(metadata["symbol_hash"]), 64)
            self.assertEqual(metadata["symbol_name"], "TEST_PART")
            self.assertIn("TEST_FP", metadata["footprint_hashes"])
            self.assertEqual(len(metadata["footprint_hashes"]["TEST_FP"]), 64)

            # Existing metadata keys remain unchanged
            self.assertEqual(metadata["part_name"], "TEST_PART")
            self.assertIn("imported_assets", metadata)

            # A fresh import verifies as fully matching
            verification = verify_component_hashes(
                metadata_path=metadata_path,
                library_path=result["selected_symbol_library"],
                footprint_dir=result["selected_footprint_library"],
            )
            self.assertEqual(verification, {"symbol": "match", "footprints": "match"})

    def test_editing_symbol_reports_symbol_differs(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)
            result = self._run_import(root)

            # Rename a pin inside the on-disk symbol library
            library_path = Path(result["selected_symbol_library"])
            content = library_path.read_text(encoding="utf-8")
            content = content.replace('(name "IN"', '(name "RENAMED"')
            library_path.write_text(content, encoding="utf-8")

            verification = verify_component_hashes(
                metadata_path=result["metadata"],
                library_path=result["selected_symbol_library"],
                footprint_dir=result["selected_footprint_library"],
            )
            self.assertEqual(verification["symbol"], "differs")
            self.assertEqual(verification["footprints"], "match")

    def test_editing_footprint_reports_footprints_differ(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)
            result = self._run_import(root)

            # Change a value inside the on-disk footprint file
            footprint_path = Path(result["footprints"][0])
            content = footprint_path.read_text(encoding="utf-8")
            content = content.replace("(scale (xyz 1 1 1))", "(scale (xyz 2 2 2))")
            footprint_path.write_text(content, encoding="utf-8")

            verification = verify_component_hashes(
                metadata_path=result["metadata"],
                library_path=result["selected_symbol_library"],
                footprint_dir=result["selected_footprint_library"],
            )
            self.assertEqual(verification["symbol"], "match")
            self.assertEqual(verification["footprints"], "differs")

    def test_reformatting_footprint_keeps_match(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)
            result = self._run_import(root)

            # Reformat whitespace only; content is unchanged
            footprint_path = Path(result["footprints"][0])
            content = footprint_path.read_text(encoding="utf-8")
            content = content.replace("\n", "\n   ").replace("  ", " ")
            footprint_path.write_text(content, encoding="utf-8")

            verification = verify_component_hashes(
                metadata_path=result["metadata"],
                library_path=result["selected_symbol_library"],
                footprint_dir=result["selected_footprint_library"],
            )
            self.assertEqual(verification["footprints"], "match")

    def test_old_metadata_without_hashes_reports_unknown(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)
            result = self._run_import(root)

            # Simulate an old import: strip the hash keys from metadata
            metadata_path = Path(result["metadata"])
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata.pop("symbol_hash", None)
            metadata.pop("symbol_name", None)
            metadata.pop("footprint_hashes", None)
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

            verification = verify_component_hashes(
                metadata_path=metadata_path,
                library_path=result["selected_symbol_library"],
                footprint_dir=result["selected_footprint_library"],
            )
            self.assertEqual(
                verification,
                {"symbol": "unknown", "footprints": "unknown"},
            )

    def test_missing_footprint_file_reports_unknown(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)
            result = self._run_import(root)

            # Delete the imported footprint file
            Path(result["footprints"][0]).unlink()

            verification = verify_component_hashes(
                metadata_path=result["metadata"],
                library_path=result["selected_symbol_library"],
                footprint_dir=result["selected_footprint_library"],
            )
            self.assertEqual(verification["footprints"], "unknown")


if __name__ == "__main__":
    unittest.main()
