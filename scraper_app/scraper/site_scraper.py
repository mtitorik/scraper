import re
import asyncio
from typing import List, Dict, Any, Optional, Set, Tuple
from urllib.parse import urljoin

from playwright.async_api import Page

from ..models.product_models import ProductRecord, PricePair, OptionPriceEntry, VariantCombination
from ..browser.popup_guard import PopupGuard
from .matcher import (
    is_accessory,
    is_preowned_or_used,
    matches_model_name,
    score_candidate,
    classify_official_unofficial,
)
from .variant_extractor import VariantExtractor


class SiteScraper:
    """Handles homepage search, search result filtering, multi-listing detection,
    and 3-layer universal product page extraction for any e-commerce site.
    """

    SEARCH_INPUT_SELECTORS = [
        "input[type='search']",
        "input[name='search']",
        "input[name='q']",
        "input[name='s']",
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
    def _build_fallback_queries(cls, product_name: str) -> List[str]:
        """Generates cleaner fallback search queries for hyphenated SKUs like 'Joyroom JR-OE2S'."""
        fallbacks: List[str] = []
        # If there's a hyphenated model code like JR-OE2S, try:
        # 1) Just the SKU ('JR-OE2S')
        # 2) Without the prefix ('Joyroom OE2S')
        sku_match = re.search(r"\b([a-zA-Z]{1,4})-([a-zA-Z0-9]*\d[a-zA-Z0-9]*)\b", product_name)
        if sku_match:
            full_sku = sku_match.group(0)
            suffix = sku_match.group(2)
            no_prefix = product_name.replace(full_sku, suffix).strip()
            if full_sku.lower() != product_name.lower():
                fallbacks.append(full_sku)
            if no_prefix.lower() != product_name.lower() and no_prefix not in fallbacks:
                fallbacks.append(no_prefix)
        return fallbacks

    @classmethod
    async def _find_search_input(cls, page: Page):
        for sel in cls.SEARCH_INPUT_SELECTORS:
            try:
                loc = page.locator(sel).first
                if await loc.is_visible(timeout=400):
                    return loc
            except Exception:
                continue

        for trig in cls.SEARCH_TRIGGER_SELECTORS:
            try:
                t_loc = page.locator(trig).first
                if await t_loc.is_visible(timeout=300):
                    await t_loc.click(timeout=800)
                    await asyncio.sleep(0.4)
                    break
            except Exception:
                continue

        for sel in cls.SEARCH_INPUT_SELECTORS:
            try:
                loc = page.locator(sel).first
                if await loc.is_visible(timeout=400):
                    return loc
            except Exception:
                continue

        return None

    @classmethod
    async def _collect_raw_candidates(cls, page: Page) -> List[Dict[str, str]]:
        """Collects candidate product links from BOTH product cards AND product-like links
        (including live search dropdowns and Tailwind/Next.js grids without .card classes).
        """
        return await page.evaluate(r"""() => {
            const items = [];
            const seenUrls = new Set();

            const addItem = (title, url) => {
                if (!title || !url) return;
                const cleanUrl = url.split("#")[0].trim();
                const cleanTitle = title.replace(/\s+/g, " ").trim();
                if (!cleanTitle || cleanTitle.length < 3) return;
                if (!cleanUrl.startsWith("http")) return;
                if (seenUrls.has(cleanUrl)) return;
                seenUrls.add(cleanUrl);
                items.push({ title: cleanTitle, url: cleanUrl });
            };

            // 1. Standard product cards & search dropdown items
            const cards = document.querySelectorAll(
                ".product-thumb, .product-card, .product-layout, .search-result-item, .product-item, .search-dropdown a, [class*='search-result' i] a, [class*='product' i] a"
            );
            cards.forEach(card => {
                if (card.tagName === "A") {
                    const titleEl = card.querySelector("h2, h3, h4, h5, p, span, .title, .name");
                    const title = (titleEl ? titleEl.innerText : card.innerText) || card.getAttribute("title") || "";
                    addItem(title, card.href);
                } else {
                    const linkEl = card.querySelector("a[href*='product'], h2 a, h3 a, h4 a, .title a, a.product-title, a[href]");
                    const titleEl = card.querySelector("h2, h3, h4, h5, .title, .product-title, .name, p");
                    if (linkEl && linkEl.href) {
                        const title = (titleEl ? titleEl.innerText : linkEl.innerText) || linkEl.getAttribute("title") || "";
                        addItem(title, linkEl.href);
                    }
                }
            });

            // 2. Always also scan all product-like links (handles Tailwind/Next.js div grids!)
            const allLinks = Array.from(document.querySelectorAll("a[href]"));
            allLinks.forEach(a => {
                const href = a.href || "";
                const hrefLower = href.toLowerCase();
                // Skip obvious non-product navigation links
                if (/\/(cart|checkout|login|register|account|wishlist|compare|blog|news|contact|about|privacy|terms|category|categories|brand|brands)\b/.test(hrefLower)) {
                    return;
                }
                const isProductUrl = /\/(product|products|item|p|shop|gadget|gadgets)\//i.test(hrefLower);
                const heading = a.querySelector("h2, h3, h4, h5, p, .title, .name");
                const rawText = (heading ? heading.innerText : a.innerText) || a.getAttribute("title") || "";
                // Clean out trailing price lines from multi-line card links
                const firstLine = rawText.split("\n").map(s => s.trim()).filter(s => s && !/^(৳|bdt|tk|\$|out of stock|in stock|add to cart|buy now|save|\-\d+%)/i.test(s))[0] || "";
                if (firstLine.length >= 4 && (isProductUrl || /\d/.test(firstLine))) {
                    addItem(firstLine, href);
                }
            });

            return items;
        }""")

    @classmethod
    def _filter_and_rank_candidates(
        cls,
        raw_items: List[Dict[str, str]],
        product_name: str,
        skip_preowned: bool,
    ) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        for item in raw_items:
            title = item.get("title", "").strip()
            url = item.get("url", "").strip()
            if not title or not url or url.startswith("javascript:"):
                continue

            if is_accessory(title, product_name):
                continue

            if skip_preowned and is_preowned_or_used(title, product_name):
                continue

            if not matches_model_name(title, product_name):
                continue

            off_type = classify_official_unofficial(title)
            candidates.append({
                "title": title,
                "url": url,
                "official_type": off_type,
                "score": score_candidate(title, product_name),
            })

        # Sort highest score first so exact model/generation always beats noisy results
        candidates.sort(key=lambda c: c["score"], reverse=True)
        return candidates

    @classmethod
    async def _run_search_query(
        cls,
        page: Page,
        query: str,
        target_product_name: str,
        skip_preowned: bool,
    ) -> List[Dict[str, Any]]:
        input_elem = await cls._find_search_input(page)
        if not input_elem:
            return []

        await input_elem.click()
        await input_elem.fill("")
        await input_elem.fill(query)
        await asyncio.sleep(0.8)  # Allow instant search dropdowns to populate

        # Check live dropdown candidates BEFORE pressing Enter as well
        dropdown_items = await cls._collect_raw_candidates(page)

        await input_elem.press("Enter")
        try:
            await page.wait_for_load_state("networkidle", timeout=3500)
        except Exception:
            await asyncio.sleep(1.5)
        await PopupGuard.dismiss_promotional_popups(page)

        page_items = await cls._collect_raw_candidates(page)

        # Merge page items + dropdown items (deduplicated by URL)
        merged: List[Dict[str, str]] = []
        seen: Set[str] = set()
        for it in page_items + dropdown_items:
            u = it.get("url", "")
            if u and u not in seen:
                seen.add(u)
                merged.append(it)

        return cls._filter_and_rank_candidates(merged, target_product_name, skip_preowned)

    @classmethod
    async def search_product(
        cls,
        page: Page,
        site_url: str,
        product_name: str,
        skip_preowned: bool = True,
    ) -> List[Dict[str, str]]:
        """Navigates to site_url, performs search (with smart SKU fallback if needed),
        and returns top-ranked candidate link(s) matching product_name.
        """
        try:
            await page.goto(site_url, wait_until="domcontentloaded", timeout=25000)
            await asyncio.sleep(0.6)
            await PopupGuard.dismiss_promotional_popups(page)

            candidates = await cls._run_search_query(page, product_name, product_name, skip_preowned)

            # Fallback search if full query returned nothing (e.g., hyphenated SKU like 'Joyroom JR-OE2S')
            if not candidates:
                for fb_query in cls._build_fallback_queries(product_name):
                    print(f"[SiteScraper] Retrying search on {site_url} with fallback query: '{fb_query}'")
                    candidates = await cls._run_search_query(page, fb_query, product_name, skip_preowned)
                    if candidates:
                        break

            if not candidates:
                return []

            # Check if separate Official and Unofficial listings exist among top candidates
            has_official = any(c["official_type"] == "Official" for c in candidates)
            has_unofficial = any(c["official_type"] == "Unofficial" for c in candidates)

            if has_official and has_unofficial:
                best_official = next(c for c in candidates if c["official_type"] == "Official")
                best_unofficial = next(c for c in candidates if c["official_type"] == "Unofficial")
                return [best_official, best_unofficial]

            return [candidates[0]]
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
        and variant clicks from a single product page using a 3-layer universal extractor.
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
            try:
                await page.wait_for_load_state("networkidle", timeout=3500)
            except Exception:
                await asyncio.sleep(0.8)
            await PopupGuard.dismiss_promotional_popups(page)

            # Scroll down gently to trigger lazy-loaded spec/description sections on Next.js/React pages
            await page.evaluate("window.scrollBy(0, 650)")
            await asyncio.sleep(0.35)
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(0.2)

            # 1. Product title
            raw_title = await page.evaluate(r"""() => {
                const h1 = document.querySelector("h1, .product-title, .product-detail-name");
                return h1 ? h1.innerText.trim() : document.title;
            }""")
            result["raw_title"] = raw_title

            # 2. Click Specification tab if interactive
            for tab_sel in [
                "button:has-text('Specification')",
                "a:has-text('Specification')",
                "[role='tab']:has-text('Specification')",
                "button:has-text('Specs')",
                "a:has-text('Additional information')",
                "[data-tab*='spec' i]",
            ]:
                try:
                    spec_tab = page.locator(tab_sel).first
                    if await spec_tab.is_visible(timeout=250):
                        await spec_tab.click(timeout=600)
                        await asyncio.sleep(0.35)
                        break
                except Exception:
                    continue

            # 3-Layer Universal Specifications Extractor
            specs_text = await page.evaluate(r"""() => {
                const extractFromContainer = (container) => {
                    if (!container) return "";
                    const lines = [];
                    const seen = new Set();
                    const pushLine = (s) => {
                        const clean = s.replace(/\s+/g, " ").trim();
                        if (clean && clean.length > 1 && !seen.has(clean)) {
                            seen.add(clean);
                            lines.push(clean);
                        }
                    };

                    // Tables (tr -> th/td pairs)
                    const rows = container.querySelectorAll("tr");
                    if (rows.length > 0) {
                        rows.forEach(r => {
                            const cells = Array.from(r.querySelectorAll("th, td"));
                            if (cells.length >= 2) {
                                const k = cells[0].innerText.trim();
                                const v = cells.slice(1).map(c => c.innerText.trim()).filter(Boolean).join(" | ");
                                if (k && v) pushLine(`${k}: ${v}`);
                            } else if (cells.length === 1) {
                                pushLine(cells[0].innerText);
                            }
                        });
                    }

                    // Definition lists (dl -> dt/dd)
                    if (lines.length === 0) {
                        const dts = container.querySelectorAll("dt");
                        dts.forEach(dt => {
                            const dd = dt.nextElementSibling;
                            if (dd && dd.tagName === "DD") {
                                pushLine(`${dt.innerText.trim()}: ${dd.innerText.trim()}`);
                            }
                        });
                    }

                    // Grid / Flex 2-column spec rows (common on Next.js / Tailwind stores!)
                    if (lines.length === 0) {
                        const kvRows = container.querySelectorAll(".spec-row, .specification-row, [class*='spec' i] > div, li");
                        kvRows.forEach(r => {
                            const kids = Array.from(r.children).filter(el => el.innerText && el.innerText.trim());
                            if (kids.length === 2) {
                                pushLine(`${kids[0].innerText.trim()}: ${kids[1].innerText.trim()}`);
                            } else if (r.tagName === "LI") {
                                pushLine(r.innerText);
                            }
                        });
                    }

                    // Fallback plain lines
                    if (lines.length === 0) {
                        const raw = (container.innerText || "").split("\n").map(l => l.trim()).filter(Boolean);
                        raw.forEach(pushLine);
                    }

                    return lines.join("\n").trim();
                };

                // Layer 1: Broad CSS selectors (OpenCart, WooCommerce, Shopify, custom)
                const selectors = [
                    "#tab-specification",
                    "#specification",
                    "#specifications",
                    "#specs",
                    "#tab-additional_information",
                    ".woocommerce-Tabs-panel--additional_information",
                    ".woocommerce-product-attributes",
                    ".product-specs",
                    ".specifications",
                    ".specification",
                    "[data-section*='spec' i]",
                    "[id*='specification' i]",
                    "table.specs",
                ];
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el && el.innerText.trim().length > 20) {
                        const extracted = extractFromContainer(el);
                        if (extracted.length > 20) return extracted;
                    }
                }

                // Layer 2: Heading-anchored discovery (Tailwind / Next.js / React)
                const headings = Array.from(document.querySelectorAll("h1, h2, h3, h4, h5, [role='tab'], button"));
                for (const h of headings) {
                    const txt = (h.innerText || "").trim().toLowerCase();
                    if (/^(specification|specifications|technical specifications?|tech specs?|key specs?|additional information)$/.test(txt)) {
                        // Try sibling or parent section
                        const section = h.closest("section, [role='tabpanel'], .tab-pane, .card") || h.parentElement;
                        if (section) {
                            const extracted = extractFromContainer(section);
                            if (extracted.length > 25) return extracted;
                        }
                        if (h.nextElementSibling) {
                            const extracted = extractFromContainer(h.nextElementSibling);
                            if (extracted.length > 25) return extracted;
                        }
                    }
                }

                // Layer 3: Any structured <table> in main content with >= 3 key-value rows
                const tables = Array.from(document.querySelectorAll("main table, article table, .product-details table, table"));
                for (const tbl of tables) {
                    if (tbl.closest("header, footer, nav")) continue;
                    const rows = tbl.querySelectorAll("tr");
                    if (rows.length >= 3) {
                        const extracted = extractFromContainer(tbl);
                        if (extracted.length > 30) return extracted;
                    }
                }

                return "";
            }""")
            if specs_text:
                result["specifications"] = specs_text

            # 3. Click Description tab if interactive
            for tab_sel in [
                "button:has-text('Description')",
                "a:has-text('Description')",
                "[role='tab']:has-text('Description')",
                "button:has-text('Overview')",
                "a:has-text('Overview')",
                "[data-tab*='desc' i]",
            ]:
                try:
                    desc_tab = page.locator(tab_sel).first
                    if await desc_tab.is_visible(timeout=250):
                        await desc_tab.click(timeout=600)
                        await asyncio.sleep(0.35)
                        break
                except Exception:
                    continue

            # 3-Layer Universal Description Extractor
            raw_desc = await page.evaluate(r"""() => {
                const cleanText = (el) => {
                    if (!el) return "";
                    const clone = el.cloneNode(true);
                    clone.querySelectorAll("script, style, nav, button, form").forEach(n => n.remove());
                    return (clone.innerText || "").replace(/\n{3,}/g, "\n\n").trim();
                };

                // Layer 1: Broad CSS selectors
                const selectors = [
                    "#tab-description",
                    "#description",
                    ".woocommerce-Tabs-panel--description",
                    ".product-description",
                    ".product-detail-description",
                    ".product-overview",
                    "[data-section*='desc' i]",
                    "[id*='product-desc' i]",
                    "[class*='product-desc' i]",
                    ".description",
                ];
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el && !el.closest("header, footer, nav")) {
                        const txt = cleanText(el);
                        if (txt.length > 40) return txt;
                    }
                }

                // Layer 2: Active tabpanel after clicking Description
                const activePanel = document.querySelector("[role='tabpanel']:not([hidden]), .tab-pane.active");
                if (activePanel) {
                    const txt = cleanText(activePanel);
                    if (txt.length > 40) return txt;
                }

                // Layer 3: Heading-anchored discovery (Tailwind / Next.js / React)
                const headings = Array.from(document.querySelectorAll("h1, h2, h3, h4, h5"));
                for (const h of headings) {
                    const txt = (h.innerText || "").trim().toLowerCase();
                    if (/^(description|product description|overview|about this item|product details|key features|highlights)$/.test(txt)) {
                        const section = h.closest("section, [role='tabpanel'], .tab-pane") || h.parentElement;
                        if (section) {
                            const content = cleanText(section);
                            if (content.length > 40) return content;
                        }
                        if (h.nextElementSibling) {
                            const content = cleanText(h.nextElementSibling);
                            if (content.length > 40) return content;
                        }
                    }
                }

                return "";
            }""")
            result["raw_description"] = raw_desc

            # 4. Extract warranty if present
            warranty_text = await page.evaluate(r"""() => {
                const elements = Array.from(document.querySelectorAll(".warranty, .badge-warranty, [data-warranty], p, li, span"));
                for (const el of elements) {
                    const txt = (el.innerText || "").trim();
                    if (/warranty/i.test(txt) && txt.length >= 6 && txt.length < 85) {
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
                    ".product-gallery img, .product-image img, .slider-thumb img, [data-zoom-image], .gallery-item img, main img"
                );
                imgEls.forEach(img => {
                    if (img.closest("header, footer, nav")) return;
                    const src = img.getAttribute("data-zoom-image") || img.getAttribute("data-src") || img.src;
                    if (src && src.startsWith("http") && !/icon|logo|badge|payment|flag/i.test(src) && !src.endsWith(".svg")) {
                        if ((img.naturalWidth === 0 || img.naturalWidth >= 150) && !imgs.includes(src)) {
                            imgs.push(src);
                        }
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

            all_imgs = list(gallery_images)
            for ex in extra_imgs:
                if ex not in all_imgs:
                    all_imgs.append(ex)
            result["image_urls"] = all_imgs

            return result
        except Exception as e:
            print(f"[SiteScraper] Page scraping error on {page_url}: {e}")
            return result
