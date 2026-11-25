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
        """Generates cleaner fallback search queries for hyphenated SKUs like 'Joyroom JR-OE2S'
        and long 6+ word titles that strict store search engines fail to match verbatim.
        """
        fallbacks: List[str] = []
        IGNORE_HYPHEN = {"in-1", "2-in-1", "3-in-1", "4-in-1", "5-in-1", "type-c", "usb-c", "wi-fi", "in-ear", "on-ear", "over-ear", "built-in"}
        # 1) Hyphenated model code like JR-OE2S -> try SKU ('JR-OE2S') and without prefix ('Joyroom OE2S')
        sku_match = re.search(r"\b([a-zA-Z]{1,4})-([a-zA-Z0-9]*\d[a-zA-Z0-9]*)\b", product_name)
        if sku_match and sku_match.group(0).lower() not in IGNORE_HYPHEN:
            full_sku = sku_match.group(0)
            suffix = sku_match.group(2)
            no_prefix = product_name.replace(full_sku, suffix).strip()
            if len(full_sku) >= 4 and full_sku.lower() != product_name.lower():
                fallbacks.append(full_sku)
            if no_prefix.lower() != product_name.lower() and no_prefix not in fallbacks:
                fallbacks.append(no_prefix)

        # 2) Long 6+ word title -> try clean first 4 words (strips marketing fluff & special pipes/dashes)
        clean_words = [w for w in re.sub(r"[|•–—/()]+", " ", product_name).split() if len(w) > 1 or w.isdigit()]
        if len(clean_words) >= 6:
            short_q = " ".join(clean_words[:4])
            if short_q.lower() != product_name.lower() and short_q not in fallbacks:
                fallbacks.append(short_q)
        return fallbacks

    @classmethod
    async def _find_search_input(cls, page: Page):
        """Fast single-eval visible search input finder (<10ms instead of 9x400ms sequential timeouts)."""
        async def _probe_visible_input() -> Optional[str]:
            try:
                return await page.evaluate(r"""(selectors) => {
                    for (const sel of selectors) {
                        const els = document.querySelectorAll(sel);
                        for (const el of els) {
                            const r = el.getBoundingClientRect();
                            if (r.width > 20 && r.height > 10 && window.getComputedStyle(el).visibility !== "hidden") {
                                return sel;
                            }
                        }
                    }
                    return null;
                }""", cls.SEARCH_INPUT_SELECTORS)
            except Exception:
                return None

        matched = await _probe_visible_input()
        if matched:
            return page.locator(matched).first

        # Try clicking a visible search trigger icon in one fast DOM probe
        try:
            trig_sel = await page.evaluate(r"""(triggers) => {
                for (const sel of triggers) {
                    const el = document.querySelector(sel);
                    if (!el) continue;
                    const r = el.getBoundingClientRect();
                    if (r.width > 5 && r.height > 5 && window.getComputedStyle(el).visibility !== "hidden") {
                        return sel;
                    }
                }
                return null;
            }""", cls.SEARCH_TRIGGER_SELECTORS)
            if trig_sel:
                await page.locator(trig_sel).first.click(timeout=800)
                await asyncio.sleep(0.25)
                matched = await _probe_visible_input()
                if matched:
                    return page.locator(matched).first
        except Exception:
            pass

        # Cold-hydration safety retry (0ms overhead when search bar is already rendered!)
        await asyncio.sleep(0.6)
        matched = await _probe_visible_input()
        if matched:
            return page.locator(matched).first

        return None

    @classmethod
    async def _extract_page_title(cls, page: Page) -> str:
        """4-step universal product title resolver:
        1. <h1>
        2. Common product-title selectors / schema ([itemprop='name'], .product_title, .product-title)
        3. OpenGraph meta tag (<meta property='og:title'>)
        4. document.title (stripping trailing ' - Store' / ' | Store' suffixes)
        """
        try:
            title = await page.evaluate(r"""() => {
                const pick = (sel) => {
                    const el = document.querySelector(sel);
                    return el && el.innerText ? el.innerText.trim() : "";
                };
                // 1. Standard h1
                const h1 = pick("h1");
                if (h1 && h1.length >= 3) return h1;

                // 2. Common product-title classes & schema markup
                for (const sel of [
                    "[itemprop='name']",
                    ".product_title",
                    ".product-title",
                    ".product-detail-name",
                    ".product-name",
                    "main h2"
                ]) {
                    const t = pick(sel);
                    if (t && t.length >= 3) return t;
                }

                // 3. OpenGraph meta tag
                const og = document.querySelector("meta[property='og:title'], meta[name='og:title']");
                if (og && og.content && og.content.trim().length >= 3) {
                    return og.content.trim().replace(/\s*[\-|–|—|\|]\s*[^\-|–|—|\|]+$/, "").trim();
                }

                // 4. Browser tab title
                return (document.title || "").replace(/\s*[\-|–|—|\|]\s*[^\-|–|—|\|]+$/, "").trim();
            }""")
            return (title or "").strip()
        except Exception:
            return ""

    @classmethod
    async def _collect_raw_candidates(cls, page: Page) -> List[Dict[str, str]]:
        """Collects candidate product links from BOTH product cards AND product-like links
        (including live search dropdowns and Tailwind/Next.js grids), ignoring skip-links & nav/footer noise.
        """
        return await page.evaluate(r"""() => {
            const items = [];
            const seenUrls = new Set();

            const isInvalidHref = (a) => {
                const rawHref = (a.getAttribute("href") || "").trim();
                if (!rawHref || rawHref.startsWith("#") || rawHref.startsWith("javascript:") || rawHref.startsWith("mailto:") || rawHref.startsWith("tel:")) {
                    return true;
                }
                return false;
            };

            const BADGE_ONLY_RE = /^(new|deal|new\s+deal|hot|sale|hot\s+deal|flash\s+sale|featured|best\s*seller|top\s*rated|limited|offer|discount|out\s+of\s+stock|in\s+stock|pre-?order|quick\s+view|view\s+all.*|add\s+to\s+cart|buy\s+now|shop\s+now|-\d+%|save\s+.*)$/i;
            const byUrl = new Map();

            const addItem = (title, url) => {
                if (!title || !url) return;
                const cleanUrl = url.split("#")[0].trim();
                const cleanTitle = title.replace(/\s+/g, " ").trim();
                if (!cleanTitle || cleanTitle.length < 3 || BADGE_ONLY_RE.test(cleanTitle)) return;
                if (!cleanUrl.startsWith("http")) return;
                const prev = byUrl.get(cleanUrl);
                // If multiple anchors point to the same product URL (e.g. badge/image link + title link), keep the richer title!
                if (!prev || cleanTitle.length > prev.title.length) {
                    byUrl.set(cleanUrl, { title: cleanTitle, url: cleanUrl });
                }
            };

            // 1. Standard product cards & search dropdown items
            const cards = document.querySelectorAll(
                ".product-thumb, .product-card, .product-layout, .search-result-item, .product-item, .search-dropdown a, [class*='search-result' i] a, [class*='autocomplete' i] a, [class*='product' i] a"
            );
            cards.forEach(card => {
                if (card.closest("footer")) return;
                if (card.tagName === "A") {
                    if (isInvalidHref(card)) return;
                    const titleEl = card.querySelector("h2, h3, h4, h5, p, span, .title, .name");
                    const title = (titleEl ? titleEl.innerText : card.innerText) || card.getAttribute("title") || "";
                    addItem(title, card.href);
                } else {
                    const linkEl = card.querySelector("a[href*='product'], h2 a, h3 a, h4 a, .title a, a.product-title, a[href]");
                    const titleEl = card.querySelector("h2, h3, h4, h5, .title, .product-title, .name, p");
                    if (linkEl && !isInvalidHref(linkEl) && linkEl.href) {
                        const title = (titleEl ? titleEl.innerText : linkEl.innerText) || linkEl.getAttribute("title") || "";
                        addItem(title, linkEl.href);
                    }
                }
            });

            // 2. Always also scan all product-like links (handles Tailwind/Next.js div grids!)
            const allLinks = Array.from(document.querySelectorAll("a[href]"));
            allLinks.forEach(a => {
                if (isInvalidHref(a)) return;
                if (a.closest("footer, nav") && !a.closest("[class*='search' i], [class*='dropdown' i], [class*='autocomplete' i]")) {
                    return;
                }
                const href = a.href || "";
                const hrefLower = href.toLowerCase();
                if (/\/(cart|checkout|login|register|account|wishlist|compare|blog|news|contact|about|privacy|terms|category|categories|product-category|brand|brands)\b/.test(hrefLower)) {
                    return;
                }
                const isProductUrl = /\/(product|products|item|p|shop|gadget|gadgets)\//i.test(hrefLower);
                const heading = a.querySelector("h2, h3, h4, h5, p, .title, .name");
                const rawText = (heading ? heading.innerText : a.innerText) || a.getAttribute("title") || "";
                const firstLine = rawText.split("\n").map(s => s.trim()).filter(s => s && !/^(৳|bdt|tk|\$|out of stock|in stock|add to cart|buy now|save|\-\d+%)/i.test(s))[0] || "";
                if (firstLine.length >= 4 && (isProductUrl || /\d/.test(firstLine))) {
                    addItem(firstLine, href);
                }
            });

            return Array.from(byUrl.values());
        }""")

    @classmethod
    def _has_custom_exclude(cls, title: str, custom_excludes: Optional[List[str]]) -> bool:
        if not custom_excludes:
            return False
        t_lower = title.lower()
        return any(kw in t_lower for kw in custom_excludes if kw)

    @classmethod
    def _filter_and_rank_candidates(
        cls,
        raw_items: List[Dict[str, str]],
        product_name: str,
        skip_preowned: bool,
        skip_accessories: bool = True,
        strict_model_matching: bool = True,
        custom_excludes: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        for item in raw_items:
            title = item.get("title", "").strip()
            url = item.get("url", "").strip()
            if not title or not url or url.startswith("javascript:"):
                continue

            if cls._has_custom_exclude(title, custom_excludes):
                continue

            if skip_accessories and is_accessory(title, product_name):
                continue

            if skip_preowned and is_preowned_or_used(title, product_name):
                continue

            if strict_model_matching and not matches_model_name(title, product_name):
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
        skip_accessories: bool = True,
        strict_model_matching: bool = True,
        custom_excludes: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        input_elem = await cls._find_search_input(page)
        if not input_elem:
            return []

        url_before = page.url.rstrip("/")

        await input_elem.click()
        await input_elem.fill("")
        await input_elem.fill(query)
        await asyncio.sleep(0.35)  # Allow instant search dropdowns to populate

        # Check live dropdown candidates BEFORE pressing Enter
        dropdown_items = await cls._collect_raw_candidates(page)

        await input_elem.press("Enter")
        try:
            await page.wait_for_load_state("networkidle", timeout=1800)
        except Exception:
            await asyncio.sleep(0.45)

        # Fallback: if pressing Enter didn't navigate (non-form React/SPA search bar), click search submit button
        if page.url.rstrip("/") == url_before:
            try:
                sub_sel = await page.evaluate(r"""() => {
                    for (const sel of ["button[type='submit']", "button[aria-label*='search' i]", ".search-submit", ".search-btn"]) {
                        const el = document.querySelector(sel);
                        if (el && el.getBoundingClientRect().width > 5) return sel;
                    }
                    return null;
                }""")
                if sub_sel:
                    await page.locator(sub_sel).first.click(timeout=600)
                    try:
                        await page.wait_for_load_state("networkidle", timeout=1600)
                    except Exception:
                        await asyncio.sleep(0.4)
            except Exception:
                pass

        await PopupGuard.dismiss_promotional_popups(page)

        # Direct Product Page Redirect Check (e.g. WooCommerce single-match redirect!)
        current_url = page.url.rstrip("/")
        is_search_results_url = bool(re.search(r"([?&](s|q|search|keyword)=|/search\b)", current_url, re.IGNORECASE))
        if current_url != url_before and not is_search_results_url:
            direct_title = await cls._extract_page_title(page)
            if (
                direct_title
                and not cls._has_custom_exclude(direct_title, custom_excludes)
                and not (skip_accessories and is_accessory(direct_title, target_product_name))
                and not (skip_preowned and is_preowned_or_used(direct_title, target_product_name))
                and (not strict_model_matching or matches_model_name(direct_title, target_product_name))
            ):
                return [{
                    "title": direct_title,
                    "url": page.url.split("#")[0],
                    "official_type": classify_official_unofficial(direct_title),
                    "score": score_candidate(direct_title, target_product_name) + 50.0,
                }]

        page_items = await cls._collect_raw_candidates(page)

        # Merge page items + dropdown items (deduplicated by URL)
        merged: List[Dict[str, str]] = []
        seen: Set[str] = set()
        for it in page_items + dropdown_items:
            u = it.get("url", "")
            if u and u not in seen:
                seen.add(u)
                merged.append(it)

        return cls._filter_and_rank_candidates(
            merged,
            target_product_name,
            skip_preowned=skip_preowned,
            skip_accessories=skip_accessories,
            strict_model_matching=strict_model_matching,
            custom_excludes=custom_excludes,
        )

    @classmethod
    async def search_product(
        cls,
        page: Page,
        site_url: str,
        product_name: str,
        skip_preowned: bool = True,
        skip_accessories: bool = True,
        strict_model_matching: bool = True,
        enable_fallback_sku_search: bool = True,
        custom_excludes: Optional[List[str]] = None,
    ) -> List[Dict[str, str]]:
        """Navigates to site_url, performs search (with optional smart SKU fallback),
        and returns top-ranked candidate link(s) matching product_name.
        """
        try:
            # Fast-path: if already on the exact same site origin with a visible header search bar,
            # skip redundant homepage reload (~2-4s saved per product!)
            from urllib.parse import urlparse
            same_origin = bool(page.url and urlparse(page.url).netloc.lower() == urlparse(site_url).netloc.lower())
            need_home = True
            if same_origin:
                existing_input = await cls._find_search_input(page)
                if existing_input is not None:
                    need_home = False
            if need_home:
                await page.goto(site_url, wait_until="domcontentloaded", timeout=25000)
                await asyncio.sleep(0.25)
            await PopupGuard.dismiss_promotional_popups(page)

            candidates = await cls._run_search_query(
                page,
                product_name,
                product_name,
                skip_preowned=skip_preowned,
                skip_accessories=skip_accessories,
                strict_model_matching=strict_model_matching,
                custom_excludes=custom_excludes,
            )

            # Safety fallback: if same-origin subpage search returned nothing, reload homepage once and retry
            if not candidates and not need_home:
                await page.goto(site_url, wait_until="domcontentloaded", timeout=25000)
                await asyncio.sleep(0.25)
                await PopupGuard.dismiss_promotional_popups(page)
                candidates = await cls._run_search_query(
                    page,
                    product_name,
                    product_name,
                    skip_preowned=skip_preowned,
                    skip_accessories=skip_accessories,
                    strict_model_matching=strict_model_matching,
                    custom_excludes=custom_excludes,
                )

            # Fallback search if full query returned nothing (e.g., hyphenated SKU like 'Joyroom JR-OE2S')
            if not candidates and enable_fallback_sku_search:
                for fb_query in cls._build_fallback_queries(product_name):
                    print(f"[SiteScraper] Retrying search on {site_url} with fallback query: '{fb_query}'")
                    candidates = await cls._run_search_query(
                        page,
                        fb_query,
                        product_name,
                        skip_preowned=skip_preowned,
                        skip_accessories=skip_accessories,
                        strict_model_matching=strict_model_matching,
                        custom_excludes=custom_excludes,
                    )
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
        scrape_variants: bool = True,
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
            # Fast-path: skip redundant double-goto if search already redirected straight to this product page!
            cur_norm = (page.url or "").split("#")[0].rstrip("/")
            target_norm = (page_url or "").split("#")[0].rstrip("/")
            if cur_norm != target_norm:
                await page.goto(page_url, wait_until="domcontentloaded", timeout=25000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=1800)
                except Exception:
                    await asyncio.sleep(0.35)
            await PopupGuard.dismiss_promotional_popups(page)

            # Scroll down gently to trigger lazy-loaded spec/description sections on Next.js/React pages
            await page.evaluate("window.scrollBy(0, 650)")
            await asyncio.sleep(0.18)
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(0.1)

            # 1. Product title (4-step fallback: h1 -> product-title/schema -> og:title -> document.title)
            result["raw_title"] = await cls._extract_page_title(page)

            # 2. Run Variant Click-Loop FIRST while page is at top (or just extract default price if disabled)
            await PopupGuard.dismiss_promotional_popups(page)
            await page.evaluate("window.scrollTo(0, 0)")

            if scrape_variants:
                def_price, attr_options, combos, extra_imgs = await VariantExtractor.extract_all_variants_and_combos(
                    page=page,
                    product_name=target_product_name,
                    source_website=source_website,
                    page_link=page_url,
                    pause_event=pause_event,
                    stop_event=stop_event,
                    throttle_callback=throttle_callback,
                )
            else:
                def_price = await VariantExtractor.extract_page_prices(page)
                attr_options, combos, extra_imgs = {}, [], set()
            result["default_price"] = def_price
            result["attribute_options"] = attr_options
            result["variant_combinations"] = combos

            # 3. Click Specification tab if interactive (single fast DOM probe instead of 6x250ms timeouts)
            try:
                spec_clicked = await page.evaluate(r"""() => {
                    const els = Array.from(document.querySelectorAll("button, a, [role='tab'], [data-tab*='spec' i]"));
                    for (const el of els) {
                        if (el.closest("header, footer, nav")) continue;
                        const r = el.getBoundingClientRect();
                        if (r.width === 0 || r.height === 0) continue;
                        const txt = (el.innerText || "").trim().toLowerCase();
                        if (/^(specification|specifications|specs|additional information)$/.test(txt)) {
                            el.click();
                            return true;
                        }
                    }
                    return false;
                }""")
                if spec_clicked:
                    await asyncio.sleep(0.2)
            except Exception:
                pass

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

                // Layer 1: Broad CSS selectors (OpenCart, WooCommerce, Shopify, Next.js/custom)
                const selectors = [
                    "#tab-specification",
                    "#tabSpecification",
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
                    "[id*='tabspec' i]",
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

            # 3b. Click Description tab if interactive (single fast DOM probe instead of 6x250ms timeouts)
            try:
                desc_clicked = await page.evaluate(r"""() => {
                    const els = Array.from(document.querySelectorAll("button, a, [role='tab'], [data-tab*='desc' i]"));
                    for (const el of els) {
                        if (el.closest("header, footer, nav")) continue;
                        const r = el.getBoundingClientRect();
                        if (r.width === 0 || r.height === 0) continue;
                        const txt = (el.innerText || "").trim().toLowerCase();
                        if (/^(descriptions?|overview)$/.test(txt)) {
                            el.click();
                            return true;
                        }
                    }
                    return false;
                }""")
                if desc_clicked:
                    await asyncio.sleep(0.2)
            except Exception:
                pass

            # 3-Layer Universal Description Extractor
            raw_desc = await page.evaluate(r"""() => {
                const cleanText = (el) => {
                    if (!el) return "";
                    const clone = el.cloneNode(true);
                    clone.querySelectorAll("script, style, nav, button, form").forEach(n => n.remove());
                    return (clone.innerText || "").replace(/\n{3,}/g, "\n\n").trim();
                };

                // Layer 1: Broad CSS selectors (OpenCart, WooCommerce, Shopify, Elementor, Next.js/camelCase)
                const selectors = [
                    "#tab-description",
                    "#tabDescription",
                    "#description",
                    ".woocommerce-Tabs-panel--description",
                    ".product-description",
                    ".product-detail-description",
                    ".product-overview",
                    ".elementor-widget-theme-post-content",
                    ".woocommerce-product-details__short-description",
                    "[data-section*='desc' i]",
                    "[id*='tabdesc' i]",
                    "[id*='description' i]",
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

                // Layer 3: Heading-anchored discovery (Tailwind / Next.js / React — singular & plural)
                const headings = Array.from(document.querySelectorAll("h1, h2, h3, h4, h5"));
                for (const h of headings) {
                    const txt = (h.innerText || "").trim().toLowerCase();
                    if (/^(descriptions?|product descriptions?|overview|about this item|product details|key features|highlights)$/.test(txt)) {
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

            # 5. Extract Hero Product Gallery-Only images (main product photo + thumbnail strip ONLY;
            # strictly excludes Related Products, Description banners, logos, and other product cards!)
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(0.25)

            gallery_images = await page.evaluate(r"""() => {
                const imgs = [];
                const pickBestSrcset = (srcset) => {
                    if (!srcset) return "";
                    let bestUrl = "";
                    let bestWidth = 0;
                    srcset.split(",").forEach(entry => {
                        const parts = entry.trim().split(/\s+/);
                        const u = parts[0];
                        const w = parts[1] ? parseInt(parts[1].replace(/\D/g, ""), 10) : 0;
                        if (u && u.startsWith("http") && w >= bestWidth) {
                            bestWidth = w;
                            bestUrl = u;
                        }
                    });
                    return bestUrl;
                };

                const isExcluded = (img) => {
                    if (!img) return true;
                    if (img.closest("header, footer, nav, [role='dialog'], [class*='modal' i], [class*='popup' i], .related, .upsells, [class*='related' i], [class*='recommend' i], [class*='recent' i], #tabDescription, #tabSpecification, #tabWarranty, #tab-description, #tab-specification")) {
                        return true;
                    }
                    // Exclude any image inside a fixed overlay (promo popups, chat widgets)
                    let p = img;
                    while (p && p !== document.body) {
                        if (window.getComputedStyle(p).position === "fixed") return true;
                        p = p.parentElement;
                    }
                    // Exclude images inside links to OTHER product pages (related product cards!)
                    const parentLink = img.closest("a[href]");
                    if (parentLink) {
                        const href = (parentLink.getAttribute("href") || "").toLowerCase();
                        if (/\/(product|products|item|p)\//.test(href) && !href.endsWith(".jpg") && !href.endsWith(".jpeg") && !href.endsWith(".png") && !href.endsWith(".webp")) {
                            return true;
                        }
                    }
                    return false;
                };

                const extractSrc = (img) => {
                    let src =
                        img.getAttribute("data-large_image") ||
                        img.getAttribute("data-zoom-image") ||
                        pickBestSrcset(img.getAttribute("srcset")) ||
                        img.getAttribute("data-src") ||
                        img.src || "";
                    // Also check if wrapped in an anchor pointing directly to full-res image
                    const link = img.closest("a[href]");
                    if (link && /\.(jpg|jpeg|png|webp)(\?|$)/i.test(link.href || "")) {
                        src = link.href;
                    }
                    if (!src || !src.startsWith("http") || src.startsWith("data:")) return "";
                    if (/icon|logo|badge|payment|flag|avatar|spinner|placeholder|popup|celebration|anniversary/i.test(src) || src.endsWith(".svg")) return "";
                    return src;
                };

                const getMediaKey = (url) => {
                    try {
                        const decoded = decodeURIComponent(url);
                        const m = decoded.match(/\/([^\/?#]+\.(?:jpg|jpeg|png|webp))/i);
                        return m ? m[1].toLowerCase() : url;
                    } catch {
                        return url;
                    }
                };

                const byKey = new Map();
                const addGalleryImg = (src) => {
                    const key = getMediaKey(src);
                    const isThumb = /\/thumb\/|-\d+x\d+\./i.test(decodeURIComponent(src));
                    if (!byKey.has(key)) {
                        byKey.set(key, { src, isThumb });
                    } else if (byKey.get(key).isThumb && !isThumb) {
                        // Prefer full-res /large/ version over /thumb/ version of the exact same photo!
                        byKey.set(key, { src, isThumb });
                    }
                };

                const collectFromContainer = (container) => {
                    if (!container) return;
                    const els = Array.from(container.querySelectorAll("img"));
                    els.forEach(img => {
                        if (isExcluded(img)) return;
                        const rect = img.getBoundingClientRect();
                        if (rect.width > 0 && rect.width < 36) return;
                        const src = extractSrc(img);
                        if (src) addGalleryImg(src);
                    });
                };

                // Tier 1: Explicit product gallery container (WooCommerce / OpenCart / Shopify / custom)
                const explicitSelectors = [
                    ".woocommerce-product-gallery",
                    ".product-gallery",
                    ".product-images",
                    ".product-image-gallery",
                    ".product-media-gallery",
                    "[data-testid*='gallery' i]"
                ];
                for (const sel of explicitSelectors) {
                    const el = document.querySelector(sel);
                    if (el) {
                        collectFromContainer(el);
                        if (byKey.size > 0) return Array.from(byKey.values()).map(v => v.src);
                    }
                }

                // Tier 2: Tailwind / Next.js Hero Gallery Discovery
                const allImgs = Array.from(document.querySelectorAll("img")).filter(img => {
                    if (isExcluded(img)) return false;
                    const rect = img.getBoundingClientRect();
                    return rect.top >= 0 && rect.top < 780 && rect.width >= 200 && rect.height >= 200;
                });
                allImgs.sort((a, b) => {
                    const ra = a.getBoundingClientRect();
                    const rb = b.getBoundingClientRect();
                    return (rb.width * rb.height) - (ra.width * ra.height);
                });

                if (allImgs.length > 0) {
                    const heroImg = allImgs[0];
                    let galleryRoot = heroImg.parentElement;
                    let cur = heroImg.parentElement;
                    for (let depth = 0; depth < 4 && cur && cur.parentElement; depth++) {
                        const next = cur.parentElement;
                        if (next.querySelector("h1") || next.tagName === "MAIN" || next.tagName === "BODY") {
                            break;
                        }
                        const imgCount = next.querySelectorAll("img").length;
                        if (imgCount >= 1 && imgCount <= 16) {
                            galleryRoot = next;
                        }
                        cur = next;
                    }
                    collectFromContainer(galleryRoot);
                }

                return Array.from(byKey.values()).map(v => v.src);
            }""")

            all_imgs = list(gallery_images)
            for ex in extra_imgs:
                if ex not in all_imgs:
                    all_imgs.append(ex)
            result["image_urls"] = all_imgs

            return result
        except Exception as e:
            print(f"[SiteScraper] Page scraping error on {page_url}: {e}")
            return result
