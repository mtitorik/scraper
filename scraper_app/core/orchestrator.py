import os
import sys
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable

from ..config.settings import AppSettings
from ..models.product_models import ProductRecord, PricePair, OptionPriceEntry, VariantCombination
from ..core.resource_guard import ResourceGuard
from ..browser.browser_manager import BrowserManager
from ..browser.popup_guard import PopupGuard
from ..scraper.site_scraper import SiteScraper
from ..media.image_downloader import ImageDownloader
from ..ai.gemini_engine import GeminiEngine
from ..excel.workbook_manager import WorkbookManager


class ScraperOrchestrator:
    """Coordinates the 6-stage pipeline:
    Waterfall search loop across unlimited priority-ordered websites,
    interactive pause/resume/stop, live Excel updates, Gemini AI processing,
    and automatic RAM context recycling.
    """

    def __init__(
        self,
        settings: AppSettings,
        on_log: Optional[Callable[[str], None]] = None,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_row_updated: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_captcha_alert: Optional[Callable[[str], None]] = None,
        on_status_change: Optional[Callable[[str], None]] = None,
    ):
        self.settings = settings
        self.on_log = on_log or (lambda m: print(f"[Orchestrator] {m}"))
        self.on_progress = on_progress or (lambda p: None)
        self.on_row_updated = on_row_updated or (lambda r: None)
        self.on_captcha_alert = on_captcha_alert or (lambda u: None)
        self.on_status_change = on_status_change or (lambda s: None)

        self.resource_guard = ResourceGuard(
            max_cores=settings.max_cpu_cores,
            max_cpu_percent=settings.max_cpu_percent,
            max_ram_gb=settings.max_ram_gb,
        )
        self.browser_manager = BrowserManager(
            mode=settings.browser_mode,
            custom_path=settings.custom_browser_path,
            block_trackers=settings.block_trackers,
        )
        self.gemini_engine = GeminiEngine(settings)
        self.image_downloader: Optional[ImageDownloader] = None
        self.workbook_manager: Optional[WorkbookManager] = None

        self.pause_event = asyncio.Event()
        self.pause_event.set()  # set means running
        self.stop_event = asyncio.Event()
        self.captcha_event = asyncio.Event()
        self.captcha_event.set()  # set means no active captcha

        self.is_running = False
        self.is_paused = False

    def update_settings(self, settings: AppSettings):
        self.settings = settings
        self.resource_guard.update_limits(
            max_cores=settings.max_cpu_cores,
            max_cpu_percent=settings.max_cpu_percent,
            max_ram_gb=settings.max_ram_gb,
        )
        self.gemini_engine.update_settings(settings)
        if self.image_downloader and settings.root_image_folder:
            self.image_downloader = ImageDownloader(settings.root_image_folder)

    def pause(self):
        """Thread-safe pause request."""
        if self.is_running and not self.is_paused:
            self.is_paused = True
            self.pause_event.clear()
            self.on_status_change("Paused")
            self.on_log("Execution paused cleanly at checkpoint.")

    def resume(self):
        """Thread-safe resume request."""
        if self.is_running and self.is_paused:
            self.is_paused = False
            self.pause_event.set()
            self.on_status_change("Running")
            self.on_log("Execution resumed.")

    def stop(self):
        """Thread-safe stop request."""
        if self.is_running:
            self.stop_event.set()
            self.pause_event.set()  # unblock if paused
            self.captcha_event.set()  # unblock if waiting for captcha
            self.on_status_change("Stopping")
            self.on_log("Stopping scraping queue...")

    def resolve_captcha(self):
        """Called when user confirms they solved the on-screen CAPTCHA."""
        self.captcha_event.set()
        self.on_log("User confirmed CAPTCHA verification. Continuing...")

    def _is_row_complete(self, record: ProductRecord) -> bool:
        """Determines if a product has all essential information so further websites can be skipped."""
        has_price = record.default_price.regular is not None and record.default_price.regular > 0
        has_specs = bool(record.specifications and record.specifications != "not found")
        has_images = (not self.settings.download_images) or bool(record.image_folder and os.path.exists(record.image_folder))

        if not (has_price and has_specs and has_images):
            return False

        # Option C check: if search_missing_official_unofficial_pair is enabled
        if self.settings.search_missing_official_unofficial_pair:
            # Check if this product has official/unofficial variants recorded
            off_unoff_entries = record.attribute_options.get("official/unofficial", [])
            has_official = any(e.label.lower() == "official" for e in off_unoff_entries)
            has_unofficial = any(e.label.lower() == "unofficial" for e in off_unoff_entries)

            # If it has only one of the pair, it is NOT complete yet
            if (has_official and not has_unofficial) or (has_unofficial and not has_official):
                return False

        return True

    async def run(
        self,
        input_xlsx_path: Optional[str],
        output_xlsx_path: str,
        root_image_folder: str,
        resume_xlsx_path: Optional[str] = None,
        manual_products: Optional[List[str]] = None,
    ):
        """Main scraping execution loop."""
        self.is_running = True
        self.is_paused = False
        self.stop_event.clear()
        self.pause_event.set()
        self.captcha_event.set()
        self.on_status_change("Running")

        self.image_downloader = ImageDownloader(root_image_folder)
        websites = [w.strip() for w in self.settings.websites if w.strip()]

        if not websites:
            self.on_log("Error: No website URLs configured. Please add at least one website.")
            self.is_running = False
            self.on_status_change("Idle")
            return

        try:
            # Step 1: Initialize WorkbookManager
            if resume_xlsx_path and os.path.exists(resume_xlsx_path):
                self.on_log(f"Resuming from existing output file: {Path(resume_xlsx_path).name}")
                self.workbook_manager = WorkbookManager.load_for_resume(resume_xlsx_path)
                self.workbook_manager.output_path = Path(output_xlsx_path).resolve()
            elif manual_products and len(manual_products) > 0:
                clean_names = [p.strip() for p in manual_products if p.strip()]
                self.on_log(f"Initializing {len(clean_names)} manual products into queue...")
                self.workbook_manager = WorkbookManager(output_xlsx_path)
                self.workbook_manager.initialize_from_input_names(clean_names)
            else:
                if not input_xlsx_path or not os.path.exists(input_xlsx_path):
                    self.on_log("Error: No valid input .xlsx file provided.")
                    self.is_running = False
                    self.on_status_change("Error")
                    return
                self.on_log(f"Reading product names from input file: {Path(input_xlsx_path).name}")
                product_names = WorkbookManager.read_input_product_names(input_xlsx_path)
                self.workbook_manager = WorkbookManager(output_xlsx_path)
                self.workbook_manager.initialize_from_input_names(product_names)

            # Immediately save the initial workbook file so user can inspect it right away!
            self.workbook_manager.save_workbook()
            self.on_log(f"Output .xlsx created immediately at {Path(output_xlsx_path).name}")

            # Notify initial state of all rows to UI
            for rec in self.workbook_manager.get_all_records():
                self.on_row_updated(rec.to_summary_dict())

            records_to_process = [
                rec for rec in self.workbook_manager.get_all_records()
                if rec.status in ("Pending", "In Progress", "Partial")
            ]
            total_count = len(self.workbook_manager.get_all_records())
            self.on_log(f"Total products: {total_count}. Pending to process: {len(records_to_process)}")

            # Step 2: Start visible Incognito browser
            self.on_log(f"Launching visible Incognito browser ({self.settings.browser_mode})...")
            page = await self.browser_manager.start()

            # Step 3: Website-First Waterfall Loop
            # Pass 1: Search Website 1 for ALL pending/incomplete products
            # Pass 2: Search Website 2 ONLY for products still missing or incomplete
            # Pass N: Repeat sequentially; stop early as soon as all products are complete!
            for site_idx, site_url in enumerate(websites, start=1):
                if self.stop_event.is_set():
                    self.on_log("Stop requested. Exiting queue...")
                    break

                pending_for_pass = [
                    rec for rec in self.workbook_manager.get_all_records()
                    if rec.status in ("Pending", "In Progress", "Partial")
                ]

                if not pending_for_pass:
                    self.on_log("All products are complete! Stopping waterfall early.")
                    break

                self.on_log(f"--- Pass {site_idx}/{len(websites)}: Searching {site_url} for {len(pending_for_pass)} pending product(s) ---")

                for pass_idx, record in enumerate(pending_for_pass, start=1):
                    if self.stop_event.is_set():
                        self.on_log("Stop requested. Exiting queue...")
                        break

                    if not self.pause_event.is_set():
                        self.on_log(f"Paused before processing '{record.product_name}'...")
                        await self.pause_event.wait()

                    await self.resource_guard.throttle_if_needed()

                    done_so_far = sum(1 for r in self.workbook_manager.get_all_records() if r.status == "Done")
                    record.status = "In Progress"
                    self.workbook_manager.update_record(record)
                    self.on_row_updated(record.to_summary_dict())

                    self.on_progress({
                        "current": done_so_far,
                        "total": total_count,
                        "product_name": record.product_name,
                        "site": site_url,
                        "stage": f"Pass {site_idx}/{len(websites)} ({pass_idx}/{len(pending_for_pass)})",
                    })
                    self.on_log(f"[Pass {site_idx} • {pass_idx}/{len(pending_for_pass)}] Searching '{record.product_name}' on {site_url}...")

                    custom_excludes = [
                        k.strip().lower()
                        for k in (self.settings.custom_exclude_keywords or "").split(",")
                        if k.strip()
                    ]

                    page_timeout_ms = max(10, int(self.settings.page_timeout_sec or 25)) * 1000
                    candidates = await SiteScraper.search_product(
                        page=page,
                        site_url=site_url,
                        product_name=record.product_name,
                        skip_preowned=self.settings.skip_preowned_devices,
                        skip_accessories=self.settings.skip_accessories,
                        strict_model_matching=self.settings.strict_model_matching,
                        enable_fallback_sku_search=self.settings.enable_fallback_sku_search,
                        custom_excludes=custom_excludes,
                        page_timeout_ms=page_timeout_ms,
                    )

                    if await PopupGuard.detect_human_verification(page):
                        self.on_log(f"Human verification challenge detected on {site_url}! Pausing for user...")
                        self.on_captcha_alert(site_url)
                        self.captcha_event.clear()
                        await self.captcha_event.wait()

                    if not candidates:
                        self.on_log(f"No match for '{record.product_name}' on {site_url}")
                        # Keep Pending/Partial so next website pass checks it
                        record.status = "Partial" if record.scraped_sources else "Pending"
                        self.workbook_manager.update_record(record)
                        self.on_row_updated(record.to_summary_dict())
                        continue

                    if site_url not in record.scraped_sources:
                        record.scraped_sources.append(site_url)

                    for cand in candidates:
                        cand_url = cand["url"]
                        self.on_log(f"Scraping product page: {cand_url}")
                        record.add_page_link(cand_url)

                        page_data = await SiteScraper.scrape_product_page(
                            page=page,
                            page_url=cand_url,
                            target_product_name=record.product_name,
                            source_website=site_url,
                            pause_event=self.pause_event,
                            stop_event=self.stop_event,
                            throttle_callback=self.resource_guard.throttle_if_needed,
                            scrape_variants=self.settings.scrape_variants,
                            page_timeout_ms=page_timeout_ms,
                        )

                        # Merge prices
                        if page_data["default_price"].regular:
                            if not record.default_price.regular or record.default_price.regular == 0:
                                record.default_price = page_data["default_price"]

                        # Merge attribute options
                        for cat, entries in page_data["attribute_options"].items():
                            if cat not in record.attribute_options:
                                record.attribute_options[cat] = []
                            for entry in entries:
                                if not any(x.label == entry.label for x in record.attribute_options[cat]):
                                    record.attribute_options[cat].append(entry)

                        # Merge variant combinations for Sheet 2
                        for combo in page_data["variant_combinations"]:
                            record.variant_combinations.append(combo)

                        # Merge specifications
                        if page_data["specifications"] != "not found":
                            if record.specifications == "not found":
                                record.specifications = page_data["specifications"]
                            else:
                                record.specifications += f"\n\n{page_data['specifications']}"

                        # Merge warranty
                        if page_data["warranty"] and "Warranty" not in record.extra_fields:
                            record.extra_fields["Warranty"] = page_data["warranty"]

                        # Download and convert images (when enabled in Matching & Filtering Rules)
                        if self.settings.download_images and page_data["image_urls"]:
                            img_urls = page_data["image_urls"]
                            max_imgs = int(self.settings.max_images_per_product or 0)
                            if max_imgs > 0:
                                img_urls = img_urls[:max_imgs]
                            folder, saved_imgs = self.image_downloader.download_product_images(
                                product_name=record.product_name,
                                image_urls=img_urls,
                            )
                            record.image_folder = folder

                        # Run Gemini AI processing
                        clean_specs, clean_desc = await self.gemini_engine.process_product_content(
                            product_name=record.product_name,
                            raw_description=page_data["raw_description"],
                            specifications=record.specifications,
                            is_found=True,
                        )
                        record.specifications = clean_specs
                        record.description_html = clean_desc

                    record.status = "Done" if self._is_row_complete(record) else "Partial"
                    self.workbook_manager.update_record(record)
                    self.workbook_manager.save_workbook()
                    self.on_row_updated(record.to_summary_dict())
                    self.on_log(f"Saved '{record.product_name}' -> Status: {record.status}")

                    # Optional politeness delay between products to avoid rate-limiting
                    delay_s = float(self.settings.request_delay_sec or 0.0)
                    if delay_s > 0 and not self.stop_event.is_set():
                        await asyncio.sleep(delay_s)

                    # Check RAM ceiling and recycle browser context if needed
                    if self.resource_guard.should_recycle_browser():
                        self.on_log("RAM ceiling reached (>85%). Recycling Incognito browser context...")
                        page = await self.browser_manager.recycle_context()

            # Finalize any products still unmatched after all website passes
            if not self.stop_event.is_set():
                for rec in self.workbook_manager.get_all_records():
                    if rec.status in ("Pending", "In Progress") and not rec.scraped_sources:
                        rec.status = "Not Found"
                        rec.specifications = "not found"
                        rec.description_html = "not found"
                        self.workbook_manager.update_record(rec)
                        self.on_row_updated(rec.to_summary_dict())
                self.workbook_manager.save_workbook()

            # Finished all records
            self.on_log("Scraping queue complete! All rows saved to Excel.")
            if self.settings.auto_open_excel and os.path.exists(output_xlsx_path):
                try:
                    import subprocess
                    if sys.platform == "win32":
                        os.startfile(output_xlsx_path)
                    elif sys.platform == "darwin":
                        subprocess.Popen(["open", output_xlsx_path])
                    else:
                        subprocess.Popen(["xdg-open", output_xlsx_path])
                except Exception:
                    pass
            self.on_progress({
                "current": total_count,
                "total": total_count,
                "product_name": "Completed",
                "site": "-",
                "stage": "Finished",
            })
            self.on_status_change("Finished")

        except Exception as e:
            self.on_log(f"Critical execution error: {e}")
            import traceback
            traceback.print_exc()
            self.on_status_change("Error")
        finally:
            self.is_running = False
            self.is_paused = False
            await self.browser_manager.stop()
            self.on_log("Browser closed.")
