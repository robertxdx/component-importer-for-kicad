import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from component_importer.cad_zip_importer import import_cad_zip
from component_importer.import_validator import validate_imported_part
from component_importer.gui_config_manager import GuiConfig, load_gui_config, save_gui_config
from component_importer.gui_import_worker import ImportComponentWorker
from component_importer.library_table_updater import (
    find_library_uri_in_table,
    update_global_kicad_library_tables,
)


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


class GlobalImportTest(unittest.TestCase):
    def create_zip(self, zip_path: Path) -> None:
        with ZipFile(zip_path, "w") as archive:
            archive.writestr("TEST_PART.kicad_sym", SYMBOL_LIBRARY)
            archive.writestr("TEST_FP.kicad_mod", FOOTPRINT)
            archive.writestr("TEST_FP.step", "STEP MODEL")

    def test_imports_and_registers_global_library(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)
            zip_path = root / "part.zip"
            global_root = root / "global"
            kicad_config = root / "kicad" / "10.0"
            kicad_config.mkdir(parents=True)

            self.create_zip(zip_path)

            model_dir = (
                global_root / "3DModels" / "My_Global_Parts.3dshapes"
            )
            result = import_cad_zip(
                zip_path=zip_path,
                project_root=global_root,
                library_name="My_Global_Parts",
                part_name="TEST_PART",
                update_library_tables=False,
                library_layout="external",
                symbol_style=None,
            )
            result["library_table_update"] = update_global_kicad_library_tables(
                kicad_config_dir=kicad_config,
                library_name="My_Global_Parts",
                footprint_library_path=result["selected_footprint_library"],
                symbol_library_paths=[result["selected_symbol_library"]],
            )

            symbol_uri = find_library_uri_in_table(
                kicad_config / "sym-lib-table",
                "My_Global_Parts",
            )
            footprint_uri = find_library_uri_in_table(
                kicad_config / "fp-lib-table",
                "My_Global_Parts",
            )
            self.assertEqual(
                symbol_uri,
                Path(result["selected_symbol_library"]).resolve().as_posix(),
            )
            self.assertEqual(
                footprint_uri,
                Path(result["selected_footprint_library"]).resolve().as_posix(),
            )

            footprint_text = Path(result["footprints"][0]).read_text(encoding="utf-8")
            self.assertIn(model_dir.resolve().as_posix(), footprint_text)
            self.assertNotIn("${KIPRJMOD}", footprint_text)

            validation = validate_imported_part(
                project_root=global_root,
                result=result,
                library_name="My_Global_Parts",
                table_root=kicad_config,
                global_tables=True,
            )
            self.assertTrue(validation["passed"], validation)

            unchanged = update_global_kicad_library_tables(
                kicad_config_dir=kicad_config,
                library_name="My_Global_Parts",
                footprint_library_path=result["selected_footprint_library"],
                symbol_library_paths=[result["selected_symbol_library"]],
            )
            self.assertFalse(unchanged["footprint_table_updated"])
            self.assertFalse(unchanged["symbol_tables_updated"])

    def test_worker_imports_project_and_global_destinations(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)
            project_root = root / "project"
            project_root.mkdir()
            (project_root / "demo.kicad_pro").write_text("{}", encoding="utf-8")
            global_root = root / "global"
            existing_symbol_dir = (
                global_root / "Symbols" / "Global_Shared_Parts"
            )
            existing_symbol_dir.mkdir(parents=True)
            existing_symbol_path = (
                existing_symbol_dir / "Global_Shared_Parts.kicad_sym"
            )
            existing_symbol_path.write_text(
                "(kicad_symbol_lib\n  (version 20231120)\n)\n",
                encoding="utf-8",
            )
            kicad_config = root / "kicad" / "10.0"
            kicad_config.mkdir(parents=True)
            zip_path = root / "part.zip"
            self.create_zip(zip_path)

            config = GuiConfig(
                project_root=str(project_root),
                library_name="Shared_Parts",
                downloads_folder=str(root),
                import_to_global_library=True,
                global_library_root=str(global_root),
                global_library_name="Global_Shared_Parts",
                kicad_config_dir=str(kicad_config),
                symbol_style_enabled=False,
            )
            finished = []
            failed = []
            worker = ImportComponentWorker(str(zip_path), "TEST_PART", config)
            worker.finished.connect(
                lambda result, validation, output: finished.append(
                    (result, validation, output)
                )
            )
            worker.failed.connect(failed.append)
            worker.run()

            self.assertFalse(failed, failed)
            self.assertEqual(len(finished), 1)
            result, validation, output = finished[0]
            self.assertTrue(validation["passed"], validation)
            self.assertIn("global_import", result)
            self.assertIn("Global library: OK", output)
            self.assertTrue((project_root / "sym-lib-table").exists())
            self.assertTrue((kicad_config / "sym-lib-table").exists())
            self.assertTrue(
                (
                    global_root
                    / "Symbols"
                    / "Global_Shared_Parts"
                    / "Global_Shared_Parts.kicad_sym"
                ).exists()
            )
            self.assertFalse(
                (
                    global_root
                    / "Symbols"
                    / "Global_Shared_Parts.kicad_sym"
                ).exists()
            )
            self.assertTrue(
                (
                    global_root
                    / "Footprints"
                    / "Global_Shared_Parts.pretty"
                ).is_dir()
            )

    def test_config_save_accepts_cloud_replace_error_after_success(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            config_path = Path(temp_dir) / "gui_config.json"
            config = GuiConfig(import_to_global_library=True)
            path_class = type(config_path)

            def replace_then_report_access_denied(source, target):
                target = Path(target)
                target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
                raise PermissionError(5, "Access is denied", str(target))

            with patch.object(
                path_class,
                "replace",
                autospec=True,
                side_effect=replace_then_report_access_denied,
            ):
                save_gui_config(config, config_path)

            loaded = load_gui_config(config_path)
            self.assertTrue(loaded.import_to_global_library)
            self.assertFalse(config_path.with_name("gui_config.json.tmp").exists())


if __name__ == "__main__":
    unittest.main()
