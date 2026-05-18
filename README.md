# Component Importer for KiCad

An open source Windows app for importing downloaded component ZIP libraries into KiCad projects.

<p align="center">
  <img src="docs/assets/importer.png" alt="Component Importer for KiCad configuration tab" width="900">
</p>

[Download the latest Windows installer](https://github.com/robertxdx/component-importer-for-kicad/releases/latest/download/KiCadComponentImporter_Setup.exe)

Support the project: [Buy me a coffee](https://buy.stripe.com/cNieVeg1c7xbalm0CEdnW00)

## What It Does

Component Importer for KiCad helps keep third-party component ZIPs organized inside a KiCad project. It can import symbols, footprints, 3D models, datasheets, and metadata into project-local libraries, then register those libraries with the project.

It is designed for workflows where you download component ZIP files from CAD/library providers and want them merged into one clean project component library.

## Features

- Imports component ZIP files into project-local KiCad libraries.
- Creates and registers symbol and footprint libraries for the project.
- Copies 3D models, datasheets, source ZIPs, and metadata into organized folders.
- Links imported symbols to their imported footprints automatically.
- Watches a downloads folder and can auto-import new component ZIP files.
- Provides provider search links from inside the app.
- Shows simple import confirmations and keeps detailed file backups automatically.

## Download

For normal users, use the installer from the latest GitHub release:

[Download KiCadComponentImporter_Setup.exe](https://github.com/robertxdx/component-importer-for-kicad/releases/latest/download/KiCadComponentImporter_Setup.exe)

## First Use With KiCad 10

KiCad 10 can keep project library tables loaded in memory while a project is open. For the first setup, do this:

1. Create or open your KiCad project once so the project folder exists.
2. Close KiCad fully, including the project window, schematic editor, and PCB editor.
3. Open Component Importer for KiCad.
4. In the Configuration tab, select the KiCad project root folder.
5. Name your components library.
6. Select the folder where you download component ZIP files.
7. Save the configuration.
8. Open KiCad again and start importing components.

After the project library already exists and KiCad has loaded it, importing new parts into that same library should not require closing KiCad every time.

## Build From Source

Requirements:

- Windows
- Python 3.14 or newer
- PyQt6
- PyInstaller
- Inno Setup 6, only needed to build the installer

Install Python dependencies:

```powershell
python -m pip install -r requirements.txt
```

Run the app from source:

```powershell
python gui_main.py
```

Build the Windows installer:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_windows_installer.ps1
```

The installer is written to `release_builds/<timestamp>/KiCadComponentImporter_Setup.exe`.

## Notes

This is an independent open source project. It is not affiliated with, endorsed by, or maintained by the KiCad project.

KiCad and related names belong to their respective owners.

## License

MIT License. See [LICENSE](LICENSE).
