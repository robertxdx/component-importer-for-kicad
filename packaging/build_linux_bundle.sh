#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="KiCadComponentImporter"
APP_DISPLAY_NAME="KiCad Component Importer"
APP_ID="kicad-component-importer"
PYTHON_BIN="${PYTHON:-python3}"
BUILD_STAMP="$(date +%Y%m%d_%H%M%S)"
ARCH="$(uname -m)"

TEMP_ROOT="${TMPDIR:-/tmp}/KiCadComponentImporterBuild/${BUILD_STAMP}"
FINAL_ARTIFACT_ROOT="${ROOT}/release_builds/${BUILD_STAMP}"
DIST_DIR="${TEMP_ROOT}/dist"
BUILD_DIR="${TEMP_ROOT}/build"
SPEC_DIR="${FINAL_ARTIFACT_ROOT}/spec"
SOURCE_DIR="${DIST_DIR}/${APP_NAME}"
SRC_ROOT="${ROOT}/src"
PACKAGE_DIR="${SRC_ROOT}/component_importer"
GUI_ASSETS_DIR="${PACKAGE_DIR}/gui_assets"
APP_ICON_PATH="${GUI_ASSETS_DIR}/app_icon.png"
ENTRY_POINT="${PACKAGE_DIR}/gui_main.py"
ARCHIVE_PATH="${FINAL_ARTIFACT_ROOT}/${APP_NAME}-linux-${ARCH}.tar.gz"

mkdir -p "${FINAL_ARTIFACT_ROOT}" "${SPEC_DIR}"

cd "${ROOT}"

"${PYTHON_BIN}" -m PyInstaller \
    --noconfirm \
    --clean \
    --windowed \
    --onedir \
    --name "${APP_NAME}" \
    --distpath "${DIST_DIR}" \
    --workpath "${BUILD_DIR}" \
    --specpath "${SPEC_DIR}" \
    --paths "${SRC_ROOT}" \
    --icon "${APP_ICON_PATH}" \
    --add-data "${GUI_ASSETS_DIR}:gui_assets" \
    "${ENTRY_POINT}"

if [[ ! -x "${SOURCE_DIR}/${APP_NAME}" ]]; then
    echo "PyInstaller build did not create ${SOURCE_DIR}/${APP_NAME}" >&2
    exit 1
fi

"${SOURCE_DIR}/${APP_NAME}" --self-test

cp "${APP_ICON_PATH}" "${SOURCE_DIR}/app_icon.png"

cat > "${SOURCE_DIR}/run.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail

APP_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
exec "\${APP_DIR}/${APP_NAME}" "\$@"
EOF

chmod +x "${SOURCE_DIR}/run.sh"

cat > "${SOURCE_DIR}/install_desktop_entry.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail

APP_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
APPLICATIONS_DIR="\${HOME}/.local/share/applications"
ICON_DIR="\${HOME}/.local/share/icons/hicolor/256x256/apps"
DESKTOP_FILE="\${APPLICATIONS_DIR}/${APP_ID}.desktop"
ICON_FILE="\${ICON_DIR}/${APP_ID}.png"

mkdir -p "\${APPLICATIONS_DIR}" "\${ICON_DIR}"
cp "\${APP_DIR}/app_icon.png" "\${ICON_FILE}"

cat > "\${DESKTOP_FILE}" <<DESKTOP
[Desktop Entry]
Type=Application
Name=${APP_DISPLAY_NAME}
Exec=\${APP_DIR}/${APP_NAME}
Icon=${APP_ID}
Categories=Development;Electronics;
Terminal=false
StartupNotify=true
DESKTOP

chmod +x "\${DESKTOP_FILE}"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "\${APPLICATIONS_DIR}" >/dev/null 2>&1 || true
fi

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache "\${HOME}/.local/share/icons/hicolor" >/dev/null 2>&1 || true
fi

echo "Installed desktop entry: \${DESKTOP_FILE}"
EOF

chmod +x "${SOURCE_DIR}/install_desktop_entry.sh"

tar -C "${DIST_DIR}" -czf "${ARCHIVE_PATH}" "${APP_NAME}"

echo "Built app folder: ${SOURCE_DIR}"
echo "Built archive: ${ARCHIVE_PATH}"
