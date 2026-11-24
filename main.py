#!/usr/bin/env python3
"""Main entry point for Scraper desktop application.
Launches the sleek modern UI in a native PyWebView window.
"""

import os
import sys
from pathlib import Path

# Ensure root directory is on PYTHONPATH
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

import webview
from scraper_app.config.settings import SettingsManager
from scraper_app.ui.bridge import ScraperBridge


def main():
    settings_manager = SettingsManager()
    bridge = ScraperBridge(settings_manager)

    # Path to web UI assets
    web_dir = ROOT_DIR / "scraper_app" / "ui" / "web"
    index_file = web_dir / "index.html"

    if not index_file.exists():
        print(f"Error: UI index file not found at {index_file}")
        sys.exit(1)

    # Create native window
    window = webview.create_window(
        title="Scraper — E-Commerce Intelligence",
        url=str(index_file.resolve()),
        js_api=bridge,
        width=1280,
        height=820,
        min_size=(980, 640),
        background_color="#0f172a",
        text_select=True,
    )
    bridge.set_window(window)

    # Start PyWebView native event loop
    webview.start(debug=False)


if __name__ == "__main__":
    main()
