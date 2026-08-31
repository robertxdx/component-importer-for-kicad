# Import ABC helpers to define the strategy interface
from abc import ABC, abstractmethod

# Import Path for filesystem paths
from pathlib import Path

# Import the classic symbol style dataclass and its file rewriter
from component_importer.symbol_style import SymbolStyle
from component_importer.symbol_style import apply_symbol_style_to_symbol_file
from component_importer.symbol_style import normalize_symbol_style


class SymbolFormattingStrategy(ABC):
    """Base class for symbol-formatting strategies.

    A strategy owns the single decision of how a merged symbol library file
    should be rewritten for the symbols imported in one operation. Concrete
    strategies exist for the no-op case (leave symbols untouched) and the
    classic SymbolStyle rewrite. A future "interactive" strategy will slot in
    here as another subclass, wired through strategy_from_symbol_style().
    """

    @abstractmethod
    def format_symbol_library_file(
        self,
        symbol_library_path: str | Path,
        symbol_names: list[str],
    ) -> dict | None:
        """Rewrite the given symbols in the symbol library file.

        Returns the same result dictionary that
        apply_symbol_style_to_symbol_file() produces, or None when the
        strategy performs no formatting.
        """
        raise NotImplementedError


class NoOpFormattingStrategy(SymbolFormattingStrategy):
    """Leave imported symbols exactly as they were merged (no styling)."""

    def format_symbol_library_file(
        self,
        symbol_library_path: str | Path,
        symbol_names: list[str],
    ) -> dict | None:
        return None


class ClassicFormattingStrategy(SymbolFormattingStrategy):
    """Apply the classic SymbolStyle rewrite via the existing symbol_style code."""

    def __init__(self, style: SymbolStyle):
        self.style = style

    def format_symbol_library_file(
        self,
        symbol_library_path: str | Path,
        symbol_names: list[str],
    ) -> dict | None:
        return apply_symbol_style_to_symbol_file(
            symbol_library_path=symbol_library_path,
            symbol_style=self.style,
            symbol_names=symbol_names,
        )


def strategy_from_symbol_style(
    style: SymbolStyle | dict | SymbolFormattingStrategy | None,
) -> SymbolFormattingStrategy:
    """Map a symbol style value to a formatting strategy.

    None maps to NoOpFormattingStrategy and a SymbolStyle/dict maps to
    ClassicFormattingStrategy. An already-constructed strategy instance is
    passed through unchanged so callers can hand import_cad_zip a strategy
    directly (the hook a later interactive strategy will use).
    """
    if isinstance(style, SymbolFormattingStrategy):
        return style

    normalized_style = normalize_symbol_style(style)

    if normalized_style is None:
        return NoOpFormattingStrategy()

    return ClassicFormattingStrategy(normalized_style)
