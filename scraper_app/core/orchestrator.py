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
        self._workbook_lock = asyncio.Lock()

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

            # Step 2: Launch visible Incognito browser & run unified 2-axis wave engine
            # parallel_websites = how many different websites run at once
            # tabs_per_website  = how many tabs each website gets for different products
            parallel_websites = max(1, int(self.settings.parallel_websites or 1))
            tabs_per_website = max(1, int(self.settings.tabs_per_website or 3))

            custom_excludes = [
                k.strip().lower()
                for k in (self.settings.custom_exclude_keywords or "").split(",")
                if k.strip()
            ]
            page_timeout_ms = max(10, int(self.settings.page_timeout_sec or 25)) * 1000
            delay_s = float(self.settings.request_delay_sec or 0.0)

            self.on_log(
                f"Launching visible Incognito browser ({self.settings.browser_mode} · {parallel_websites} website(s) at once × {tabs_per_website} tab(s)/website)..."
            )

            async def _fetch_site_payload(page, site_url: str, product_name: str, worker_tag: str) -> Dict[str, Any]:
                """Searches & scrapes a single website on `page` without mutating shared WorkbookManager state."""
                candidates = await SiteScraper.search_product(
                    page=page,
                    site_url=site_url,
                    product_name=product_name,
                    skip_preowned=self.settings.skip_preowned_devices,
                    skip_accessories=self.settings.skip_accessories,
                    strict_model_matching=self.settings.strict_model_matching,
                    enable_fallback_sku_search=self.settings.enable_fallback_sku_search,
                    custom_excludes=custom_excludes,
                    page_timeout_ms=page_timeout_ms,
                )

                if await PopupGuard.detect_human_verification(page):
                    try:
                        await page.bring_to_front()
                    except Exception:
                        pass
                    self.on_log(f"[{worker_tag}] Human verification challenge detected on {site_url}! Pausing all tabs...")
                    self.on_captcha_alert(site_url)
                    self.captcha_event.clear()
                    await self.captcha_event.wait()

                if not candidates:
                    return {"site_url": site_url, "found": False, "pages": []}

                scraped_pages: List[Dict[str, Any]] = []
                for cand in candidates:
                    if self.stop_event.is_set():
                        break
                    cand_url = cand["url"]
                    self.on_log(f"[{worker_tag}] Scraping: {cand_url}")
                    page_data = await SiteScraper.scrape_product_page(
                        page=page,
                        page_url=cand_url,
                        target_product_name=product_name,
                        source_website=site_url,
                        pause_event=self.pause_event,
                        stop_event=self.stop_event,
                        throttle_callback=self.resource_guard.throttle_if_needed,
                        scrape_variants=self.settings.scrape_variants,
                        page_timeout_ms=page_timeout_ms,
                    )
                    # Offload synchronous HTTP image downloads + Pillow conversion to a worker thread!
                    saved_folder = ""
                    if self.settings.download_images and page_data["image_urls"]:
                        img_urls = page_data["image_urls"]
                        max_imgs = int(self.settings.max_images_per_product or 0)
                        if max_imgs > 0:
                            img_urls = img_urls[:max_imgs]
                        saved_folder, _ = await asyncio.to_thread(
                            self.image_downloader.download_product_images,
                            product_name,
                            img_urls,
                        )
                    page_data["saved_image_folder"] = saved_folder
                    scraped_pages.append(page_data)

                return {"site_url": site_url, "found": bool(scraped_pages), "pages": scraped_pages}

            async def _commit_site_payload(record: ProductRecord, payload: Dict[str, Any], worker_tag: str, site_url: str):
                """Merges scraped data into `record`, runs Gemini AI if enabled, and saves Excel under lock."""
                if payload["found"]:
                    # Run Gemini AI outside the workbook lock so sibling tabs can still save!
                    processed_pages: List[Dict[str, Any]] = []
                    for page_data in payload["pages"]:
                        specs_in = record.specifications
                        if page_data["specifications"] != "not found":
                            specs_in = page_data["specifications"] if specs_in == "not found" else f"{specs_in}\n\n{page_data['specifications']}"
                        clean_specs, clean_desc = await self.gemini_engine.process_product_content(
                            product_name=record.product_name,
                            raw_description=page_data["raw_description"],
                            specifications=specs_in,
                            is_found=True,
                        )
                        page_data["_clean_specs"] = clean_specs
                        page_data["_clean_desc"] = clean_desc
                        processed_pages.append(page_data)

                    async with self._workbook_lock:
                        if site_url not in record.scraped_sources:
                            record.scraped_sources.append(site_url)
                        for page_data in processed_pages:
                            record.add_page_link(page_data["page_url"])
                            if page_data["default_price"].regular:
                                if not record.default_price.regular or record.default_price.regular == 0:
                                    record.default_price = page_data["default_price"]
                            for cat, entries in page_data["attribute_options"].items():
                                if cat not in record.attribute_options:
                                    record.attribute_options[cat] = []
                                for entry in entries:
                                    if not any(x.label == entry.label for x in record.attribute_options[cat]):
                                        record.attribute_options[cat].append(entry)
                            for combo in page_data["variant_combinations"]:
                                record.variant_combinations.append(combo)
                            if page_data.get("_clean_specs") and page_data["_clean_specs"] != "not found":
                                record.specifications = page_data["_clean_specs"]
                            if page_data.get("_clean_desc") and page_data["_clean_desc"] != "not found":
                                record.description_html = page_data["_clean_desc"]
                            if page_data["warranty"] and "Warranty" not in record.extra_fields:
                                record.extra_fields["Warranty"] = page_data["warranty"]
                            if page_data.get("saved_image_folder") and not record.image_folder:
                                record.image_folder = page_data["saved_image_folder"]

                        record.status = "Done" if self._is_row_complete(record) else "Partial"
                        self.workbook_manager.update_record(record)
                        await asyncio.to_thread(self.workbook_manager.save_workbook)
                        self.on_row_updated(record.to_summary_dict())
                        done_so_far = sum(1 for r in self.workbook_manager.get_all_records() if r.status == "Done")
                        self.on_progress({
                            "current": done_so_far,
                            "total": total_count,
                            "product_name": record.product_name,
                            "site": site_url,
                            "stage": worker_tag,
                        })
                        self.on_log(f"[{worker_tag}] Saved '{record.product_name}' -> {record.status}")
                else:
                    async with self._workbook_lock:
                        self.on_log(f"[{worker_tag}] No match for '{record.product_name}' on {site_url}")
                        if record.status != "Done":
                            record.status = "Partial" if record.scraped_sources else "Pending"
                            self.workbook_manager.update_record(record)
                            self.on_row_updated(record.to_summary_dict())

            # =====================================================================
            # Unified 2-Axis Wave Engine: (Websites at once) × (Tabs per website)
            # =====================================================================
            for wave_start in range(0, len(websites), parallel_websites):
                if self.stop_event.is_set():
                    self.on_log("Stop requested. Exiting queue...")
                    break

                pending_for_wave = [
                    rec for rec in self.workbook_manager.get_all_records()
                    if rec.status in ("Pending", "In Progress", "Partial")
                ]
                if not pending_for_wave:
                    self.on_log("All products are complete! Stopping early.")
                    break

                wave_sites = websites[wave_start:wave_start + parallel_websites]
                per_site_tabs = max(1, min(tabs_per_website, len(pending_for_wave)))
                total_tabs = len(wave_sites) * per_site_tabs
                worker_pages = await self.browser_manager.create_worker_pages(total_tabs)

                wave_num = (wave_start // parallel_websites) + 1
                total_waves = (len(websites) + parallel_websites - 1) // parallel_websites
                self.on_log(
                    f"--- Wave {wave_num}/{total_waves}: {len(wave_sites)} website(s) × {per_site_tabs} tab(s)/site = {total_tabs} tab(s) ({len(pending_for_wave)} pending) ---"
                )

                site_queues: Dict[str, asyncio.Queue] = {}
                for s_url in wave_sites:
                    q: asyncio.Queue = asyncio.Queue()
                    for rec in pending_for_wave:
                        q.put_nowait(rec)
                    site_queues[s_url] = q

                async def _wave_worker(tab_idx: int, tab_page, s_url: str, site_rank: int):
                    if tab_idx > 0:
                        await asyncio.sleep(0.25 * tab_idx)
                    tag = f"Tab {tab_idx + 1} · Site #{site_rank}"
                    q = site_queues[s_url]
                    while not self.stop_event.is_set():
                        try:
                            record: ProductRecord = q.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                        try:
                            if not self.pause_event.is_set():
                                await self.pause_event.wait()
                            if not self.captcha_event.is_set():
                                await self.captcha_event.wait()
                            if self.stop_event.is_set():
                                break

                            # Skip if another website already completed this product!
                            if self._is_row_complete(record):
                                continue

                            await self.resource_guard.throttle_if_needed()

                            async with self._workbook_lock:
                                if record.status == "Pending":
                                    record.status = "In Progress"
                                    self.workbook_manager.update_record(record)
                                    self.on_row_updated(record.to_summary_dict())
                                done_so_far = sum(1 for r in self.workbook_manager.get_all_records() if r.status == "Done")
                                self.on_progress({
                                    "current": done_so_far,
                                    "total": total_count,
                                    "product_name": record.product_name,
                                    "site": s_url,
                                    "stage": tag,
                                })

                            self.on_log(f"[{tag}] Searching '{record.product_name}' on {s_url}...")
                            payload = await _fetch_site_payload(tab_page, s_url, record.product_name, tag)
                            await _commit_site_payload(record, payload, tag, s_url)

                            if delay_s > 0 and not self.stop_event.is_set():
                                await asyncio.sleep(delay_s)

                            if self.resource_guard.should_recycle_browser():
                                self.on_log(f"[{tag}] RAM >85% — recycling tab...")
                                tab_page = await self.browser_manager.recycle_page(tab_page)
                        finally:
                            q.task_done()

                tasks = []
                tab_cursor = 0
                for s_offset, s_url in enumerate(wave_sites):
                    site_rank = wave_start + s_offset + 1
                    for _ in range(per_site_tabs):
                        tasks.append(_wave_worker(tab_cursor, worker_pages[tab_cursor], s_url, site_rank))
                        tab_cursor += 1

                await asyncio.gather(*tasks)

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
