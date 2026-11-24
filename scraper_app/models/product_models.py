from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any


@dataclass
class PricePair:
    regular: Optional[int] = None
    discounted: Optional[int] = None

    def regular_display(self) -> str:
        return str(self.regular) if self.regular is not None else "not found"

    def discounted_display(self) -> str:
        return str(self.discounted) if self.discounted is not None else ""

    def has_discount(self) -> bool:
        return self.discounted is not None and self.discounted > 0 and (
            self.regular is None or self.discounted < self.regular
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "regular": self.regular,
            "discounted": self.discounted,
            "regular_display": self.regular_display(),
            "discounted_display": self.discounted_display(),
        }


@dataclass
class OptionPriceEntry:
    label: str
    prices: PricePair = field(default_factory=PricePair)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "prices": self.prices.to_dict(),
        }


@dataclass
class VariantCombination:
    product_name: str
    source_website: str = ""
    page_link: str = ""
    official_type: str = "not found"  # Official / Unofficial
    region: str = "not found"
    storage: str = "not found"
    color: str = "not found"
    extra_attributes: Dict[str, str] = field(default_factory=dict)
    prices: PricePair = field(default_factory=PricePair)
    stock_status: str = "In Stock"  # "In Stock" / "Out of Stock" / "Upcoming"

    def to_row_dict(self) -> Dict[str, Any]:
        extra_str = "; ".join(f"{k}: {v}" for k, v in sorted(self.extra_attributes.items())) if self.extra_attributes else "-"
        return {
            "Product name": self.product_name,
            "Source Website": self.source_website or "-",
            "Page Link": self.page_link or "-",
            "Official/Unofficial": self.official_type,
            "Region": self.region,
            "Storage": self.storage,
            "Colour": self.color,
            "Extra Attributes": extra_str,
            "Regular Price": self.prices.regular_display(),
            "Discounted Price": self.prices.discounted_display() or "-",
            "Stock Status": self.stock_status,
        }


@dataclass
class ProductRecord:
    product_name: str
    page_links: List[str] = field(default_factory=list)
    image_folder: str = ""
    default_price: PricePair = field(default_factory=PricePair)
    # attribute_options maps normalized category -> list of OptionPriceEntry
    # e.g., "colour" -> [OptionPriceEntry("Black", PricePair(120000, 115000)), OptionPriceEntry("White", ...)]
    # "official/unofficial" -> [OptionPriceEntry("Official", ...), OptionPriceEntry("Unofficial", ...)]
    # "region" -> [OptionPriceEntry("USA", ...), OptionPriceEntry("SG", ...)]
    # "storage" -> [OptionPriceEntry("128GB", ...), OptionPriceEntry("256GB", ...)]
    attribute_options: Dict[str, List[OptionPriceEntry]] = field(default_factory=dict)
    extra_fields: Dict[str, str] = field(default_factory=dict)  # e.g. "Warranty": "1 Year Apple Care"
    specifications: str = "not found"
    description_html: str = "not found"
    status: str = "Pending"  # "Pending", "In Progress", "Partial", "Done", "Not Found"
    variant_combinations: List[VariantCombination] = field(default_factory=list)
    scraped_sources: List[str] = field(default_factory=list)
    error_message: str = ""

    def add_page_link(self, link: str):
        if link and link not in self.page_links:
            self.page_links.append(link)

    def get_combined_page_links(self) -> str:
        if not self.page_links:
            return "not found"
        return " | ".join(self.page_links)

    def to_summary_dict(self) -> Dict[str, Any]:
        return {
            "product_name": self.product_name,
            "page_links": self.page_links,
            "image_folder": self.image_folder,
            "default_price": self.default_price.to_dict(),
            "status": self.status,
            "specifications": self.specifications[:120] + "..." if len(self.specifications) > 120 else self.specifications,
            "description_html_len": len(self.description_html),
            "variant_count": len(self.variant_combinations),
            "sources": self.scraped_sources,
        }
