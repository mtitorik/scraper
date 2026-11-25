import os
import sys
import shutil
import asyncio
import subprocess
from pathlib import Path
from typing import Optional, Dict, Tuple, List, Callable, Any

from playwright.async_api import async_playwright, Playwright, Browser, BrowserContext, Page


class BrowserManager:
    """Manages Chromium-based browser detection, Playwright launching in visible Incognito mode,
    RAM-based context recycling, and 1-click built-in Chromium installation.
    """

    def __init__(self, mode: str = "auto", custom_path: str = "", block_trackers: bool = True):
        self.mode = mode  # "auto", "chrome", "msedge", "brave", "bundled", "custom"
        self.custom_path = custom_path
        self.block_trackers = block_trackers
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._active_page: Optional[Page] = None

    @staticmethod
    def get_known_browser_paths() -> Dict[str, List[str]]:
        """Returns default binary paths for major Chromium browsers per OS."""
        if sys.platform == "darwin":
            return {
                "chrome": ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"],
                "msedge": ["/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"],
                "brave": ["/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"],
            }
        elif sys.platform == "win32":
            local_app = os.environ.get("LOCALAPPDATA", "")
            prog_files = os.environ.get("ProgramFiles", "C:\\Program Files")
            prog_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
            return {
                "chrome": [
                    os.path.join(prog_files, "Google", "Chrome", "Application", "chrome.exe"),
                    os.path.join(prog_files_x86, "Google", "Chrome", "Application", "chrome.exe"),
                    os.path.join(local_app, "Google", "Chrome", "Application", "chrome.exe"),
                ],
                "msedge": [
                    os.path.join(prog_files, "Microsoft", "Edge", "Application", "msedge.exe"),
                    os.path.join(prog_files_x86, "Microsoft", "Edge", "Application", "msedge.exe"),
                    os.path.join(local_app, "Microsoft", "Edge", "Application", "msedge.exe"),
                ],
                "brave": [
                    os.path.join(prog_files, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
                    os.path.join(local_app, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
                ],
            }
        else:
            return {
                "chrome": ["/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium-browser", "/usr/bin/chromium"],
                "msedge": ["/usr/bin/microsoft-edge", "/usr/bin/microsoft-edge-stable"],
                "brave": ["/usr/bin/brave-browser", "/usr/bin/brave"],
            }

    @classmethod
    def detect_installed_browsers(cls) -> Dict[str, Optional[str]]:
        """Checks filesystem for installed Chrome, Edge, and Brave."""
        paths = cls.get_known_browser_paths()
        result: Dict[str, Optional[str]] = {}
        for browser_name, candidates in paths.items():
            found = None
            for p in candidates:
                if os.path.isfile(p):
                    found = p
                    break
            if not found:
                # Also try PATH lookup
                bin_name = "google-chrome" if browser_name == "chrome" else ("msedge" if browser_name == "msedge" else "brave")
                found_in_path = shutil.which(bin_name)
                if found_in_path:
                    found = found_in_path
            result[browser_name] = found
        return result

    def resolve_browser_target(self) -> Tuple[Optional[str], Optional[str]]:
        """Resolves (executable_path, channel) based on selected mode.
        Returns:
            (executable_path, None) or (None, channel) or (None, None) for bundled chromium.
        """
        detected = self.detect_installed_browsers()

        if self.mode == "custom" and self.custom_path and os.path.isfile(self.custom_path):
            return self.custom_path, None

        if self.mode == "chrome":
            if detected.get("chrome"):
                return detected["chrome"], None
            return None, "chrome"

        if self.mode == "msedge":
            if detected.get("msedge"):
                return detected["msedge"], None
            return None, "msedge"

        if self.mode == "brave":
            if detected.get("brave"):
                return detected["brave"], None

        if self.mode == "bundled":
            return None, None

        # Auto-detect priority: Chrome -> Edge -> Brave -> Bundled
        if detected.get("chrome"):
            return detected["chrome"], None
        if detected.get("msedge"):
            return detected["msedge"], None
        if detected.get("brave"):
            return detected["brave"], None

        # Fallback to Playwright's bundled or channel
        return None, None

    async def start(self) -> Page:
        """Launches visible Incognito Chromium browser and opens an initial page."""
        if self._active_page and not self._active_page.is_closed():
            return self._active_page

        self._playwright = await async_playwright().start()
        exec_path, channel = self.resolve_browser_target()

        launch_kwargs: Dict[str, Any] = {
            "headless": False,  # Always-visible Incognito browser!
            "args": [
                "--no-default-browser-check",
                "--no-first-run",
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
            ],
        }

        if exec_path:
            launch_kwargs["executable_path"] = exec_path
        elif channel:
            launch_kwargs["channel"] = channel

        try:
            self._browser = await self._playwright.chromium.launch(**launch_kwargs)
        except Exception as e:
            # If launch with specific channel failed, fallback to bundled chromium
            print(f"[BrowserManager] Direct launch failed ({e}), falling back to bundled chromium...")
            launch_kwargs.pop("executable_path", None)
            launch_kwargs.pop("channel", None)
            self._browser = await self._playwright.chromium.launch(**launch_kwargs)

        self._context = await self._create_incognito_context()
        self._active_page = await self._context.new_page()
        return self._active_page

    TRACKER_DOMAINS = (
        "googletagmanager.com",
        "google-analytics.com",
        "doubleclick.net",
        "connect.facebook.net",
        "facebook.com/tr",
        "analytics.tiktok.com",
        "static.hotjar.com",
        "clarity.ms",
        "embed.tawk.to",
        "client.crisp.chat",
        "widget.intercom.io",
        "cdn.onesignal.com",
    )

    async def _create_incognito_context(self) -> BrowserContext:
        """Creates a fresh, isolated incognito context with non-essential 3rd-party tracker blocking."""
        context = await self._browser.new_context(
            viewport={"width": 1366, "height": 860},
            ignore_https_errors=True,
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        )
        if self.block_trackers:
            # Abort known 3rd-party analytics/chat pixels so pages settle much faster without touching site logic/images
            async def _route_filter(route):
                url_lower = route.request.url.lower()
                if any(d in url_lower for d in self.TRACKER_DOMAINS):
                    await route.abort()
                else:
                    await route.continue_()

            await context.route("**/*", _route_filter)
        return context

    async def recycle_context(self) -> Page:
        """Cleanly closes current context and opens a fresh one to release RAM cache."""
        print("[BrowserManager] Recycling browser context to free RAM...")
        if self._context:
            try:
                await self._context.close()
            except Exception as e:
                print(f"[BrowserManager] Warning closing context: {e}")
        self._context = await self._create_incognito_context()
        self._active_page = await self._context.new_page()
        return self._active_page

    async def get_page(self) -> Page:
        if not self._active_page or self._active_page.is_closed():
            return await self.start()
        return self._active_page

    async def stop(self):
        """Cleanly closes context, browser, and playwright."""
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None
            self._active_page = None

        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    @classmethod
    def install_bundled_chromium(cls, progress_callback: Optional[Callable[[str], None]] = None) -> bool:
        """Installs Playwright bundled chromium via subprocess, streaming output to callback."""
        cmd = [sys.executable, "-m", "playwright", "install", "chromium"]
        if progress_callback:
            progress_callback("Starting Playwright Chromium download...")
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for line in proc.stdout:
                line_str = line.strip()
                if line_str and progress_callback:
                    progress_callback(line_str)
            proc.wait()
            return proc.returncode == 0
        except Exception as e:
            if progress_callback:
                progress_callback(f"Installation error: {e}")
            return False
