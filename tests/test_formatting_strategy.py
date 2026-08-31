import tempfile
import unittest
from pathlib import Path

from component_importer.formatting_strategy import (
    ClassicFormattingStrategy,
    NoOpFormattingStrategy,
    SymbolFormattingStrategy,
    strategy_from_symbol_style,
)
from component_importer.symbol_style import (
    SymbolStyle,
    apply_symbol_style_to_symbol_file,
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


class StrategyFactoryTest(unittest.TestCase):
    def test_none_maps_to_noop(self):
        strategy = strategy_from_symbol_style(None)
        self.assertIsInstance(strategy, NoOpFormattingStrategy)

    def test_symbol_style_maps_to_classic(self):
        strategy = strategy_from_symbol_style(SymbolStyle())
        self.assertIsInstance(strategy, ClassicFormattingStrategy)
        self.assertIsInstance(strategy.style, SymbolStyle)

    def test_dict_maps_to_classic(self):
        strategy = strategy_from_symbol_style({"line_width_mm": 0.3})
        self.assertIsInstance(strategy, ClassicFormattingStrategy)

    def test_strategy_instance_passes_through_unchanged(self):
        existing = NoOpFormattingStrategy()
        self.assertIs(strategy_from_symbol_style(existing), existing)

        classic = ClassicFormattingStrategy(SymbolStyle())
        self.assertIs(strategy_from_symbol_style(classic), classic)

    def test_base_class_is_abstract(self):
        self.assertTrue(issubclass(NoOpFormattingStrategy, SymbolFormattingStrategy))
        self.assertTrue(issubclass(ClassicFormattingStrategy, SymbolFormattingStrategy))


class NoOpStrategyTest(unittest.TestCase):
    def test_noop_leaves_file_untouched(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            library_path = Path(temp_dir) / "lib.kicad_sym"
            library_path.write_text(SYMBOL_LIBRARY, encoding="utf-8")

            result = NoOpFormattingStrategy().format_symbol_library_file(
                symbol_library_path=library_path,
                symbol_names=["TEST_PART"],
            )

            self.assertIsNone(result)
            self.assertEqual(
                library_path.read_text(encoding="utf-8"),
                SYMBOL_LIBRARY,
            )


class ClassicStrategyTest(unittest.TestCase):
    def test_classic_output_matches_direct_symbol_style_call(self):
        style = SymbolStyle()

        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            strategy_path = Path(temp_dir) / "strategy.kicad_sym"
            direct_path = Path(temp_dir) / "direct.kicad_sym"
            strategy_path.write_text(SYMBOL_LIBRARY, encoding="utf-8")
            direct_path.write_text(SYMBOL_LIBRARY, encoding="utf-8")

            strategy_result = ClassicFormattingStrategy(style).format_symbol_library_file(
                symbol_library_path=strategy_path,
                symbol_names=["TEST_PART"],
            )
            direct_result = apply_symbol_style_to_symbol_file(
                symbol_library_path=direct_path,
                symbol_style=style,
                symbol_names=["TEST_PART"],
            )

            self.assertEqual(strategy_result["updated"], direct_result["updated"])
            self.assertEqual(
                strategy_result["styled_symbol_names"],
                direct_result["styled_symbol_names"],
            )
            self.assertEqual(
                strategy_path.read_text(encoding="utf-8"),
                direct_path.read_text(encoding="utf-8"),
            )
            # The classic path must actually change something for this fixture.
            self.assertTrue(strategy_result["updated"])
            self.assertNotEqual(
                strategy_path.read_text(encoding="utf-8"),
                SYMBOL_LIBRARY,
            )


if __name__ == "__main__":
    unittest.main()
