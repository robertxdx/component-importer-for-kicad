import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from component_importer.cad_zip_importer import (
    build_overwrite_message,
    check_existing_component,
    import_cad_zip,
)
from component_importer.content_hash import verify_component_hashes


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


# The exact sentences the overwrite flow must produce for each mismatch shape
SYMBOL_SENTENCE = "The Symbol has been modified since it was imported."
FOOTPRINT_SENTENCE = "The Footprint has been modified since it was imported."
BOTH_SENTENCE = "The Symbol and Footprint have been modified since it was imported."


class OverwriteMessageBuilderTest(unittest.TestCase):
    def test_both_match_reports_only_base(self):
        message = build_overwrite_message(
            "PART", {"symbol": "match", "footprints": "match"}
        )
        self.assertEqual(message, "PART already exists in the library.")

    def test_symbol_differs_only(self):
        message = build_overwrite_message(
            "PART", {"symbol": "differs", "footprints": "match"}
        )
        self.assertTrue(message.endswith(SYMBOL_SENTENCE))
        self.assertNotIn("Footprint", message)

    def test_footprint_differs_only(self):
        message = build_overwrite_message(
            "PART", {"symbol": "match", "footprints": "differs"}
        )
        self.assertTrue(message.endswith(FOOTPRINT_SENTENCE))

    def test_both_differ(self):
        message = build_overwrite_message(
            "PART", {"symbol": "differs", "footprints": "differs"}
        )
        self.assertTrue(message.endswith(BOTH_SENTENCE))

    def test_unknown_symbol_maps_to_modified(self):
        # An unverifiable ("unknown") state is reported as modified
        message = build_overwrite_message(
            "PART", {"symbol": "unknown", "footprints": "match"}
        )
        self.assertTrue(message.endswith(SYMBOL_SENTENCE))

    def test_unknown_footprint_maps_to_modified(self):
        message = build_overwrite_message(
            "PART", {"symbol": "match", "footprints": "unknown"}
        )
        self.assertTrue(message.endswith(FOOTPRINT_SENTENCE))

    def test_both_unknown_reports_both_modified(self):
        message = build_overwrite_message(
            "PART", {"symbol": "unknown", "footprints": "unknown"}
        )
        self.assertTrue(message.endswith(BOTH_SENTENCE))

    def test_none_verification_reports_both_modified(self):
        message = build_overwrite_message("PART", None)
        self.assertTrue(message.endswith(BOTH_SENTENCE))

    def test_differs_and_unknown_reports_both_modified(self):
        message = build_overwrite_message(
            "PART", {"symbol": "differs", "footprints": "unknown"}
        )
        self.assertTrue(message.endswith(BOTH_SENTENCE))


class CheckExistingComponentTest(unittest.TestCase):
    def _create_zip(self, zip_path: Path, symbol_text: str = SYMBOL_LIBRARY) -> None:
        with ZipFile(zip_path, "w") as archive:
            archive.writestr("TEST_PART.kicad_sym", symbol_text)
            archive.writestr("TEST_FP.kicad_mod", FOOTPRINT)
            archive.writestr("TEST_FP.step", "STEP MODEL")

    def _import(self, root: Path) -> dict:
        zip_path = root / "part.zip"
        self._create_zip(zip_path)
        project_root = root / "project"
        result = import_cad_zip(
            zip_path=zip_path,
            project_root=project_root,
            library_name="MyParts",
            part_name="TEST_PART",
            update_library_tables=False,
            symbol_style=None,
        )
        return result

    def _check(self, root: Path) -> dict:
        return check_existing_component(
            zip_path=root / "part.zip",
            project_root=root / "project",
            library_name="MyParts",
            part_name="TEST_PART",
        )

    def test_new_component_not_detected(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)
            self._create_zip(root / "part.zip")
            info = check_existing_component(
                zip_path=root / "part.zip",
                project_root=root / "project",
                library_name="MyParts",
                part_name="TEST_PART",
            )
            self.assertFalse(info["already_exists"])

    def test_fresh_import_matches(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)
            self._import(root)
            info = self._check(root)
            self.assertTrue(info["already_exists"])
            self.assertEqual(
                info["verification"], {"symbol": "match", "footprints": "match"}
            )
            self.assertEqual(
                info["message"], "TEST_PART already exists in the library."
            )

    def test_edited_symbol_reports_symbol_sentence(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)
            result = self._import(root)
            lib = Path(result["selected_symbol_library"])
            lib.write_text(
                lib.read_text(encoding="utf-8").replace('(name "IN"', '(name "EDIT"'),
                encoding="utf-8",
            )
            info = self._check(root)
            self.assertTrue(info["already_exists"])
            self.assertTrue(info["message"].endswith(SYMBOL_SENTENCE))

    def test_edited_footprint_reports_footprint_sentence(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)
            result = self._import(root)
            fp = Path(result["footprints"][0])
            fp.write_text(
                fp.read_text(encoding="utf-8").replace(
                    "(scale (xyz 1 1 1))", "(scale (xyz 2 2 2))"
                ),
                encoding="utf-8",
            )
            info = self._check(root)
            self.assertTrue(info["message"].endswith(FOOTPRINT_SENTENCE))

    def test_edited_both_reports_both_sentence(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)
            result = self._import(root)
            lib = Path(result["selected_symbol_library"])
            lib.write_text(
                lib.read_text(encoding="utf-8").replace('(name "IN"', '(name "EDIT"'),
                encoding="utf-8",
            )
            fp = Path(result["footprints"][0])
            fp.write_text(
                fp.read_text(encoding="utf-8").replace(
                    "(scale (xyz 1 1 1))", "(scale (xyz 2 2 2))"
                ),
                encoding="utf-8",
            )
            info = self._check(root)
            self.assertTrue(info["message"].endswith(BOTH_SENTENCE))

    def _assert_both_modified_after_metadata(self, root: Path) -> None:
        info = self._check(root)
        self.assertTrue(info["already_exists"])
        self.assertTrue(info["message"].endswith(BOTH_SENTENCE))

    def test_missing_metadata_reports_both_modified(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)
            result = self._import(root)
            Path(result["metadata"]).unlink()
            self._assert_both_modified_after_metadata(root)

    def test_empty_metadata_reports_both_modified(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)
            result = self._import(root)
            Path(result["metadata"]).write_text("", encoding="utf-8")
            self._assert_both_modified_after_metadata(root)

    def test_invalid_json_metadata_reports_both_modified(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)
            result = self._import(root)
            Path(result["metadata"]).write_text("{not valid json", encoding="utf-8")
            self._assert_both_modified_after_metadata(root)

    def test_metadata_missing_hash_keys_reports_both_modified(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)
            result = self._import(root)
            metadata_path = Path(result["metadata"])
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata.pop("symbol_hash", None)
            metadata.pop("symbol_name", None)
            metadata.pop("footprint_hashes", None)
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
            self._assert_both_modified_after_metadata(root)

    def test_metadata_wrong_types_reports_both_modified(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)
            result = self._import(root)
            metadata_path = Path(result["metadata"])
            metadata_path.write_text(
                json.dumps(
                    {
                        "symbol_name": 123,
                        "symbol_hash": {"unexpected": "object"},
                        "footprint_hashes": "not-a-dict",
                    }
                ),
                encoding="utf-8",
            )
            self._assert_both_modified_after_metadata(root)


class VerifyHardeningTest(unittest.TestCase):
    def _dirs(self, root: Path):
        library = root / "lib.kicad_sym"
        library.write_text(SYMBOL_LIBRARY, encoding="utf-8")
        footprint_dir = root / "fp.pretty"
        footprint_dir.mkdir()
        (footprint_dir / "TEST_FP.kicad_mod").write_text(FOOTPRINT, encoding="utf-8")
        return library, footprint_dir

    def _verify(self, metadata_path, root):
        library, footprint_dir = self._dirs(root)
        return verify_component_hashes(metadata_path, library, footprint_dir)

    def test_missing_metadata_file(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)
            result = self._verify(root / "absent.json", root)
            self.assertEqual(result, {"symbol": "unknown", "footprints": "unknown"})

    def test_empty_metadata_file(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)
            path = root / "meta.json"
            path.write_text("", encoding="utf-8")
            result = self._verify(path, root)
            self.assertEqual(result, {"symbol": "unknown", "footprints": "unknown"})

    def test_invalid_json(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)
            path = root / "meta.json"
            path.write_text("{oops", encoding="utf-8")
            result = self._verify(path, root)
            self.assertEqual(result, {"symbol": "unknown", "footprints": "unknown"})

    def test_json_not_object(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)
            path = root / "meta.json"
            path.write_text("[1, 2, 3]", encoding="utf-8")
            result = self._verify(path, root)
            self.assertEqual(result, {"symbol": "unknown", "footprints": "unknown"})

    def test_wrong_types_do_not_crash(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)
            path = root / "meta.json"
            path.write_text(
                json.dumps(
                    {
                        "symbol_name": 42,
                        "symbol_hash": ["list"],
                        "footprint_hashes": "string",
                    }
                ),
                encoding="utf-8",
            )
            # Must not raise; unverifiable values stay unknown
            result = self._verify(path, root)
            self.assertEqual(result["symbol"], "unknown")
            self.assertEqual(result["footprints"], "unknown")


if __name__ == "__main__":
    unittest.main()
