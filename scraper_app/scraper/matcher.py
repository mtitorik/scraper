import re
from typing import Optional, List, Tuple


ACCESSORY_KEYWORDS = [
    "case",
    "cover",
    "glass",
    "protector",
    "cable",
    "charger",
    "adapter",
    "strap",
    "band",
    "pouch",
    "sleeve",
    "stand",
    "skin",
    "film",
    "lens",
    "screen guard",
    "tempered glass",
    "pencil tip",
    "power bank",
    "airtag holder",
    "magsafe wallet",
]

PREOWNED_KEYWORDS = [
    "pre-owned",
    "pre owned",
    "preowned",
    "used",
    "refurbished",
    "second hand",
    "second-hand",
    "open box",
    "open-box",
    "box opened",
    "unboxed",
]

REGION_MAP = {
    r"\b(usa|us|united states)\b": "USA",
    r"\b(sg|singapore)\b": "SG",
    r"\b(uae|dubai)\b": "UAE",
    r"\b(jp|japan|japanese)\b": "Japan",
    r"\b(hk|hong\s*kong)\b": "HK",
    r"\b(uk|united kingdom)\b": "UK",
    r"\b(global|international)\b": "Global",
    r"\b(in|india|indian)\b": "India",
    r"\b(vn|vietnam)\b": "Vietnam",
    r"\b(au|australia)\b": "Australia",
    r"\b(ca|canada)\b": "Canada",
    r"\b(eu|europe)\b": "EU",
    r"\b(cn|china)\b": "China",
    r"\b(kr|korea)\b": "Korea",
    r"\b(my|malaysia)\b": "Malaysia",
    r"\b(th|thailand)\b": "Thailand",
}


def parse_price(text: Optional[str]) -> Optional[int]:
    """Extracts a clean integer price from strings like '৳ 125,000', 'BDT 135000.00', '$999'."""
    if not text:
        return None
    # Remove trailing decimal cents e.g. .00
    cleaned = re.sub(r"\.00\b", "", str(text))
    # Remove commas and spaces
    cleaned = re.sub(r"[, \t\xa0]", "", cleaned)
    # Find sequence of digits between 2 and 8 digits long
    match = re.search(r"(\d{2,8})", cleaned)
    if match:
        val = int(match.group(1))
        return val if val > 0 else None
    return None


def is_accessory(candidate_title: str, query: str) -> bool:
    """Returns True if candidate appears to be an accessory while the query is not."""
    q_lower = query.lower()
    c_lower = candidate_title.lower()

    # If the user explicitly asked for an accessory in the query, don't filter it out
    for acc in ACCESSORY_KEYWORDS:
        if re.search(r"\b" + re.escape(acc) + r"\b", q_lower):
            return False

    # Check if candidate has an accessory keyword
    for acc in ACCESSORY_KEYWORDS:
        if re.search(r"\b" + re.escape(acc) + r"\b", c_lower):
            return True

    return False


def is_preowned_or_used(candidate_title: str, query: str) -> bool:
    """Returns True if candidate is marked as pre-owned/used/refurbished while query is not."""
    q_lower = query.lower()
    c_lower = candidate_title.lower()

    for kw in PREOWNED_KEYWORDS:
        if kw in q_lower:
            return False

    for kw in PREOWNED_KEYWORDS:
        if kw in c_lower:
            return True

    return False


def matches_model_name(candidate_title: str, query: str) -> bool:
    """Checks if the candidate title strictly matches the target model name
    without accidentally matching higher or different tiers (e.g. Pro vs Pro Max vs Plus).
    """
    c_lower = candidate_title.lower()
    q_lower = query.lower()

    # Query tokens
    q_tokens = [t for t in re.findall(r"[a-z0-9]+", q_lower) if len(t) > 1]
    if not q_tokens:
        return True

    # Must contain essential query tokens
    for token in q_tokens:
        if token not in c_lower:
            return False

    # Strict model tier checks
    has_q_pro_max = "pro max" in q_lower or "promax" in q_lower
    has_c_pro_max = "pro max" in c_lower or "promax" in c_lower

    if not has_q_pro_max and has_c_pro_max:
        return False

    has_q_plus = "plus" in q_lower
    has_c_plus = "plus" in c_lower
    if not has_q_plus and has_c_plus:
        return False

    has_q_pro = "pro" in q_lower and not has_q_pro_max
    has_c_pro = "pro" in c_lower and not has_c_pro_max
    if not has_q_pro and has_c_pro:
        return False

    has_q_anc = "anc" in q_lower
    has_c_anc = "anc" in c_lower
    if not has_q_anc and has_c_anc:
        return False

    has_q_ultra = "ultra" in q_lower
    has_c_ultra = "ultra" in c_lower
    if not has_q_ultra and has_c_ultra:
        return False

    return True


def classify_official_unofficial(text: str) -> str:
    """Classifies a title, badge, or variant label as Official or Unofficial.
    Ignores region tags (USA, SG, etc.).
    """
    t_lower = text.lower()

    # Unofficial first (so 'Apple Unauthorized' doesn't get caught by 'Apple Authorized')
    if any(k in t_lower for k in ["unofficial", "unauthorized", "apple unauthorized", "international version", "int version"]):
        return "Unofficial"

    if any(k in t_lower for k in ["official", "authorized", "apple authorized", "brand warranty", "official warranty"]):
        return "Official"

    return "not found"


def extract_region(text: str) -> str:
    """Extracts geographic region tag (e.g. USA, SG, UAE, Japan) from title or variant string."""
    t_lower = text.lower()
    for pattern, canonical_name in REGION_MAP.items():
        if re.search(pattern, t_lower):
            return canonical_name
    return "not found"


def extract_storage(text: str) -> str:
    """Extracts storage capacity like 64GB, 128GB, 256GB, 512GB, 1TB."""
    match = re.search(r"\b(16|32|64|128|256|512)\s*(gb|tb)\b|\b(1|2)\s*tb\b", text, re.IGNORECASE)
    if match:
        cap = match.group(0).upper().replace(" ", "")
        if not cap.endswith("GB") and not cap.endswith("TB"):
            cap += "GB"
        return cap
    return "not found"
