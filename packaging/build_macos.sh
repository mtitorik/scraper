#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Building Scraper for macOS ==="
cd "$ROOT_DIR"

if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Clean previous build artifacts
rm -rf build dist

echo "Running PyInstaller..."
pyinstaller --clean -y packaging/scraper_macos.spec

echo "Creating .dmg / archive..."
cd dist
if command -v hdiutil &>/dev/null; then
    hdiutil create -volname "Scraper" -srcfolder "Scraper.app" -ov -format UDZO "Scraper-macOS.dmg"
    echo "Successfully generated dist/Scraper-macOS.dmg"
else
    zip -r "Scraper-macOS.zip" "Scraper.app"
    echo "Successfully generated dist/Scraper-macOS.zip"
fi

echo "=== Build Complete! ==="
