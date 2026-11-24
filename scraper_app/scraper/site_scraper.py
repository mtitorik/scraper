import re
import asyncio
from typing import List, Dict, Any, Optional, Set, Tuple
from urllib.parse import urljoin

from playwright.async_api import Page

from ..models.product_models import ProductRecord, PricePair, OptionPriceEntry, VariantCombination
from ..browser.popup_guard import PopupGuard
from .matcher import is_accessory, is_preowned_or_used, matches_model_name, classify_official_unofficial
from .variant_extractor import VariantExtractor


class SiteScraper:
    """Handles homepage search, search result filtering, multi-listing detection,
    and product page extraction for any e-commerce site.
    """

    SEARCH_INPUT_SELECTORS = [
        "input[type='search']",
        "input[name='search']",
        "input[name='q']",
        "input[name='keyword']",
        "input[placeholder*='search' i]",
        "input[placeholder*='খুঁজুন' i]",
        "#search-input",
        ".search-input",
    ]

    SEARCH_TRIGGER_SELECTORS = [
        "button[aria-label*='search' i]",
        ".header-search-icon",
        ".search-icon",
        ".search-trigger",
        "a[href*='search']",
        ".search-btn",
    ]

    @classmethod
    async def search_product(
        cls,
        page: Page,
        site_url: str,
        product_name: str,
        skip_preowned: bool = True,
    ) -> List[Dict[str, str]]:
        """Navigates to site_url, performs search, and returns candidate links matching product_name.
        Returns list of dicts: [{'title': ..., 'url': ..., 'official_type': ...}].
        """
        candidates: List[Dict[str, str]] = []
        try:
            await page.goto(site_url, wait_until="domcontentloaded", timeout=25000)
            await asyncio.sleep(0.5)
            await PopupGuard.dismiss_promotional_popups(page)

            # Look for search input
            input_elem = None
            for sel in cls.SEARCH_INPUT_SELECTORS:
                try:
                    loc = page.locator(sel).first
                    if await loc.is_visible(timeout=400):
                        input_elem = loc
                        break
                except Exception:
                    continue

            # If not immediately visible, try clicking a search trigger icon
            if not input_elem:
                for trig in cls.SEARCH_TRIGGER_SELECTORS:
                    try:
                        t_loc = page.locator(trig).first
                        if await t_loc.is_visible(timeout=300):
                            await t_loc.click(timeout=800)
                            await asyncio.sleep(0.4)
                            break
                    except Exception:
                        continue

                # Re-check search inputs
                for sel in cls.SEARCH_INPUT_SELECTORS:
                    try:
                        loc = page.locator(sel).first
                        if await loc.is_visible(timeout=400):
                            input_elem = loc
                            break
                    except Exception:
                        continue

            if not input_elem:
                print(f"[SiteScraper] Search input not found on {site_url}")
                return []

            await input_elem.click()
            await input_elem.fill(product_name)
            await asyncio.sleep(0.2)
            await input_elem.press("Enter")
            await asyncio.sleep(1.2)
            await PopupGuard.dismiss_promotional_popups(page)

            # Collect search result links and titles
            raw_items = await page.evaluate(r"""() => {
                const items = [];
                // Look for product cards / search result items
                const cards = document.querySelectorAll(
                    ".product-thumb, .product-card, .product-layout, .search-result-item, .product-item, .card, article"
                );

                if (cards.length > 0) {
                    cards.forEach(card => {
                        const linkEl = card.querySelector("a[href*='product'], h3 a, h4 a, .title a, a.product-title, a");
                        const titleEl = card.querySelector("h3, h4, .title, .product-title, .name, a");
                        if (linkEl && linkEl.href) {
                            const title = (titleEl ? titleEl.innerText : linkEl.innerText).trim();
                            if (title && !items.some(x => x.url === linkEl.href)) {
                                items.push({ title: title, url: linkEl.href });
                            }
                        }
                    });
                } else {
                    // Fallback to all product links
                    const links = Array.from(document.querySelectorAll("a[href]"));
                    links.forEach(a => {
                        const href = a.href;
                        const txt = a.innerText.trim();
                        if (txt.length > 5 && /\d/.test(txt) && !items.some(x => x.url === href)) {
                            items.push({ title: txt, url: href });
                        }
                    });
                }
                return items;
            }""")

            # Filter candidates using matcher rules
            for item in raw_items:
                title = item.get("title", "").strip()
                url = item.get("url", "").strip()
                if not title or not url or url.startswith("javascript:"):
                    continue

                # Exclude accessories unless query asks for it
                if is_accessory(title, product_name):
                    continue

                # Exclude pre-owned / used unless query asks for it
                if skip_preowned and is_preowned_or_used(title, product_name):
                    continue

                # Check strict model matching
                if not matches_model_name(title, product_name):
                    continue

                off_type = classify_official_unofficial(title)
                candidates.append({
                    "title": title,
                    "url": url,
                    "official_type": off_type,
                })

            # Check if separate Official and Unofficial listings exist in candidates
            has_official = any(c["official_type"] == "Official" for c in candidates)
            has_unofficial = any(c["official_type"] == "Unofficial" for c in candidates)

            if has_official and has_unofficial:
                # Keep both!
                best_official = next(c for c in candidates if c["official_type"] == "Official")
                best_unofficial = next(c for c in candidates if c["official_type"] == "Unofficial")
                return [best_official, best_unofficial]

            if candidates:
                # Return the best candidate
                return [candidates[0]]

            return []
        except Exception as e:
            print(f"[SiteScraper] Search error on {site_url}: {e}")
            return []

    @classmethod
    async def scrape_product_page(
        cls,
        page: Page,
        page_url: str,
        target_product_name: str,
        source_website: str,
        pause_event: Optional[asyncio.Event] = None,
        stop_event: Optional[asyncio.Event] = None,
        throttle_callback: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Scrapes full specifications, raw description, warranty, images,
        and variant clicks from a single product page.
        """
        result: Dict[str, Any] = {
            "page_url": page_url,
            "raw_title": "",
            "default_price": PricePair(),
            "attribute_options": {},
            "variant_combinations": [],
            "specifications": "not found",
            "raw_description": "",
            "warranty": "",
            "image_urls": [],
        }

        try:
            await page.goto(page_url, wait_until="domcontentloaded", timeout=25000)
            await asyncio.sleep(0.5)
            await PopupGuard.dismiss_promotional_popups(page)

            # 1. Product title
            raw_title = await page.evaluate(r"""() => {
                const h1 = document.querySelector("h1, .product-title, .product-detail-name");
                return h1 ? h1.innerText.trim() : document.title;
            }""")
            result["raw_title"] = raw_title

            # 2. Click specification tab if available to reveal lazy content
            try:
                spec_tab = page.locator("a:has-text('Specification'), button:has-text('Specification'), [data-tab*='spec']").first
                if await spec_tab.is_visible(timeout=300):
                    await spec_tab.click(timeout=600)
                    await asyncio.sleep(0.3)
            except Exception:
                pass

            # Extract specifications text formatted as Category\nKey: Value
            specs_text = await page.evaluate(r"""() => {
                let text = "";
                const specTable = document.querySelector("#tab-specification, .specification, .product-specs, [data-section*='spec'], table.specs");
                if (specTable) {
                    const rows = specTable.querySelectorAll("tr, .spec-row, li");
                    rows.forEach(r => {
                        const keyEl = r.querySelector("td:first-child, .spec-key, strong, th");
                        const valEl = r.querySelector("td:last-child, .spec-val, span");
                        if (keyEl && valEl && keyEl !== valEl) {
                            text += `${keyEl.innerText.trim()}: ${valEl.innerText.trim()}\n`;
                        } else {
                            const line = r.innerText.trim();
                            if (line) text += `${line}\n`;
                        }
                    });
                }
                return text.trim();
            }""")
            if specs_text:
                result["specifications"] = specs_text

            # 3. Click description tab if available
            try:
                desc_tab = page.locator("a:has-text('Description'), button:has-text('Description'), [data-tab*='desc']").first
                if await desc_tab.is_visible(timeout=300):
                    await desc_tab.click(timeout=600)
                    await asyncio.sleep(0.3)
            except Exception:
                pass

            # Extract raw description
            raw_desc = await page.evaluate(r"""() => {
                const descEl = document.querySelector("#tab-description, .product-description, .description, [data-section*='desc']");
                return descEl ? descEl.innerText.trim() : "";
            }""")
            result["raw_description"] = raw_desc

            # 4. Extract warranty if present
            warranty_text = await page.evaluate(r"""() => {
                const elements = Array.from(document.querySelectorAll(".warranty, .badge-warranty, [data-warranty], p, li"));
                for (const el of elements) {
                    const txt = el.innerText.trim();
                    if (/warranty/i.test(txt) && txt.length < 80) {
                        return txt;
                    }
                }
                return "";
            }""")
            result["warranty"] = warranty_text

            # 5. Extract initial high-resolution gallery images
            gallery_images = await page.evaluate(r"""() => {
                const imgs = [];
                const imgEls = document.querySelectorAll(
                    ".product-gallery img, .product-image img, .slider-thumb img, [data-zoom-image], .gallery-item img"
                );
                imgEls.forEach(img => {
                    const src = img.getAttribute("data-zoom-image") || img.getAttribute("data-src") || img.src;
                    if (src && src.startsWith("http") && !src.includes("icon") && !src.includes("logo") && !src.endsWith(".svg")) {
                        if (!imgs.includes(src)) imgs.push(src);
                    }
                });
                return imgs;
            }""")

            # 6. Run variant click-loop to gather prices, options, and combo rows
            def_price, attr_options, combos, extra_imgs = await VariantExtractor.extract_all_variants_and_combos(
                page=page,
                product_name=target_product_name,
                source_website=source_website,
                page_link=page_url,
                pause_event=pause_event,
                stop_event=stop_event,
                throttle_callback=throttle_callback,
            )

            result["default_price"] = def_price
            result["attribute_options"] = attr_options
            result["variant_combinations"] = combos

            # Combine unique image URLs
            all_imgs = list(gallery_images)
            for ex in extra_imgs:
                if ex not in all_imgs:
                    all_imgs.append(ex)
            result["image_urls"] = all_imgs

            return result
        except Exception as e:
            print(f"[SiteScraper] Page scraping error on {page_url}: {e}")
            return result
