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

                const isExcludedAncestor = (el) => {
                    return !el || Boolean(el.closest("header, footer, nav, .related, .upsells, [class*='related' i], #tabDescription, #tabWarranty, table"));
                };

                const isNoiseText = (txt) => {
                    const lower = (txt || "").toLowerCase();
                    return /\b(emi|\/mo|\/month|per month|installment|booking|advance|save\b|off\b|orders above)\b/.test(lower);
                };

                const isNoisePrice = (el) => {
                    if (isExcludedAncestor(el)) return true;
                    const own = (el.innerText || "").trim();
                    if (!own || !/\d/.test(own)) return true;
                    if (isNoiseText(own)) return true;
                    // Check direct parent only if parent is small (avoids rejecting a valid price inside a large container that also has an OFF badge)
                    const parentTxt = el.parentElement ? (el.parentElement.innerText || "").trim() : "";
                    if (parentTxt.length < 60 && isNoiseText(parentTxt)) return true;
                    return false;
                };

                const findValid = (selector) => {
                    const els = Array.from(document.querySelectorAll(selector));
                    for (const el of els) {
                        if (!isNoisePrice(el)) return el;
                    }
                    return null;
                };

                // 1. Check struck-through regular price (<del>, .price-old, .line-through)
                const delElem = findValid("del, .price-old, .old-price, .line-through, .original-price");
                let saleElem = findValid("ins, .special-price, .price-new, .sale-price, .discount-price, .current-price");

                // 2. Tailwind-aware lookup: if <del> exists but no semantic sale class, look in nearby price wrapper for bold currency text
                if (delElem && !saleElem) {
                    const wrapper = delElem.closest("div.group, div.flex, section") || delElem.parentElement?.parentElement;
                    if (wrapper) {
                        const candidates = Array.from(wrapper.querySelectorAll("p, span, strong, b, div")).filter(el => {
                            if (el === delElem || el.contains(delElem) || delElem.contains(el)) return false;
                            if (el.children.length > 1) return false;
                            const txt = (el.innerText || "").trim();
                            return /^[৳$£€]?\s*[\d,]+(?:\.\d{2})?(\s*(tk|bdt))?$/i.test(txt) && !isNoiseText(txt);
                        });
                        if (candidates.length > 0) saleElem = candidates[0];
                    }
                }

                if (delElem && saleElem) {
                    reg = delElem.innerText;
                    disc = saleElem.innerText;
                } else if (delElem) {
                    reg = delElem.innerText;
                    const pElem = findValid(".price, .product-price");
                    if (pElem && pElem !== delElem) disc = pElem.innerText;
                } else {
                    const pElem = findValid(".price, .product-price, .price-new, .current-price, [data-price]");
                    if (pElem) {
                        reg = pElem.innerText;
                    } else {
                        // 3. Tailwind-aware hero price fallback (e.g. '৳650' next to '(Cash Price)' with no <del> and no .price class)
                        const heroPrices = Array.from(document.querySelectorAll("main p, main span, main strong, section p, section span, div p, div span")).filter(el => {
                            if (isExcludedAncestor(el)) return false;
                            if (el.children.length > 1) return false;
                            const txt = (el.innerText || "").trim();
                            if (!/[৳$£€]\s*[\d,]+|[\d,]+\s*(tk|bdt)\b/i.test(txt)) return false;
                            if (txt.length > 35 || isNoiseText(txt)) return false;
                            const style = window.getComputedStyle(el);
                            const fontSize = parseFloat(style.fontSize) || 14;
                            const fontWeight = parseInt(style.fontWeight, 10) || 400;
                            return fontSize >= 17 || fontWeight >= 600;
                        });
                        if (heroPrices.length > 0) {
                            reg = heroPrices[0].innerText;
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

                const processBlock = (heading, buttons) => {
                    if (!heading || !buttons || buttons.length === 0) return;
                    const cleanHead = heading.toLowerCase().replace(/[:*]/g, '').trim();
                    if (!result[cleanHead]) result[cleanHead] = [];
                    
                    buttons.forEach((btn, idx) => {
                        const label = (btn.getAttribute("data-value") || btn.getAttribute("title") || btn.innerText || "").trim();
                        const isOOS = btn.classList.contains("disabled") || btn.classList.contains("out-of-stock") || btn.disabled || /out of stock/i.test(btn.innerText);
                        const isSelected = btn.classList.contains("selected") || btn.classList.contains("active") || btn.classList.contains("current");
                        if (label && !result[cleanHead].some(x => x.label === label)) {
                            result[cleanHead].push({
                                label: label,
                                is_oos: !!isOOS,
                                is_selected: !!isSelected,
                                selector: btn.getAttribute("id") ? `#${btn.getAttribute("id")}` : null,
                                index: idx
                            });
                        }
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
                    const container = node.nextElementSibling || node.parentElement;
                    if (!container) return;
                    const btns = Array.from(container.querySelectorAll("button, a[role='button']")).filter(b => {
                        const lbl = (b.getAttribute("data-value") || b.getAttribute("title") || b.innerText || "").trim();
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

                # Try clicking this option button
                price_for_item = default_price
                is_oos = item.get("is_oos", False)

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
                        # Prefer Playwright's native mouse click first (scrolls cleanly into view & triggers React/Next.js state)
                        try:
                            btn_loc = page.get_by_role("button", name=label, exact=True).first
                            await btn_loc.scroll_into_view_if_needed(timeout=1000)
                            if await btn_loc.is_visible(timeout=500):
                                await btn_loc.click(timeout=2000)
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
                        await asyncio.sleep(0.8)
                        price_for_item = await cls.extract_page_prices(page)

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
