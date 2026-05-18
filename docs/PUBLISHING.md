# Publishing Guide

This guide is for publishing Component Importer for KiCad on GitHub.

## 1. Push The Source Code

From the project folder:

```powershell
git init
git branch -M main
git add .
git commit -m "Initial public release"
git remote add origin https://github.com/robertxdx/component-importer-for-kicad.git
git push -u origin main
```

If the remote already exists, use:

```powershell
git remote set-url origin https://github.com/robertxdx/component-importer-for-kicad.git
git push -u origin main
```

## 2. Enable GitHub Pages

1. Open the repository on GitHub.
2. Go to Settings.
3. Go to Pages.
4. Under Build and deployment, choose Deploy from a branch.
5. Select branch `main`.
6. Select folder `/docs`.
7. Save.

The page will be available at:

```text
https://robertxdx.github.io/component-importer-for-kicad/
```

## 3. Create The First Release

1. Open the repository on GitHub.
2. Click Releases.
3. Click Draft a new release.
4. Create tag `v0.1.0`.
5. Use release title `v0.1.0`.
6. Upload the installer:

```text
D:\Cloud\Python_projects\component_importer\release_builds\20260518_205706\KiCadComponentImporter_Setup.exe
```

7. Paste the release notes below.
8. Publish the release.

## Release Notes For v0.1.0

First public release of Component Importer for KiCad.

### Download

Use `KiCadComponentImporter_Setup.exe` from the release assets.

### Included

- Windows installer.
- Component ZIP import into project-local KiCad libraries.
- Symbol, footprint, 3D model, datasheet, metadata, and source ZIP handling.
- Automatic footprint link updates for imported symbols.
- Downloads folder watcher for automatic import.
- Search links for common CAD/library providers.

### First Use

For KiCad 10, configure and save the importer before opening KiCad with the target project. KiCad can cache newly created project libraries while a project is already open.
