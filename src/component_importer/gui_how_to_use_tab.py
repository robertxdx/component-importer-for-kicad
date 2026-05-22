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
              Input your downloads folder path, name your library, check or
              uncheck <b>Automatically import new ZIP files</b>, optionally
              check <b>Start automatically on login</b>, then click
              <b>Save Configuration</b>. After this is saved once, the app uses
              that configuration automatically on startup. Click
              <b>Save Configuration</b> again only when you change the project
              root, downloads folder, library name, or checkboxes.
            </p>

            <h3>Step 5.</h3>
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
              Import the ZIP. Click a ZIP entry in the Import ZIP tab to put it
              in the <b>Component ZIP</b> box, then click <b>Import ZIP</b>.
            </p>

            <h3>Step 3.</h3>
            <p>
              In KiCad, place the symbol from your configured symbol library.
              The footprint is assigned automatically by the importer.
            </p>

            <h2>Automatic import</h2>

            <p>
              When <b>Automatically import new ZIP files</b> is checked and
              saved, keep this app running. Minimize the app or press
              <b>X</b> to send it to the tray. To close the app fully,
              right-click the tray icon and choose <b>Exit</b>.
              While the app is running in the tray, it watches the configured
              downloads folder for new ZIP files.
            </p>

            <p>
              When a new ZIP appears, the app waits briefly for the download to
              finish, names the component from the ZIP filename, imports it into
              the configured library, creates backups, and shows a confirmation
              popup when the import finishes.
            </p>

            <p>
              If the same component is already present in the configured
              library, the app skips the import so duplicate KiCad entries are
              not created.
            </p>

            <p>
              If you change the <b>Library name</b>, the app creates or reuses
              the matching project library for that name. If you switch back to
              an older library name, new components are imported alongside the
              components already stored in that older library.
            </p>

            <p>
              When automatic import is unchecked, use the <b>Import ZIP</b> tab
              to import ZIP files manually.
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
              <li><b>Library name</b>: shared name used for the generated <b>.kicad_sym</b> and <b>.pretty</b> libraries.</li>
              <li><b>Automatically import new ZIP files</b>: watches the downloads folder while the app is running and imports new ZIP files after they finish downloading.</li>
              <li><b>Start automatically on login</b>: starts this app when you log in and opens it minimized to the tray when a system tray is available.</li>
            </ul>

            <h3>Import ZIP tab</h3>
            <ul>
              <li><b>Component ZIP</b>: selected provider ZIP file to import.</li>
              <li><b>Browse</b>: choose a ZIP manually.</li>
              <li><b>Import ZIP</b>: imports symbols, footprints, 3D models, datasheets, and updates KiCad library tables.</li>
              <li><b>ZIP list</b>: updates when the watch folder changes; click a ZIP to copy it into the Component ZIP field.</li>
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
              <li>Already imported components are skipped to avoid duplicate KiCad entries.</li>
              <li>For automatic import, minimize the app or press <b>X</b> to keep it running in the tray. To stop the app, right-click the tray icon and choose <b>Exit</b>.</li>
              <li>When an import succeeds, the app shows a confirmation popup with the component and library name.</li>
              <li>Saved configuration is loaded automatically when the app starts. Save again only after changing configuration values.</li>
              <li>For first use, configure and save this app before opening KiCad so KiCad loads the project libraries from the start.</li>
              <li>If a KiCad chooser was already open during import, close and reopen only that chooser to refresh its view.</li>
              <li>The app imports libraries. It does not automatically place a new symbol onto the schematic.</li>
            </ul>
            """
        )

        # Add help text
        main_layout.addWidget(help_text)
