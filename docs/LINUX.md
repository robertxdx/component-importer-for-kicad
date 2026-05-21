# Linux Support Notes

The first Linux target family is Ubuntu and Ubuntu-based desktops:

- Ubuntu LTS
- Zorin OS
- Pop!_OS
- Linux Mint and other close Ubuntu derivatives should usually work too

## Recommended Release Strategy

Start with a `.tar.gz` PyInstaller bundle built on the oldest Ubuntu LTS version you want to support. A bundle built on an older supported Ubuntu is more likely to run on newer Ubuntu-derived systems than the other way around.

For the current target set, use this order:

1. `.tar.gz` bundle for early testing and GitHub Releases.
2. `.deb` package once the app is stable on Ubuntu/Zorin/Pop.
3. AppImage if users outside the Ubuntu family ask for a single-file portable app.
4. Flatpak if you want the broadest desktop Linux distribution path later.

## Source Run On Ubuntu/Zorin/Pop

Install system basics:

```bash
sudo apt update
sudo apt install python3-venv python3-pip
```

Create an environment and run the app:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[build]"
python -m component_importer.gui_main
```

If Qt reports that the `xcb` platform plugin could not be loaded, install the common Qt/XCB runtime libraries:

```bash
sudo apt install libxcb-cursor0 libxcb-xinerama0 libxkbcommon-x11-0 libegl1 libgl1
```

## Build The Linux Bundle

Build on Linux:

```bash
bash packaging/build_linux_bundle.sh
```

The archive will be written to:

```text
release_builds/<timestamp>/KiCadComponentImporter-linux-<arch>.tar.gz
```

After unpacking the archive, run:

```bash
./run.sh
```

Optionally install a user-level desktop launcher:

```bash
./install_desktop_entry.sh
```

## Compatibility Notes

PyInstaller Linux builds are not true cross-distro binaries. They do not bundle every system library, especially glibc and low-level desktop libraries. Build on the oldest supported distro baseline, then test on newer ones.

For this project, test at minimum:

- Ubuntu LTS with GNOME
- Zorin OS
- Pop!_OS

The app handles missing system tray support by falling back to normal window behavior. This matters on some GNOME/Wayland setups where tray icons are hidden or unsupported.
