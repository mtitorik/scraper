import os
import sys
import json
import asyncio
import threading
import subprocess
import webbrowser
from pathlib import Path
from typing import Dict, Any, Optional, List

import webview

from ..config.settings import SettingsManager, AppSettings
from ..core.orchestrator import ScraperOrchestrator
from ..browser.browser_manager import BrowserManager
from ..core.resource_guard import ResourceGuard


class ScraperBridge:
    """JS-to-Python bridge for PyWebView. Exposes native OS file dialogs,
    scraping queue controls, live settings, and pushes real-time events to the UI.
    """

    def __init__(self, settings_manager: SettingsManager):
        self.settings_manager = settings_manager
        self.window: Optional[webview.Window] = None
        self.orchestrator: Optional[ScraperOrchestrator] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.worker_thread: Optional[threading.Thread] = None

    def set_window(self, window: webview.Window):
        self.window = window

    def _dispatch_js_event(self, event_type: str, payload: Any):
        """Pushes an asynchronous event into the PyWebView frontend."""
        if not self.window:
            return
        event_obj = {"type": event_type, "payload": payload}
        js_code = f"if (window.onBackendEvent) window.onBackendEvent({json.dumps(event_obj)});"
        try:
            self.window.evaluate_js(js_code)
        except Exception:
            pass

    # --- Settings Management ---
    def get_settings(self) -> Dict[str, Any]:
        return self.settings_manager.settings.to_dict()

    def save_settings(self, data: Dict[str, Any]) -> bool:
        new_settings = AppSettings.from_dict(data)
        success = self.settings_manager.save(new_settings)
        if success and self.orchestrator:
            self.orchestrator.update_settings(new_settings)
        return success

    # --- Native OS Dialogs ---
    def pick_input_file(self) -> Optional[str]:
        if not self.window:
            return None
        dialog_type = getattr(getattr(webview, "FileDialog", None), "OPEN", webview.OPEN_DIALOG)
        res = self.window.create_file_dialog(
            dialog_type,
            file_types=("Excel Files (*.xlsx)",),
        )
        return res[0] if res else None

    def pick_output_file(self) -> Optional[str]:
        if not self.window:
            return None
        dialog_type = getattr(getattr(webview, "FileDialog", None), "SAVE", webview.SAVE_DIALOG)
        res = self.window.create_file_dialog(
            dialog_type,
            file_types=("Excel Files (*.xlsx)",),
            save_filename="scraper_output.xlsx",
        )
        return res if isinstance(res, str) else (res[0] if res else None)

    def pick_resume_file(self) -> Optional[str]:
        if not self.window:
            return None
        dialog_type = getattr(getattr(webview, "FileDialog", None), "OPEN", webview.OPEN_DIALOG)
        res = self.window.create_file_dialog(
            dialog_type,
            file_types=("Excel Files (*.xlsx)",),
        )
        return res[0] if res else None

    def pick_folder(self) -> Optional[str]:
        if not self.window:
            return None
        dialog_type = getattr(getattr(webview, "FileDialog", None), "FOLDER", webview.FOLDER_DIALOG)
        res = self.window.create_file_dialog(dialog_type)
        return res[0] if res else None

    def open_external_url(self, url: str) -> bool:
        """Opens an http/https URL in the user's default system browser."""
        if not url:
            return False
        clean_url = url.strip()
        if not (clean_url.startswith("http://") or clean_url.startswith("https://")):
            return False
        try:
            webbrowser.open(clean_url, new=2)
            return True
        except Exception as e:
            print(f"[Bridge] Error opening URL {clean_url}: {e}")
            return False

    def open_local_path(self, file_or_folder_path: str) -> bool:
        """Opens a local file or directory using the OS default application."""
        if not file_or_folder_path or not os.path.exists(file_or_folder_path):
            return False
        try:
            if sys.platform == "win32":
                os.startfile(file_or_folder_path)
            elif sys.platform == "darwin":
                subprocess.run(["open", file_or_folder_path], check=False)
            else:
                subprocess.run(["xdg-open", file_or_folder_path], check=False)
            return True
        except Exception as e:
            print(f"[Bridge] Error opening path: {e}")
            return False

    # --- Browser & Resource Tools ---
    def detect_browsers(self) -> Dict[str, Any]:
        return BrowserManager.detect_installed_browsers()

    def install_bundled_chromium(self):
        """Downloads Playwright Chromium in a background thread and streams progress to JS."""
        def run_install():
            def cb(msg):
                self._dispatch_js_event("chromium_install_progress", msg)
            success = BrowserManager.install_bundled_chromium(progress_callback=cb)
            self._dispatch_js_event("chromium_install_done", {"success": success})

        t = threading.Thread(target=run_install, daemon=True)
        t.start()
        return True

    def get_live_resources(self) -> Dict[str, Any]:
        if self.orchestrator and self.orchestrator.resource_guard:
            return self.orchestrator.resource_guard.get_live_metrics()
        rg = ResourceGuard(
            max_cores=self.settings_manager.settings.max_cpu_cores,
            max_cpu_percent=self.settings_manager.settings.max_cpu_percent,
            max_ram_gb=self.settings_manager.settings.max_ram_gb,
        )
        return rg.get_live_metrics()

    # --- Live Table Data ---
    def get_current_table_data(self) -> Dict[str, Any]:
        if not self.orchestrator or not self.orchestrator.workbook_manager:
            return {"products": [], "variants": []}
        wb = self.orchestrator.workbook_manager
        products = [r.to_summary_dict() for r in wb.get_all_records()]
        variants = []
        for r in wb.get_all_records():
            for v in r.variant_combinations:
                variants.append(v.to_row_dict())
        return {"products": products, "variants": variants}

    def get_product_detail(self, product_name: str) -> Optional[Dict[str, Any]]:
        if not self.orchestrator or not self.orchestrator.workbook_manager:
            return None
        rec = self.orchestrator.workbook_manager.get_record(product_name)
        return rec.to_detail_dict() if rec else None

    # --- Scraping Queue Controls ---
    def start_scraping(
        self,
        input_path: Optional[str],
        output_path: str,
        root_folder: str,
        resume_path: Optional[str] = None,
        manual_products: Optional[List[str]] = None,
    ):
        if self.orchestrator and self.orchestrator.is_running:
            return False

        def orchestrator_thread_entry():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

            self.orchestrator = ScraperOrchestrator(
                settings=self.settings_manager.settings,
                on_log=lambda msg: self._dispatch_js_event("log", msg),
                on_progress=lambda p: self._dispatch_js_event("progress", p),
                on_row_updated=lambda r: self._dispatch_js_event("row_updated", r),
                on_captcha_alert=lambda u: self._dispatch_js_event("captcha_alert", u),
                on_status_change=lambda s: self._dispatch_js_event("status_change", s),
            )

            try:
                self.loop.run_until_complete(
                    self.orchestrator.run(
                        input_xlsx_path=input_path,
                        output_xlsx_path=output_path,
                        root_image_folder=root_folder,
                        resume_xlsx_path=resume_path,
                        manual_products=manual_products,
                    )
                )
            except Exception as e:
                self._dispatch_js_event("log", f"Thread error: {e}")
            finally:
                self.loop.close()

        self.worker_thread = threading.Thread(target=orchestrator_thread_entry, daemon=True)
        self.worker_thread.start()
        return True

    def pause_scraping(self):
        if self.orchestrator:
            self.orchestrator.pause()
            return True
        return False

    def resume_scraping(self):
        if self.orchestrator:
            self.orchestrator.resume()
            return True
        return False

    def stop_scraping(self):
        if self.orchestrator:
            self.orchestrator.stop()
            return True
        return False

    def verify_captcha_done(self):
        if self.orchestrator:
            self.orchestrator.resolve_captcha()
            return True
        return False
