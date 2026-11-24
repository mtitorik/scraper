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
        """Extracts current Regular and Discounted prices from active page DOM."""
        try:
            prices_info = await page.evaluate(r"""() => {
                let reg = null;
                let disc = null;

                // Look for common e-commerce price patterns
                const delElem = document.querySelector("del, .price-old, .old-price, .line-through, .original-price");
                const saleElem = document.querySelector(".special-price, .price-new, .sale-price, .discount-price, .current-price");

                if (delElem && saleElem) {
                    reg = delElem.innerText;
                    disc = saleElem.innerText;
                } else if (delElem) {
                    reg = delElem.innerText;
                    const pElem = document.querySelector(".price, .product-price");
                    if (pElem && pElem !== delElem) disc = pElem.innerText;
                } else {
                    const priceElems = Array.from(document.querySelectorAll(".price, .product-price, .price-new, .current-price, [data-price]"));
                    for (const el of priceElems) {
                        const txt = el.innerText.trim();
                        if (txt && /\d/.test(txt)) {
                            reg = txt;
                            break;
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
                    # Find and click element matching label
                    clicked = await page.evaluate(r"""(label) => {
                        const candidates = Array.from(document.querySelectorAll("button, a, .swatch, label, span, div"));
                        for (const el of candidates) {
                            if (el.innerText.trim().toLowerCase() === label.toLowerCase() ||
                                el.getAttribute("title")?.trim().toLowerCase() === label.toLowerCase() ||
                                el.getAttribute("data-value")?.trim().toLowerCase() === label.toLowerCase()) {
                                el.scrollIntoView({ block: "nearest" });
                                el.click();
                                return true;
                            }
                        }
                        return false;
                    }""", label)

                    if clicked:
                        await asyncio.sleep(0.35)
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
