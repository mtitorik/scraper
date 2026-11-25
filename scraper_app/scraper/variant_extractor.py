import re
import asyncio
from typing import List, Dict, Any, Optional, Set, Tuple
from playwright.async_api import Page, Locator

from ..models.product_models import PricePair, OptionPriceEntry, VariantCombination
from .matcher import parse_price, classify_official_unofficial, extract_region, extract_storage


class VariantExtractor:
    """Clicks through color, storage, official/unofficial, and region variants on a product page
    to extract all pricing, stock status, and variant combinations for Sheet 1 & Sheet 2.
    """

    PRICE_SELECTORS = [
        ".price-new",
        ".special-price",
        ".sale-price",
        ".product-price",
        ".price",
        "[data-price]",
        ".current-price",
        ".regular-price",
        ".price-old",
        "del",
        ".line-through",
    ]

    @classmethod
    async def extract_page_prices(cls, page: Page) -> PricePair:
        """Extracts current Regular and Discounted prices from active page DOM,
        supporting both semantic classes (.price, del, ins) AND Tailwind utility layouts
        (e.g. '৳500 (Cash Price)' + '<del>৳785</del>'), while ignoring EMI, Save/OFF, and Booking figures.
        """
        try:
            prices_info = await page.evaluate(r"""() => {
                let reg = null;
                let disc = null;

                const isSpecTable = (el) => {
                    const tbl = el.closest("table");
                    if (!tbl) return false;
                    if (tbl.closest("#tabSpecification, #tab-specification, #specification, .specifications, .woocommerce-product-attributes")) return true;
                    if (tbl.classList.contains("data-table") || tbl.classList.contains("specs")) return true;
                    return tbl.querySelectorAll("tr").length >= 6;
                };

                const isExcludedAncestor = (el, allowBelowFold) => {
                    if (!el) return true;
                    if (el.closest("header, footer, nav, aside, .sidebar, .widget, .product_list_widget, [class*='sidebar' i], [role='dialog'], .related, .upsells, .p-s-item, .wd-product, .wd-products, .wd-dropdown, .product-grid-item, .product-card, .product-thumb, .product-layout, [class*='related' i], [class*='similar' i], [class*='upsell' i], [class*='recommend' i], #tabDescription, #tabWarranty, #tabSpecification")) return true;
                    if (isSpecTable(el)) return true;
                    const rect = el.getBoundingClientRect();
                    if (rect.width === 0 && rect.height === 0) return true;
                    if (!allowBelowFold && (rect.top < 0 || rect.top > 860)) return true;
                    return false;
                };

                const isNoiseText = (txt) => {
                    const lower = (txt || "").toLowerCase();
                    return /\b(emi|\/mo|\/month|per month|installment|booking|advance|save\b|off\b|orders above)\b/.test(lower);
                };

                const isNoisePrice = (el, allowBelowFold) => {
                    if (isExcludedAncestor(el, allowBelowFold)) return true;
                    const own = (el.innerText || "").trim();
                    if (!own || !/\d/.test(own)) return true;
                    if (isNoiseText(own)) return true;
                    // Check direct parent only if parent is small (avoids rejecting a valid price inside a large container that also has an OFF badge)
                    const parentTxt = el.parentElement ? (el.parentElement.innerText || "").trim() : "";
                    if (parentTxt.length < 60 && isNoiseText(parentTxt)) return true;
                    return false;
                };

                // Prefer explicit product-summary roots (e.g., WooCommerce .entry-summary, OpenCart .product-info-table)
                // so tall galleries pushing price below y=860 (like anker.com.bd) are never skipped or shadowed by sidebars!
                const summaryRoot = document.querySelector(
                    ".summary.entry-summary, .entry-summary, .product-summary, .elementor-widget-woocommerce-product-price, .wd-single-price, .product-info-table, .product-essential, .product-short-info"
                );
                const root = summaryRoot || document;
                const allowBelowFold = !!summaryRoot;

                const findValid = (selector, searchRoot = root, belowFold = allowBelowFold) => {
                    const els = Array.from(searchRoot.querySelectorAll(selector));
                    for (const el of els) {
                        if (!isNoisePrice(el, belowFold)) return el;
                    }
                    return null;
                };

                const PRICE_TOKEN_RE = /(?:[৳$£€]|tk\.?|bdt)\s*[\d,]+(?:\.\d{2})?|[\d,]+(?:\.\d{2})?\s*(?:[৳$£€]|tk\.?|bdt)\b/i;

                // 1. Check struck-through regular price (<del>, .price-old, .line-through)
                let delElem = findValid("del, .price-old, .old-price, .line-through, .original-price");
                let saleElem = findValid("ins, .special-price, .price-new, .sale-price, .discount-price, .current-price, .product__sale_price");
                if (!delElem && summaryRoot) {
                    delElem = findValid("del, .price-old, .old-price, .line-through, .original-price", document, false);
                }
                if (!saleElem && summaryRoot) {
                    saleElem = findValid("ins, .special-price, .price-new, .sale-price, .discount-price, .current-price, .product__sale_price", document, false);
                }

                // 2. Tailwind-aware lookup: if <del> exists but no semantic sale class, look in nearby price wrapper for bold currency text
                if (delElem && !saleElem) {
                    const wrapper = delElem.closest("div.group, div.flex, section") || delElem.parentElement?.parentElement;
                    if (wrapper) {
                        const candidates = Array.from(wrapper.querySelectorAll("p, span, strong, b, div")).filter(el => {
                            if (el === delElem || el.contains(delElem) || delElem.contains(el)) return false;
                            if (el.children.length > 1) return false;
                            const txt = (el.innerText || "").trim();
                            return PRICE_TOKEN_RE.test(txt) && txt.length <= 30 && !isNoiseText(txt);
                        });
                        if (candidates.length > 0) saleElem = candidates[0];
                    }
                }

                if (delElem && saleElem) {
                    reg = delElem.innerText;
                    disc = saleElem.innerText;
                } else if (delElem) {
                    reg = delElem.innerText;
                    const pElem = findValid(".price, .product-price, .product__price");
                    if (pElem && pElem !== delElem) disc = pElem.innerText;
                } else if (saleElem) {
                    reg = saleElem.innerText;
                } else {
                    const pElem = findValid(".price, .product-price, .product__price, .price-new, .current-price, [data-price]");
                    if (pElem) {
                        reg = pElem.innerText;
                    } else {
                        // 3. Universal hero price fallback (supports '৳650', 'Tk. 22,999', '<b>৳82,500</b>', and sibling regular/sale pairs!)
                        const heroPrices = Array.from(document.querySelectorAll("main p, main span, main strong, main b, section p, section span, section b, div p, div span, div b")).filter(el => {
                            if (isExcludedAncestor(el, false)) return false;
                            if (el.children.length > 1) return false;
                            const txt = (el.innerText || "").trim();
                            if (!PRICE_TOKEN_RE.test(txt)) return false;
                            if (txt.length > 35 || isNoiseText(txt)) return false;
                            const style = window.getComputedStyle(el);
                            const fontSize = parseFloat(style.fontSize) || 14;
                            const fontWeight = parseInt(style.fontWeight, 10) || 400;
                            return fontSize >= 16 || fontWeight >= 600;
                        });
                        if (heroPrices.length > 0) {
                            const primary = heroPrices[0];
                            reg = primary.innerText;
                            // Check if a sibling inside the exact same parent holds a struck-through or higher regular price (e.g. Gadget&Gear 'Tk. 22,999' + 'Tk. 23,999')
                            if (primary.parentElement) {
                                const siblings = Array.from(primary.parentElement.querySelectorAll("span, p, del, s, b, strong")).filter(s => {
                                    if (s === primary || s.contains(primary) || primary.contains(s)) return false;
                                    if (s.children.length > 1) return false;
                                    const t = (s.innerText || "").trim();
                                    return PRICE_TOKEN_RE.test(t) && t.length <= 30 && !isNoiseText(t);
                                });
                                if (siblings.length > 0) {
                                    disc = primary.innerText;
                                    reg = siblings[0].innerText;
                                }
                            }
                        }
                    }
                }
                return { reg, disc };
            }""")

            reg_val = parse_price(prices_info.get("reg"))
            disc_val = parse_price(prices_info.get("disc"))

            # If reg_val and disc_val are reversed (e.g., sale was picked as reg)
            if reg_val and disc_val and disc_val > reg_val:
                reg_val, disc_val = disc_val, reg_val

            # If only disc was found, make it reg
            if not reg_val and disc_val:
                reg_val = disc_val
                disc_val = None

            return PricePair(regular=reg_val, discounted=disc_val)
        except Exception:
            return PricePair()

    @classmethod
    async def extract_variant_groups(cls, page: Page) -> Dict[str, List[Dict[str, Any]]]:
        """Scans page for interactive variant options (Color, Storage, Official/Unofficial, Region, etc.)."""
        try:
            groups = await page.evaluate(r"""() => {
                const result = {};
                
                // Selectors for option blocks
                const containers = document.querySelectorAll(
                    ".product-options, .variations, .attribute-swatches, .option-group, .variant-picker, [data-option-group], .attributes, .product-variant"
                );

                const rgbToColorName = (bg) => {
                    if (!bg) return "";
                    const m = bg.match(/rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i);
                    if (!m) return "";
                    const r = parseInt(m[1], 10), g = parseInt(m[2], 10), b = parseInt(m[3], 10);
                    if (r < 45 && g < 45 && b < 45) return "Black";
                    if (r > 220 && g > 220 && b > 220) return "White";
                    if (Math.abs(r - g) < 18 && Math.abs(g - b) < 18) {
                        return r > 175 ? "Silver" : (r > 100 ? "Gray" : "Dark Gray");
                    }
                    if (r > 180 && g < 90 && b < 90) return "Red";
                    if (r > 200 && g > 140 && b < 90) return "Gold";
                    if (r > 190 && g > 100 && b > 140) return "Pink";
                    if (g > r + 25 && g > b + 20) return "Green";
                    if (b > r + 25 && b > g + 15) return "Blue";
                    if (r > 120 && b > 120 && g < 110) return "Purple";
                    if (r > 200 && g > 180 && b < 100) return "Yellow";
                    return `rgb(${r},${g},${b})`;
                };

                const extractBtnLabel = (btn, heading) => {
                    let lbl = (btn.getAttribute("data-value") || btn.getAttribute("title") || btn.getAttribute("aria-label") || btn.innerText || "").trim();
                    if (!lbl && /color|colour/i.test(heading || "")) {
                        const swatch = btn.querySelector("span[style*='background'], div[style*='background']") || btn;
                        const bg = window.getComputedStyle(swatch).backgroundColor || "";
                        lbl = rgbToColorName(bg);
                    }
                    return lbl;
                };

                const processBlock = (heading, buttons) => {
                    if (!heading || !buttons || buttons.length === 0) return;
                    const cleanHead = heading.toLowerCase().replace(/[:*]/g, '').trim();
                    if (!result[cleanHead]) result[cleanHead] = [];
                    
                    buttons.forEach((btn, idx) => {
                        let label = extractBtnLabel(btn, cleanHead);
                        if (!label) return;
                        // Ensure duplicate color names (e.g. two shades of Gray) remain distinguishable
                        if (result[cleanHead].some(x => x.label === label)) {
                            label = `${label} ${idx + 1}`;
                        }
                        const isOOS = btn.classList.contains("disabled") || btn.classList.contains("out-of-stock") || btn.disabled || /out of stock/i.test(btn.innerText);
                        const isSelected = btn.classList.contains("selected") || btn.classList.contains("active") || btn.classList.contains("current");
                        const swatchKey = `sw_${cleanHead.replace(/[^a-z0-9]/g, '')}_${idx}`;
                        btn.setAttribute("data-scraper-opt", swatchKey);
                        result[cleanHead].push({
                            label: label,
                            is_oos: !!isOOS,
                            is_selected: !!isSelected,
                            selector: `[data-scraper-opt="${swatchKey}"]`,
                            index: idx
                        });
                    });
                };

                // Pattern A: standard container with labels
                containers.forEach(cont => {
                    const labelElem = cont.querySelector("label, .option-title, .attribute-name, h4, h5");
                    const heading = labelElem ? labelElem.innerText : "option";
                    const btns = Array.from(cont.querySelectorAll("button, a.swatch, .swatch-element, input[type='radio'] + label, .variant-option"));
                    processBlock(heading, btns);
                });

                // Pattern B: Look for buttons or pills grouped by attributes
                if (Object.keys(result).length === 0) {
                    const allSwatches = Array.from(document.querySelectorAll("button.swatch, .color-swatch, .storage-option, .region-option, .variant-btn"));
                    if (allSwatches.length > 0) {
                        result["variant"] = allSwatches.map((b, idx) => ({
                            label: (b.getAttribute("title") || b.innerText).trim(),
                            is_oos: b.disabled || b.classList.contains("out-of-stock"),
                            is_selected: b.classList.contains("active"),
                            selector: null,
                            index: idx
                        }));
                    }
                }

                // Pattern C: Standard <select> dropdowns (WooCommerce/Shopify variations)
                const selects = Array.from(document.querySelectorAll(".variations select, .product-options select, form.cart select, select[name*='attribute' i]"));
                selects.forEach(sel => {
                    const labelEl = sel.closest("tr, .form-group, div")?.querySelector("label");
                    const rawHead = (labelEl ? labelEl.innerText : (sel.getAttribute("name") || "option")).replace(/^attribute_pa_|^attribute_/i, "");
                    const cleanHead = rawHead.toLowerCase().replace(/[:*_-]/g, " ").trim() || "option";
                    const opts = Array.from(sel.options).filter(o => o.value && !/choose|select/i.test(o.text));
                    if (opts.length > 0) {
                        if (!result[cleanHead]) result[cleanHead] = [];
                        opts.forEach((o, idx) => {
                            const lbl = o.text.trim();
                            if (lbl && !result[cleanHead].some(x => x.label === lbl)) {
                                result[cleanHead].push({
                                    label: lbl,
                                    is_oos: o.disabled,
                                    is_selected: o.selected,
                                    is_select_option: true,
                                    select_name: sel.getAttribute("name") || "",
                                    option_value: o.value,
                                    selector: null,
                                    index: idx
                                });
                            }
                        });
                    }
                });

                // Pattern D: Tailwind / label-anchored variant cards (e.g. <p>Size:</p> + sibling div of <button>1m</button><button>2m</button>)
                const VARIANT_LABEL_RE = /^(size|length|color|colour|storage|capacity|ram|memory|region|country|version|type|warranty|official|unofficial|sim|connectivity|edition|chip|band|strap|model|option|variant)s?\s*:?$/i;
                const ACTION_BTN_RE = /^(add to cart|shop now|buy now|order now|messenger|whatsapp|compare|wishlist|\+|\-|\d+)$/i;
                const labelNodes = Array.from(document.querySelectorAll("p, label, span, h4, h5, div"));
                labelNodes.forEach(node => {
                    if (node.closest("header, footer, nav, #tabDescription, #tabSpecification, table")) return;
                    if (node.children.length > 2) return;
                    const rawTxt = (node.innerText || "").trim();
                    if (!rawTxt || rawTxt.length > 35 || !VARIANT_LABEL_RE.test(rawTxt)) return;

                    const heading = rawTxt.replace(/[:*]/g, "").trim().toLowerCase();
                    const nextSib = node.nextElementSibling;
                    const container = (nextSib && !["BUTTON", "A", "INPUT", "SPAN"].includes(nextSib.tagName))
                        ? nextSib
                        : node.parentElement;
                    if (!container) return;
                    const btns = Array.from(container.querySelectorAll("button, a[role='button']")).filter(b => {
                        const lbl = extractBtnLabel(b, heading);
                        return lbl && lbl.length <= 40 && !ACTION_BTN_RE.test(lbl);
                    });
                    if (btns.length >= 2) {
                        processBlock(heading, btns);
                    }
                });

                return result;
            }""")
            return groups or {}
        except Exception as e:
            print(f"[VariantExtractor] Warning extracting variant groups: {e}")
            return {}

    @classmethod
    async def _extract_woocommerce_variations_json(
        cls,
        page: Page,
        product_name: str,
        source_website: str,
        page_link: str,
        default_price: PricePair,
    ) -> Optional[Tuple[PricePair, Dict[str, List[OptionPriceEntry]], List[VariantCombination], Set[str]]]:
        """Fast, 100%-exact extractor for WooCommerce multi-axis variable products via
        form.variations_form[data-product_variations] (avoids stuck range prices when
        multiple attributes like Color + Storage + Region must be selected together).
        """
        try:
            raw_vars = await page.evaluate(r"""() => {
                const form = document.querySelector("form.variations_form[data-product_variations]");
                if (!form) return null;
                try {
                    const parsed = JSON.parse(form.getAttribute("data-product_variations") || "[]");
                    if (!Array.isArray(parsed) || parsed.length < 2) return null;
                    // Also collect human-readable labels from <select> options if present
                    const labelMap = {};
                    form.querySelectorAll("select[name]").forEach(sel => {
                        const name = sel.getAttribute("name") || "";
                        labelMap[name] = {};
                        Array.from(sel.options).forEach(o => {
                            if (o.value) labelMap[name][o.value.toLowerCase()] = o.text.trim();
                        });
                    });
                    return { variations: parsed, labelMap };
                } catch {
                    return null;
                }
            }""")
            if not raw_vars or not raw_vars.get("variations"):
                return None

            variations = raw_vars["variations"]
            label_map = raw_vars.get("labelMap") or {}
            extra_images: Set[str] = set()
            variant_combinations: List[VariantCombination] = []
            # Track lowest active price per (normalized_cat, label) for Sheet 1 columns
            option_best: Dict[str, Dict[str, PricePair]] = {}

            def _norm_cat(raw_attr_key: str) -> str:
                clean = re.sub(r"^attribute_(pa_)?", "", raw_attr_key, flags=re.IGNORECASE)
                clean = clean.replace("-", " ").replace("_", " ").strip().lower()
                if any(k in clean for k in ["color", "colour", "swatch"]):
                    return "colour"
                if any(k in clean for k in ["storage", "capacity", "rom"]):
                    return "storage"
                if any(k in clean for k in ["official", "warranty", "type"]):
                    return "official/unofficial"
                if any(k in clean for k in ["region", "country"]):
                    return "region"
                return clean or "variant"

            for v in variations:
                attrs = v.get("attributes") or {}
                reg_raw = v.get("display_regular_price")
                sale_raw = v.get("display_price")
                reg_int = int(round(float(reg_raw))) if reg_raw not in (None, "") else None
                sale_int = int(round(float(sale_raw))) if sale_raw not in (None, "") else None
                if reg_int is not None and sale_int is not None:
                    if sale_int < reg_int:
                        pp = PricePair(regular=reg_int, discounted=sale_int)
                    else:
                        pp = PricePair(regular=reg_int, discounted=None)
                elif sale_int is not None:
                    pp = PricePair(regular=sale_int, discounted=None)
                else:
                    pp = default_price

                in_stock = bool(v.get("is_in_stock", True))
                img_obj = v.get("image") or {}
                full_src = img_obj.get("full_src") or img_obj.get("url") or ""
                if isinstance(full_src, str) and full_src.startswith("http"):
                    extra_images.add(full_src)

                official_type = classify_official_unofficial(product_name)
                region = extract_region(product_name)
                storage = extract_storage(product_name)
                color = "not found"
                extra_attrs: Dict[str, str] = {}

                for attr_k, attr_v in attrs.items():
                    if not attr_v:
                        continue
                    cat = _norm_cat(attr_k)
                    # Resolve human label from select options if available
                    lbl = (label_map.get(attr_k) or {}).get(str(attr_v).lower(), str(attr_v).replace("-", " ").strip())
                    if not lbl:
                        continue

                    if cat == "colour":
                        color = lbl
                    elif cat == "storage":
                        storage = lbl
                    elif cat == "region":
                        region = lbl
                    elif cat == "official/unofficial":
                        official_type = lbl
                    else:
                        extra_attrs[cat] = lbl

                    # Keep representative price per option (prefer in-stock lowest active price)
                    if cat not in option_best:
                        option_best[cat] = {}
                    prev = option_best[cat].get(lbl)
                    cur_active = pp.discounted or pp.regular or 10**9
                    prev_active = (prev.discounted or prev.regular or 10**9) if prev else 10**9
                    if prev is None or (in_stock and cur_active < prev_active):
                        option_best[cat][lbl] = pp

                variant_combinations.append(VariantCombination(
                    product_name=product_name,
                    source_website=source_website,
                    page_link=page_link,
                    official_type=official_type,
                    region=region,
                    storage=storage,
                    color=color,
                    extra_attributes=extra_attrs,
                    prices=pp,
                    stock_status="In Stock" if (in_stock and pp.regular) else "Out of Stock",
                ))

            attribute_options: Dict[str, List[OptionPriceEntry]] = {
                cat: [OptionPriceEntry(label=lbl, prices=pp) for lbl, pp in opts.items()]
                for cat, opts in option_best.items()
                if opts
            }
            if not attribute_options:
                return None

            # Ensure default_price is populated if hero range price was missing
            if default_price.regular is None and variant_combinations:
                default_price = variant_combinations[0].prices

            return default_price, attribute_options, variant_combinations, extra_images
        except Exception:
            return None

    @classmethod
    async def extract_all_variants_and_combos(
        cls,
        page: Page,
        product_name: str,
        source_website: str,
        page_link: str,
        pause_event: Optional[asyncio.Event] = None,
        stop_event: Optional[asyncio.Event] = None,
        throttle_callback: Optional[Any] = None,
    ) -> Tuple[PricePair, Dict[str, List[OptionPriceEntry]], List[VariantCombination], Set[str]]:
        """Clicks through variants, returns (default_price, attribute_options, variant_combinations, extra_image_urls)."""
        extra_images: Set[str] = set()
        attribute_options: Dict[str, List[OptionPriceEntry]] = {}
        variant_combinations: List[VariantCombination] = []

        # 1. Base / Default price
        default_price = await cls.extract_page_prices(page)

        # 1b. Fast & exact WooCommerce variation matrix path (handles multi-axis Color x Storage x Region cleanly!)
        woo_res = await cls._extract_woocommerce_variations_json(
            page=page,
            product_name=product_name,
            source_website=source_website,
            page_link=page_link,
            default_price=default_price,
        )
        if woo_res is not None:
            return woo_res

        # 2. Extract options on page
        groups = await cls.extract_variant_groups(page)

        if not groups:
            # Single product with no in-page buttons
            single_combo = VariantCombination(
                product_name=product_name,
                source_website=source_website,
                page_link=page_link,
                official_type=classify_official_unofficial(product_name),
                region=extract_region(product_name),
                storage=extract_storage(product_name),
                color="not found",
                prices=default_price,
                stock_status="In Stock" if default_price.regular else "Out of Stock",
            )
            return default_price, attribute_options, [single_combo], extra_images

        # Normalize group names into: colour, storage, official/unofficial, region, or custom
        normalized_groups: Dict[str, List[Dict[str, Any]]] = {}
        for raw_name, items in groups.items():
            norm_name = raw_name.lower().strip()
            if any(k in norm_name for k in ["color", "colour", "swatch"]):
                key = "colour"
            elif any(k in norm_name for k in ["storage", "capacity", "rom"]):
                key = "storage"
            elif any(k in norm_name for k in ["official", "warranty", "type"]):
                key = "official/unofficial"
            elif any(k in norm_name for k in ["region", "country"]):
                key = "region"
            else:
                key = norm_name
            normalized_groups[key] = items

        # Iterate through options to capture individual option pricing and combinations
        for cat_name, items in normalized_groups.items():
            if cat_name not in attribute_options:
                attribute_options[cat_name] = []

            for item in items:
                label = item.get("label", "").strip()
                if not label:
                    continue

                if stop_event and stop_event.is_set():
                    break
                if pause_event:
                    await pause_event.wait()
                if throttle_callback:
                    await throttle_callback()

                # Try clicking this option button (skip click if already active/selected!)
                price_for_item = default_price
                is_oos = item.get("is_oos", False)

                if not item.get("is_selected"):
                    try:
                        # Handle <select> dropdown variants OR clickable button/swatch variants
                        if item.get("is_select_option") and item.get("select_name") is not None:
                            clicked = await page.evaluate(r"""({selName, optVal}) => {
                                const sel = selName
                                    ? document.querySelector(`select[name="${selName}"]`)
                                    : document.querySelector(".variations select, .product-options select, form.cart select");
                                if (!sel) return false;
                                sel.value = optVal;
                                sel.dispatchEvent(new Event("change", { bubbles: true }));
                                return true;
                            }""", {"selName": item.get("select_name"), "optVal": item.get("option_value")})
                        else:
                            clicked = False
                            # 1. Prefer exact tagged selector from extract_variant_groups (works for textless color circles too!)
                            opt_sel = item.get("selector")
                            if opt_sel:
                                try:
                                    opt_loc = page.locator(opt_sel).first
                                    await opt_loc.scroll_into_view_if_needed(timeout=600)
                                    if await opt_loc.is_visible(timeout=300):
                                        await opt_loc.click(timeout=1200)
                                        clicked = True
                                except Exception:
                                    clicked = False

                            # 2. Prefer Playwright's native mouse click by role/name
                            if not clicked:
                                try:
                                    btn_loc = page.get_by_role("button", name=label, exact=True).first
                                    await btn_loc.scroll_into_view_if_needed(timeout=600)
                                    if await btn_loc.is_visible(timeout=300):
                                        await btn_loc.click(timeout=1200)
                                        clicked = True
                                except Exception:
                                    clicked = False

                            if not clicked:
                                clicked = await page.evaluate(r"""(label) => {
                                    const target = label.toLowerCase();
                                    const selectorOrder = [
                                        "button",
                                        "a[role='button'], a.swatch, .swatch-element",
                                        "input[type='radio'] + label, label",
                                        "span, div"
                                    ];
                                    for (const sel of selectorOrder) {
                                        const candidates = Array.from(document.querySelectorAll(sel));
                                        for (const el of candidates) {
                                            if (el.closest("header, footer, nav")) continue;
                                            const txt = (el.innerText || "").trim().toLowerCase();
                                            const titleAttr = (el.getAttribute("title") || "").trim().toLowerCase();
                                            const valAttr = (el.getAttribute("data-value") || "").trim().toLowerCase();
                                            if (txt === target || titleAttr === target || valAttr === target) {
                                                const clickTarget = el.closest("button, a, label") || el;
                                                clickTarget.scrollIntoView({ block: "nearest" });
                                                clickTarget.click();
                                                return true;
                                            }
                                        }
                                    }
                                    return false;
                                }""", label)

                        if clicked:
                            # Smart fast polling (150ms x 3) instead of blind 800ms sleep
                            prev_sig = (default_price.regular, default_price.discounted)
                            for _ in range(3):
                                await asyncio.sleep(0.15)
                                candidate_price = await cls.extract_page_prices(page)
                                price_for_item = candidate_price
                                if (candidate_price.regular, candidate_price.discounted) != prev_sig:
                                    break

                            # Capture any updated gallery image src
                            new_img = await page.evaluate(r"""() => {
                                const mainImg = document.querySelector(".product-gallery img, .product-image img, #main-image, [data-zoom-image]");
                                return mainImg ? (mainImg.getAttribute("data-zoom-image") || mainImg.src) : null;
                            }""")
                            if new_img and new_img.startswith("http"):
                                extra_images.add(new_img)
                    except Exception:
                        pass

                # If out of stock and price is 0 or hidden, price_for_item stays None (which renders as 'not found')
                if is_oos and (not price_for_item.regular or price_for_item.regular == 0):
                    price_for_item = PricePair(regular=None, discounted=None)

                # Add to attribute_options for Sheet 1
                attribute_options[cat_name].append(OptionPriceEntry(label=label, prices=price_for_item))

                # Also add to VariantCombination for Sheet 2
                combo = VariantCombination(
                    product_name=product_name,
                    source_website=source_website,
                    page_link=page_link,
                    official_type=label if cat_name == "official/unofficial" else classify_official_unofficial(label),
                    region=label if cat_name == "region" else extract_region(label),
                    storage=label if cat_name == "storage" else extract_storage(label),
                    color=label if cat_name == "colour" else "not found",
                    extra_attributes={cat_name: label} if cat_name not in ["colour", "storage", "official/unofficial", "region"] else {},
                    prices=price_for_item,
                    stock_status="Out of Stock" if is_oos else ("In Stock" if price_for_item.regular else "Out of Stock"),
                )
                variant_combinations.append(combo)

        return default_price, attribute_options, variant_combinations, extra_images
