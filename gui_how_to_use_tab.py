# Import widgets
from PyQt6.QtWidgets import QTextBrowser
from PyQt6.QtWidgets import QVBoxLayout
from PyQt6.QtWidgets import QWidget


# Help tab explaining the normal app workflow
class HowToUseTab(QWidget):
    # Create tab
    def __init__(self):
        # Initialize QWidget
        super().__init__()

        # Build UI
        self.build_ui()

    # Build UI widgets
    def build_ui(self) -> None:
        # Main layout
        main_layout = QVBoxLayout(self)

        # Read-only help text
        help_text = QTextBrowser()
        help_text.setOpenExternalLinks(True)
        help_text.setHtml(
            """
            <h2>First use with a KiCad project</h2>

            <h3>Step 1.</h3>
            <p>
              Create the KiCad project first, if it does not already exist.
              The project must have a folder containing a <b>.kicad_pro</b> file.
            </p>

            <h3>Step 2.</h3>
            <p>
              Close KiCad fully before the first setup. Close the schematic
              editor, PCB editor, and KiCad project window.
            </p>

            <h3>Step 3.</h3>
            <p>
              Open this importer app and go to the <b>Configuration</b> tab.
              Select the KiCad project root folder.
            </p>

            <h3>Step 4.</h3>
            <p>
              Name your components library. Use the same name for the main,
              symbol, and footprint library unless you have a specific reason
              to split them. When the configuration is saved, the app creates
              and registers these project libraries.
            </p>

            <h3>Step 5.</h3>
            <p>
              Choose the folder where you download component ZIP files, then
              click <b>Save Configuration</b>.
            </p>

            <h3>Step 6.</h3>
            <p>
              Open KiCad again and open the schematic. The project libraries
              are now already registered before KiCad loads the project.
            </p>

            <h2>Normal importing after first setup</h2>

            <h3>Step 1.</h3>
            <p>
              Search for a part online or download a component ZIP manually from a
              provider.
            </p>

            <h3>Step 2.</h3>
            <p>
              Import the ZIP. Double-click a ZIP entry in the Import ZIP tab, or
              select it and click <b>Use Selected ZIP</b>, then click
              <b>Import ZIP</b>.
            </p>

            <h3>Step 3.</h3>
            <p>
              In KiCad, place the symbol from your configured symbol library.
              The footprint is assigned automatically by the importer.
            </p>

            <h2>KiCad 10 behavior</h2>

            <p>
              KiCad 10 can keep project symbol and footprint library tables
              loaded in memory while the project is open. If this app creates a
              brand-new library while KiCad is already open, KiCad may not show
              that library or its footprints until KiCad is closed and opened
              again.
            </p>

            <p>
              This is why the first-use setup should be done with KiCad closed.
              After the library already exists and KiCad has loaded it, new
              imported components are added into the same library and should not
              require closing KiCad every time.
            </p>

            <h2>Legend</h2>

            <h3>Configuration tab</h3>
            <ul>
              <li><b>KiCad project root</b>: folder that contains the project <b>.kicad_pro</b> file.</li>
              <li><b>Downloads/watch folder</b>: folder where you download the component ZIP files.</li>
              <li><b>Main library name</b>: default shared library name used by the app.</li>
              <li><b>Symbol library name</b>: name of the generated <b>.kicad_sym</b> library.</li>
              <li><b>Footprint library name</b>: name of the generated <b>.pretty</b> footprint library.</li>
              <li><b>Automatically import new ZIP files</b>: watches that folder for newly downloaded component ZIP files and imports them automatically.</li>
            </ul>

            <h3>Import ZIP tab</h3>
            <ul>
              <li><b>Component ZIP</b>: selected provider ZIP file to import.</li>
              <li><b>Browse</b>: choose a ZIP manually.</li>
              <li><b>Refresh Downloads</b>: list recent ZIPs from the watch folder.</li>
              <li><b>Use Selected ZIP</b>: copy the selected list entry into the Component ZIP field.</li>
              <li><b>Import ZIP</b>: imports symbols, footprints, 3D models, datasheets, and updates KiCad library tables.</li>
              <li><b>ZIP list</b>: double-click a ZIP to select it quickly.</li>
            </ul>

            <h3>Search tab</h3>
            <ul>
              <li><b>Search text</b>: MPN or component keyword.</li>
              <li><b>Provider</b>: choose <b>All</b> or a single provider.</li>
              <li><b>Search</b>: builds provider search links.</li>
              <li><b>Open Selected</b>: opens the highlighted result.</li>
              <li><b>Open Results</b>: opens all results currently shown in the list.</li>
            </ul>

            <h3>Notes</h3>
            <ul>
              <li>The app always creates backups before changing project library files.</li>
              <li>Auto import waits a short built-in moment for a ZIP file to finish downloading before importing it.</li>
              <li>When an import succeeds, the app shows a confirmation popup with the component and library name.</li>
              <li>For first use, configure and save this app before opening KiCad so KiCad loads the project libraries from the start.</li>
              <li>If a KiCad chooser was already open during import, close and reopen only that chooser to refresh its view.</li>
              <li>The app imports libraries. It does not automatically place a new symbol onto the schematic.</li>
            </ul>
            """
        )

        # Add help text
        main_layout.addWidget(help_text)
