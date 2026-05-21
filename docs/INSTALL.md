# Installation Guide

Component Importer for KiCad currently supports Windows and Ubuntu-based Linux distributions.

## Windows

1. Download the latest Windows installer from the GitHub release assets:

```text
KiCadComponentImporter_Setup.exe
```

2. Run the installer.
3. Launch **KiCad Component Importer** from the Start menu.
4. Select your KiCad project folder, downloads/watch folder, and library names in the Configuration tab.

## Linux Bundle

The Linux bundle targets Ubuntu, Zorin OS, Pop!_OS, and close Ubuntu-based distributions.

1. Download the Linux archive from the release assets, when provided:

```text
KiCadComponentImporter-linux-x86_64.tar.gz
```

2. Extract it:

```bash
tar -xzf KiCadComponentImporter-linux-x86_64.tar.gz
cd KiCadComponentImporter
```

3. Run the app:

```bash
./run.sh
```

4. Optionally install a user-level desktop launcher:

```bash
./install_desktop_entry.sh
```

After that, search for **KiCad Component Importer** in your app launcher.

## Linux Source Install

Use this path when testing from the repository.

1. Install basic tools:

```bash
sudo apt update
sudo apt install git python3 python3-venv python3-pip
```

2. Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

3. Install the app:

```bash
python -m pip install -U pip
python -m pip install -e ".[build]"
```

4. Run it:

```bash
python -m component_importer.gui_main
```

If Qt reports that the `xcb` platform plugin could not be loaded, install the common Qt/XCB runtime libraries:

```bash
sudo apt install libxcb-cursor0 libxcb-xinerama0 libxkbcommon-x11-0 libegl1 libgl1
```

## Build The Linux Bundle

From the repository root on Linux:

```bash
bash packaging/build_linux_bundle.sh
```

The archive is written to:

```text
release_builds/<timestamp>/KiCadComponentImporter-linux-<arch>.tar.gz
```

## Update

Windows: install the newer `.exe` release over the old one.

Linux bundle: remove or replace the old extracted `KiCadComponentImporter` folder, then extract the newer archive. If you installed the desktop launcher, run `./install_desktop_entry.sh` again from the new folder.

## Uninstall

Windows: uninstall from Windows Apps & Features.

Linux bundle: delete the extracted `KiCadComponentImporter` folder. If you installed the desktop launcher, remove:

```bash
rm -f ~/.local/share/applications/kicad-component-importer.desktop
rm -f ~/.local/share/icons/hicolor/256x256/apps/kicad-component-importer.png
```
