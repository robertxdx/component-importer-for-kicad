# Import widgets
from PyQt6.QtWidgets import QWidget
from PyQt6.QtWidgets import QVBoxLayout
from PyQt6.QtWidgets import QHBoxLayout
from PyQt6.QtWidgets import QLineEdit
from PyQt6.QtWidgets import QPushButton
from PyQt6.QtWidgets import QListWidget
from PyQt6.QtWidgets import QLabel
from PyQt6.QtWidgets import QComboBox

# Import signals
from PyQt6.QtCore import pyqtSignal

# Import online search helpers
from online_component_search import build_component_search_results
from online_component_search import open_search_result


# Search tab
class SearchTab(QWidget):
    # Provider choices shown in the dropdown.
    # The second value must match OnlineSearchResult.provider exactly.
    PROVIDER_CHOICES = [
        ("All", None),
        ("SnapMagic / SnapEDA", "SnapMagic / SnapEDA"),
        ("ComponentSearchEngine / SamacSys", "ComponentSearchEngine / SamacSys"),
        ("Ultra Librarian", "Ultra Librarian"),
        ("DigiKey", "DigiKey"),
        ("Mouser", "Mouser"),
        ("Octopart", "Octopart"),
    ]

    # Log signal
    logMessage = pyqtSignal(str)

    # Create tab
    def __init__(self):
        # Initialize QWidget
        super().__init__()

        # Store results
        self.results = []
        self.all_results = []

        # Build UI
        self.build_ui()

    # Build UI
    def build_ui(self) -> None:
        # Main layout
        main_layout = QVBoxLayout(self)

        # Help label
        help_label = QLabel(
            "Search opens provider pages in your browser. "
            "After downloading a KiCad ZIP, use Import ZIP or enable auto import."
        )
        help_label.setWordWrap(True)

        # Search row
        search_row = QHBoxLayout()
        self.query_edit = QLineEdit()
        self.query_edit.setPlaceholderText("Enter MPN, for example AP63203WU")
        self.search_button = QPushButton("Search")
        self.open_selected_button = QPushButton("Open Selected")
        self.open_all_button = QPushButton("Open Results")

        # Add search widgets
        search_row.addWidget(self.query_edit)
        search_row.addWidget(self.search_button)
        search_row.addWidget(self.open_selected_button)
        search_row.addWidget(self.open_all_button)

        # Provider selection row
        provider_row = QHBoxLayout()
        provider_row.addWidget(QLabel("Provider:"))

        self.provider_combo = QComboBox()

        for label, provider_name in self.PROVIDER_CHOICES:
            self.provider_combo.addItem(label, provider_name)

        provider_row.addWidget(self.provider_combo)
        provider_row.addStretch()

        # Results list
        self.results_list = QListWidget()

        # Add widgets
        main_layout.addWidget(help_label)
        main_layout.addLayout(search_row)
        main_layout.addLayout(provider_row)
        main_layout.addWidget(self.results_list)

        # Connect signals
        self.search_button.clicked.connect(self.search)
        self.open_selected_button.clicked.connect(self.open_selected)
        self.open_all_button.clicked.connect(self.open_visible_results)
        self.results_list.itemDoubleClicked.connect(self.open_selected)
        self.provider_combo.currentIndexChanged.connect(self.refresh_results_list)

    # Get selected provider name, or None for all providers
    def get_selected_provider_name(self) -> str | None:
        return self.provider_combo.currentData()

    # Check whether a search result should be shown for current provider settings
    def should_include_result(self, result) -> bool:
        # All providers selected
        selected_provider = self.get_selected_provider_name()

        if selected_provider is None:
            return True

        # Single provider selected
        return result.provider == selected_provider

    # Refresh visible results based on current provider selection
    def refresh_results_list(self, *args) -> None:
        # Return if no search has been run yet
        if not self.all_results:
            return

        # Filter current results
        self.results = [
            result
            for result in self.all_results
            if self.should_include_result(result)
        ]

        # Rebuild list
        self.results_list.clear()

        for result in self.results:
            self.results_list.addItem(
                f"{result.provider} | {result.result_type} | {result.url}"
            )

    # Search online
    def search(self) -> None:
        # Get query
        query = self.query_edit.text().strip()

        # Stop if empty
        if not query:
            self.logMessage.emit("Search query is empty.")
            return

        try:
            # Build and filter results
            self.all_results = build_component_search_results(query)
            self.refresh_results_list()

            # Log message
            selected_provider = self.provider_combo.currentText()

            self.logMessage.emit(
                f"Found {len(self.results)} provider links for {query}. "
                f"Provider: {selected_provider}."
            )

        except Exception as error:
            # Log error
            self.logMessage.emit(f"Search failed: {error}")

    # Open selected result
    def open_selected(self) -> None:
        # Get selected row
        row = self.results_list.currentRow()

        # Stop if invalid
        if row < 0 or row >= len(self.results):
            self.logMessage.emit("No search result selected.")
            return

        # Open result
        open_search_result(self.results, row + 1)

        # Log message
        self.logMessage.emit(f"Opened: {self.results[row].provider}")

    # Open all currently visible provider results
    def open_visible_results(self) -> None:
        # Stop if no results
        if not self.results:
            self.logMessage.emit("No search results available.")
            return

        # Open visible provider results
        count = 0

        # Loop through results
        for index, result in enumerate(self.results, start=1):
            open_search_result(self.results, index)
            count += 1

        # Log message
        if count:
            self.logMessage.emit(f"Opened {count} provider page(s).")
        else:
            self.logMessage.emit("No provider pages available.")
