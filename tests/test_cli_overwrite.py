import contextlib
import io
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from component_importer import cli


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

SYMBOL_SENTENCE = "The Symbol has been modified since it was imported."
FOOTPRINT_SENTENCE = "The Footprint has been modified since it was imported."
BOTH_SENTENCE = "The Symbol and Footprint have been modified since it was imported."


class _FakeStdin:
    def __init__(self, tty: bool):
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


@contextlib.contextmanager
def chdir(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def run_main(argv, *, tty=True, inputs=None):
    out = io.StringIO()
    input_iter = iter(inputs or [])

    def fake_input(prompt=""):
        try:
            return next(input_iter)
        except StopIteration:
            raise EOFError

    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out), patch(
        "sys.stdin", _FakeStdin(tty)
    ), patch("builtins.input", fake_input):
        code = cli.main(argv)

    return code, out.getvalue()


class CliOverwriteTest(unittest.TestCase):
    def _create_zip(self, zip_path: Path, symbol_text: str = SYMBOL_LIBRARY) -> None:
        with ZipFile(zip_path, "w") as archive:
            archive.writestr("TEST_PART.kicad_sym", symbol_text)
            archive.writestr("TEST_FP.kicad_mod", FOOTPRINT)
            archive.writestr("TEST_FP.step", "STEP MODEL")

    def _make_project(self, root: Path) -> None:
        (root / "demo.kicad_pro").write_text("{}", encoding="utf-8")

    def _setup_imported(self, root: Path) -> None:
        # A project with one already-imported part
        self._make_project(root)
        self._create_zip(root / "part.zip")
        with chdir(root):
            run_main(["init", "--library", "MyParts"])
            code, _ = run_main(["import", "part.zip"])
        self.assertEqual(code, 0)

    def _lib_path(self, root: Path) -> Path:
        return root / "libraries" / "MyParts.kicad_sym"

    def _footprint_path(self, root: Path) -> Path:
        return root / "libraries" / "MyParts.pretty" / "TEST_FP.kicad_mod"

    def _metadata_path(self, root: Path) -> Path:
        return root / "libraries" / "metadata" / "TEST_PART_import_metadata.json"

    def test_prompt_shown_and_cancel_keeps_zip(self):
        with self._temp() as root:
            self._setup_imported(root)
            with chdir(root):
                code, output = run_main(
                    ["import", "part.zip", "--delete"], tty=True, inputs=["N"]
                )
            self.assertEqual(code, 0)
            self.assertIn("already exists in the library", output)
            self.assertIn("Cancelled", output)
            # A cancelled overwrite must keep the ZIP on disk
            self.assertTrue((root / "part.zip").exists())

    def test_overwrite_replaces_library_content(self):
        with self._temp() as root:
            self._setup_imported(root)
            # Re-create the source ZIP with a changed symbol pin name
            modified = SYMBOL_LIBRARY.replace('(name "IN"', '(name "REPLACED"')
            self._create_zip(root / "part.zip", symbol_text=modified)
            with chdir(root):
                code, output = run_main(
                    ["import", "part.zip"], tty=True, inputs=["y"]
                )
            self.assertEqual(code, 0)
            self.assertIn("REPLACED", self._lib_path(root).read_text(encoding="utf-8"))

    def test_yes_flag_skips_prompt(self):
        with self._temp() as root:
            self._setup_imported(root)
            with chdir(root):
                # inputs=None: if the prompt were reached, input() would raise
                # EOFError and the message would say "Cancelled" instead.
                code, output = run_main(["import", "part.zip", "--yes"], tty=True)
            self.assertEqual(code, 0)
            self.assertIn("Overwriting TEST_PART (--yes)", output)
            self.assertNotIn("Cancelled", output)

    def test_non_tty_defaults_to_cancel(self):
        with self._temp() as root:
            self._setup_imported(root)
            with chdir(root):
                code, output = run_main(
                    ["import", "part.zip", "--delete"], tty=False
                )
            self.assertEqual(code, 0)
            self.assertIn("not a terminal", output)
            self.assertIn("Cancelled", output)
            self.assertTrue((root / "part.zip").exists())

    def test_all_yes_overwrites_multiple(self):
        with self._temp() as root:
            self._make_project(root)
            self._create_zip(root / "aaa.zip", symbol_text=SYMBOL_LIBRARY)
            bbb = SYMBOL_LIBRARY.replace("TEST_PART", "OTHER_PART")
            self._create_zip(root / "bbb.zip", symbol_text=bbb)
            with chdir(root):
                run_main(["init", "--library", "MyParts"])
                # First pass imports both (nothing exists yet, no prompts)
                first, _ = run_main(["import", "--all"])
                self.assertEqual(first, 0)
                # Second pass: both exist; --yes overwrites all with no prompt
                code, output = run_main(["import", "--all", "--yes"])
            self.assertEqual(code, 0)
            self.assertEqual(output.count("Overwriting"), 2)
            self.assertIn("Imported 2 of 2", output)

    def test_all_cancel_excludes_only_that_zip_from_delete(self):
        with self._temp() as root:
            self._make_project(root)
            self._create_zip(root / "aaa.zip", symbol_text=SYMBOL_LIBRARY)
            bbb = SYMBOL_LIBRARY.replace("TEST_PART", "OTHER_PART")
            self._create_zip(root / "bbb.zip", symbol_text=bbb)
            with chdir(root):
                run_main(["init", "--library", "MyParts"])
                run_main(["import", "--all"])
                # aaa -> overwrite (y, deletable), bbb -> cancel (N, kept)
                code, output = run_main(
                    ["import", "--all", "--delete"], tty=True, inputs=["y", "N"]
                )
            self.assertEqual(code, 0)
            # The cancelled part keeps its ZIP; the overwritten one is deleted
            self.assertFalse((root / "aaa.zip").exists())
            self.assertTrue((root / "bbb.zip").exists())
            self.assertIn("Imported 1 of 2", output)

    def test_wording_symbol_modified(self):
        with self._temp() as root:
            self._setup_imported(root)
            lib = self._lib_path(root)
            lib.write_text(
                lib.read_text(encoding="utf-8").replace('(name "IN"', '(name "EDIT"'),
                encoding="utf-8",
            )
            with chdir(root):
                code, output = run_main(
                    ["import", "part.zip"], tty=True, inputs=["N"]
                )
            self.assertEqual(code, 0)
            self.assertIn(SYMBOL_SENTENCE, output)

    def test_wording_footprint_modified(self):
        with self._temp() as root:
            self._setup_imported(root)
            fp = self._footprint_path(root)
            fp.write_text(
                fp.read_text(encoding="utf-8").replace(
                    "(scale (xyz 1 1 1))", "(scale (xyz 2 2 2))"
                ),
                encoding="utf-8",
            )
            with chdir(root):
                code, output = run_main(
                    ["import", "part.zip"], tty=True, inputs=["N"]
                )
            self.assertEqual(code, 0)
            self.assertIn(FOOTPRINT_SENTENCE, output)

    def test_wording_both_modified(self):
        with self._temp() as root:
            self._setup_imported(root)
            lib = self._lib_path(root)
            lib.write_text(
                lib.read_text(encoding="utf-8").replace('(name "IN"', '(name "EDIT"'),
                encoding="utf-8",
            )
            fp = self._footprint_path(root)
            fp.write_text(
                fp.read_text(encoding="utf-8").replace(
                    "(scale (xyz 1 1 1))", "(scale (xyz 2 2 2))"
                ),
                encoding="utf-8",
            )
            with chdir(root):
                code, output = run_main(
                    ["import", "part.zip"], tty=True, inputs=["N"]
                )
            self.assertEqual(code, 0)
            self.assertIn(BOTH_SENTENCE, output)

    def _assert_bad_metadata_reports_both(self, corrupt) -> None:
        with self._temp() as root:
            self._setup_imported(root)
            corrupt(self._metadata_path(root))
            with chdir(root):
                code, output = run_main(
                    ["import", "part.zip"], tty=True, inputs=["N"]
                )
            self.assertEqual(code, 0)
            self.assertIn(BOTH_SENTENCE, output)
            # Cancel is still available and keeps the part unchanged
            self.assertIn("Cancelled", output)

    def test_wording_metadata_absent(self):
        self._assert_bad_metadata_reports_both(lambda path: path.unlink())

    def test_wording_metadata_empty(self):
        self._assert_bad_metadata_reports_both(
            lambda path: path.write_text("", encoding="utf-8")
        )

    def test_wording_metadata_invalid_json(self):
        self._assert_bad_metadata_reports_both(
            lambda path: path.write_text("{bad json", encoding="utf-8")
        )

    def test_wording_metadata_missing_hash_keys(self):
        def strip_keys(path: Path) -> None:
            metadata = json.loads(path.read_text(encoding="utf-8"))
            for key in ("symbol_hash", "symbol_name", "footprint_hashes"):
                metadata.pop(key, None)
            path.write_text(json.dumps(metadata), encoding="utf-8")

        self._assert_bad_metadata_reports_both(strip_keys)

    def test_wording_metadata_wrong_types(self):
        self._assert_bad_metadata_reports_both(
            lambda path: path.write_text(
                json.dumps(
                    {
                        "symbol_name": 5,
                        "symbol_hash": {"x": 1},
                        "footprint_hashes": "nope",
                    }
                ),
                encoding="utf-8",
            )
        )

    @contextlib.contextmanager
    def _temp(self):
        import tempfile

        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            yield Path(temp_dir).resolve()


if __name__ == "__main__":
    unittest.main()
