import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch
from zipfile import ZipFile

from component_importer.cad_zip_importer import import_cad_zip
from component_importer.gui_config_manager import GuiConfig
from component_importer.gui_import_worker import ImportComponentWorker


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


def _create_zip(zip_path: Path, symbol_text: str = SYMBOL_LIBRARY) -> None:
    with ZipFile(zip_path, "w") as archive:
        archive.writestr("TEST_PART.kicad_sym", symbol_text)
        archive.writestr("TEST_FP.kicad_mod", FOOTPRINT)
        archive.writestr("TEST_FP.step", "STEP MODEL")


class WorkerSkipFlagTest(unittest.TestCase):
    def _prepare_project(self, root: Path) -> Path:
        project_root = root / "project"
        project_root.mkdir()
        (project_root / "demo.kicad_pro").write_text("{}", encoding="utf-8")
        _create_zip(root / "v1.zip")
        import_cad_zip(
            zip_path=root / "v1.zip",
            project_root=project_root,
            library_name="MyParts",
            part_name="TEST_PART",
            update_library_tables=False,
            symbol_style=None,
        )
        return project_root

    def _run_worker(self, root, project_root, skip_existing_components):
        modified = SYMBOL_LIBRARY.replace('(name "IN"', '(name "REPLACED"')
        _create_zip(root / "v2.zip", symbol_text=modified)
        config = GuiConfig(
            project_root=str(project_root),
            library_name="MyParts",
            downloads_folder=str(root),
            import_to_global_library=False,
            symbol_style_enabled=False,
            auto_import_enabled=False,
        )
        finished = []
        failed = []
        worker = ImportComponentWorker(
            str(root / "v2.zip"),
            "TEST_PART",
            config,
            skip_existing_components=skip_existing_components,
        )
        worker.finished.connect(
            lambda result, validation, output: finished.append(result)
        )
        worker.failed.connect(failed.append)
        worker.run()
        self.assertFalse(failed, failed)
        return project_root / "libraries" / "MyParts.kicad_sym"

    def test_skip_false_overwrites_library_content(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)
            project_root = self._prepare_project(root)
            lib = self._run_worker(root, project_root, skip_existing_components=False)
            self.assertIn("REPLACED", lib.read_text(encoding="utf-8"))

    def test_skip_true_keeps_existing_library_content(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)
            project_root = self._prepare_project(root)
            lib = self._run_worker(root, project_root, skip_existing_components=True)
            text = lib.read_text(encoding="utf-8")
            self.assertNotIn("REPLACED", text)
            self.assertIn('(name "IN"', text)


@unittest.skipUnless(
    os.environ.get("QT_QPA_PLATFORM") == "offscreen",
    "GUI test requires QT_QPA_PLATFORM=offscreen",
)
class MainWindowOverwriteDecisionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def _make_window(self):
        from component_importer import gui_main_window

        # A minimal config avoids all filesystem side effects during __init__:
        # auto-import is off (no watcher) and the config is invalid enough that
        # prepare_project_libraries does nothing.
        loaded = GuiConfig(
            project_root="",
            downloads_folder="/nonexistent-kicad-importer-test",
            auto_import_enabled=False,
        )
        with patch.object(gui_main_window, "load_gui_config", return_value=loaded), \
             patch.object(gui_main_window, "set_startup_enabled"):
            window = gui_main_window.MainWindow()

        # Isolate the decision path from config validation and library prep
        window.check_config_before_operation = lambda: True
        window.prepare_project_libraries = lambda **kwargs: True
        window.import_busy = False
        window.config = GuiConfig(
            project_root="/nonexistent-kicad-importer-test",
            library_name="MyParts",
            downloads_folder="/nonexistent-kicad-importer-test",
            auto_import_enabled=False,
            interactive_pin_layout=False,
        )
        return window

    def _patched_worker(self, gui_main_window):
        # Replace the worker and thread with recorders so start_import performs
        # no real import work but its constructor kwargs stay observable.
        return (
            patch.object(gui_main_window, "ImportComponentWorker"),
            patch.object(gui_main_window, "QThread"),
        )

    def test_manual_overwrite_starts_worker_with_skip_false(self):
        from component_importer import gui_main_window
        from PyQt6.QtWidgets import QMessageBox

        window = self._make_window()
        existing = {
            "already_exists": True,
            "verification": {"symbol": "differs", "footprints": "match"},
            "message": "PART already exists in the library.",
        }
        with patch.object(
            gui_main_window, "check_existing_component", return_value=existing
        ), patch.object(
            QMessageBox, "exec", return_value=QMessageBox.StandardButton.Ok
        ), patch.object(
            gui_main_window, "ImportComponentWorker"
        ) as worker_cls, patch.object(gui_main_window, "QThread"):
            window.start_import("part.zip", "PART", auto_import=False)

        worker_cls.assert_called_once()
        self.assertFalse(worker_cls.call_args.kwargs["skip_existing_components"])
        self.assertTrue(window.import_busy)

    def test_manual_cancel_starts_no_worker(self):
        from component_importer import gui_main_window
        from PyQt6.QtWidgets import QMessageBox

        window = self._make_window()
        existing = {
            "already_exists": True,
            "verification": {"symbol": "match", "footprints": "match"},
            "message": "PART already exists in the library.",
        }
        with patch.object(
            gui_main_window, "check_existing_component", return_value=existing
        ), patch.object(
            QMessageBox, "exec", return_value=QMessageBox.StandardButton.Cancel
        ), patch.object(
            gui_main_window, "ImportComponentWorker"
        ) as worker_cls, patch.object(gui_main_window, "QThread"):
            window.start_import("part.zip", "PART", auto_import=False)

        worker_cls.assert_not_called()
        self.assertFalse(window.import_busy)

    def test_manual_new_part_skips_dialog_and_imports(self):
        from component_importer import gui_main_window
        from PyQt6.QtWidgets import QMessageBox

        window = self._make_window()
        existing = {
            "already_exists": False,
            "verification": {"symbol": "unknown", "footprints": "unknown"},
            "message": "",
        }
        with patch.object(
            gui_main_window, "check_existing_component", return_value=existing
        ), patch.object(QMessageBox, "exec") as exec_mock, patch.object(
            gui_main_window, "ImportComponentWorker"
        ) as worker_cls, patch.object(gui_main_window, "QThread"):
            window.start_import("part.zip", "PART", auto_import=False)

        exec_mock.assert_not_called()
        worker_cls.assert_called_once()
        self.assertTrue(worker_cls.call_args.kwargs["skip_existing_components"])

    def test_auto_import_never_prompts_or_reconstructs(self):
        from component_importer import gui_main_window

        window = self._make_window()
        # Interactive pin layout ON: the auto path must still stay silent.
        window.config = replace(window.config, interactive_pin_layout=True)

        overwrite_spy = MagicMock()
        interactive_spy = MagicMock(return_value=None)
        window.resolve_overwrite_decision = overwrite_spy
        window.resolve_interactive_strategy = interactive_spy

        with patch.object(
            gui_main_window, "ImportComponentWorker"
        ) as worker_cls, patch.object(gui_main_window, "QThread"):
            window.start_import("part.zip", "PART", auto_import=True)

        overwrite_spy.assert_not_called()
        interactive_spy.assert_not_called()
        worker_cls.assert_called_once()
        self.assertTrue(worker_cls.call_args.kwargs["skip_existing_components"])

    def test_auto_import_existing_part_interactive_on_stays_silent(self):
        from component_importer import gui_main_window
        from PyQt6.QtWidgets import QMessageBox

        window = self._make_window()
        # Interactive pin layout ON and the part already exists on disk: the auto
        # path must still start the worker with skip=True, never open the
        # overwrite dialog, and never consult either resolver.
        window.config = replace(window.config, interactive_pin_layout=True)

        overwrite_spy = MagicMock()
        interactive_spy = MagicMock(return_value=None)
        window.resolve_overwrite_decision = overwrite_spy
        window.resolve_interactive_strategy = interactive_spy

        existing = {
            "already_exists": True,
            "verification": {"symbol": "differs", "footprints": "differs"},
            "message": "PART already exists in the library.",
        }
        with patch.object(
            gui_main_window, "check_existing_component", return_value=existing
        ) as existing_mock, patch.object(
            QMessageBox, "exec"
        ) as exec_mock, patch.object(
            gui_main_window, "ImportComponentWorker"
        ) as worker_cls, patch.object(gui_main_window, "QThread"):
            window.start_import("part.zip", "PART", auto_import=True)

        # No dialog, no existence probe, no resolver calls: fully silent.
        exec_mock.assert_not_called()
        existing_mock.assert_not_called()
        overwrite_spy.assert_not_called()
        interactive_spy.assert_not_called()
        worker_cls.assert_called_once()
        self.assertTrue(worker_cls.call_args.kwargs["skip_existing_components"])


if __name__ == "__main__":
    unittest.main()
