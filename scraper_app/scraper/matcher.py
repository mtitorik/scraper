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

# Phrases describing included accessories on a real device (not standalone accessories)
INCLUDED_ACCESSORY_PHRASES = [
    r"\bwith\s+[a-z0-9\-\s]{0,25}charging\s+case\b",
    r"\bmagsafe\s+charging\s+case\b",
    r"\bwireless\s+charging\s+case\b",
    r"\bcharging\s+case\b",
    r"\bcarry(?:ing)?\s+case\b",
    r"\bwith\s+[a-z0-9\-\s]{0,20}(?:sport\s+)?(?:band|strap|loop)\b",
    r"\bwith\s+[a-z0-9\-\s]{0,20}(?:charger|adapter|cable)\b",
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

ORDINAL_MAP = {
    "1": ["1", "1st", "first", "gen 1", "1st gen"],
    "2": ["2", "2nd", "second", "gen 2", "2nd gen", "ii"],
    "3": ["3", "3rd", "third", "gen 3", "3rd gen", "iii"],
    "4": ["4", "4th", "fourth", "gen 4", "4th gen", "iv"],
    "5": ["5", "5th", "fifth", "gen 5", "5th gen", "v"],
}

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
    cleaned = re.sub(r"\.00\b", "", str(text))
    cleaned = re.sub(r"[, \t\xa0]", "", cleaned)
    match = re.search(r"(\d{2,8})", cleaned)
    if match:
        val = int(match.group(1))
        return val if val > 0 else None
    return None


MAIN_DEVICE_KEYWORDS = [
    "iphone", "samsung", "galaxy", "pixel", "xiaomi", "redmi", "poco", "oneplus",
    "realme", "oppo", "vivo", "motorola", "nokia", "honor", "huawei", "tecno", "infinix",
    "ipad", "macbook", "imac", "mac mini", "watch", "airpods", "buds", "earbuds",
    "earphone", "headphone", "tws", "laptop", "tablet", "tab", "speaker", "camera",
    "gopro", "drone", "monitor", "playstation", "ps5", "xbox", "nintendo", "switch",
]


def is_accessory(candidate_title: str, query: str) -> bool:
    """Returns True if candidate appears to be a standalone accessory while the query is a main device.
    Allows searching accessory brands/models directly (e.g. 'Baseus Dura Series PD' -> '...Fast Charging Cable'),
    and ignores benign phrases like 'with MagSafe Charging Case' or 'with Sport Band'.
    """
    q_lower = query.lower()
    c_lower = candidate_title.lower()

    # If the user explicitly asked for an accessory in the query, don't filter it out
    for acc in ACCESSORY_KEYWORDS:
        if re.search(r"\b" + re.escape(acc) + r"\b", q_lower):
            return False

    # Strip included-in-box phrases (e.g. "AirPods Pro 2 with MagSafe Charging Case")
    stripped_title = c_lower
    for phrase_pat in INCLUDED_ACCESSORY_PHRASES:
        stripped_title = re.sub(phrase_pat, " ", stripped_title)

    # Check if the query is for a main device (phone, earbuds, watch, tablet, laptop, etc.)
    query_is_main_device = any(re.search(r"\b" + re.escape(dev) + r"\b", q_lower) for dev in MAIN_DEVICE_KEYWORDS)

    # If query is NOT a main device (e.g. "Baseus Dura Series PD", "Anker 65W", "Ugreen Nexode"),
    # only reject explicit protective covers/cases meant FOR another device
    if not query_is_main_device:
        return bool(re.search(r"\b(case|cover|protector|glass|pouch|sleeve)\s+for\b", stripped_title))

    # For main devices, reject standalone accessories
    for acc in ACCESSORY_KEYWORDS:
        if re.search(r"\b" + re.escape(acc) + r"\b", stripped_title):
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


def _token_matches(token: str, candidate_lower: str, compact_candidate: str) -> bool:
    """Checks if a single query token matches candidate_lower cleanly on word boundaries."""
    # Pure numeric token (e.g. "2", "16", "4"): must match on word boundary or ordinal equivalent
    if token.isdigit():
        if re.search(r"(?<![a-z0-9])" + re.escape(token) + r"(?![a-z0-9])", candidate_lower):
            return True
        for alt in ORDINAL_MAP.get(token, []):
            if re.search(r"(?<![a-z0-9])" + re.escape(alt) + r"(?![a-z0-9])", candidate_lower):
                return True
        return False

    # Alphanumeric model code (e.g. "oe2s", "r60i", "jroe2s", "m3")
    if re.search(r"[a-z]", token) and re.search(r"[0-9]", token):
        if re.search(r"(?<![a-z0-9])" + re.escape(token) + r"(?![a-z0-9])", candidate_lower):
            return True
        if token in compact_candidate:
            return True
        return False

    # Regular alphabetic word
    return bool(re.search(r"\b" + re.escape(token) + r"\b", candidate_lower) or token in candidate_lower)


def _extract_hyphenated_skus(text_lower: str) -> List[Tuple[str, str, str]]:
    """Extracts hyphenated model codes like 'jr-oe2s' -> (full='jr-oe2s', prefix='jr', suffix='oe2s')."""
    skus = []
    for m in re.finditer(r"\b([a-z]{1,4})-([a-z0-9]*\d[a-z0-9]*)\b", text_lower):
        skus.append((m.group(0), m.group(1), m.group(2)))
    return skus


def matches_model_name(candidate_title: str, query: str) -> bool:
    """Checks if the candidate title strictly matches the target model name
    without accidentally matching wrong generations (e.g. AirPods Pro 2 vs 3)
    or different tiers (e.g. Pro vs Pro Max vs Plus).
    """
    c_lower = candidate_title.lower()
    q_lower = query.lower()
    compact_c = re.sub(r"[^a-z0-9]", "", c_lower)

    # Identify hyphenated SKU prefixes (e.g. 'jr' in 'jr-oe2s') that some stores omit ('Joyroom OE2S')
    optional_sku_prefixes = set()
    for _, prefix, suffix in _extract_hyphenated_skus(q_lower):
        # If the distinctive suffix (e.g. 'oe2s') is present in candidate, prefix ('jr') can be optional
        if _token_matches(suffix, c_lower, compact_c):
            optional_sku_prefixes.add(prefix)

    # Keep ALL numeric tokens (including single digits like '2', '3', '4') and words with len > 1
    q_tokens = [t for t in re.findall(r"[a-z0-9]+", q_lower) if len(t) > 1 or t.isdigit()]
    if not q_tokens:
        return True

    for token in q_tokens:
        if token in optional_sku_prefixes:
            continue
        if not _token_matches(token, c_lower, compact_c):
            return False

    # Reject conflicting generation number right after the model stem (e.g. "AirPods Pro 2" vs "AirPods Pro 3")
    q_tail_num = re.search(r"([a-z]+)\s+(\d{1,2})\b", q_lower)
    if q_tail_num:
        stem, q_num = q_tail_num.group(1), q_tail_num.group(2)
        c_stem_nums = re.findall(r"\b" + re.escape(stem) + r"\s+(\d{1,2})\b", c_lower)
        if c_stem_nums and q_num not in c_stem_nums:
            return False

    # Strict model tier checks
    has_q_pro_max = "pro max" in q_lower or "promax" in q_lower
    has_c_pro_max = "pro max" in c_lower or "promax" in c_lower
    if not has_q_pro_max and has_c_pro_max:
        return False

    has_q_plus = bool(re.search(r"\bplus\b", q_lower))
    has_c_plus = bool(re.search(r"\bplus\b", c_lower))
    if not has_q_plus and has_c_plus:
        return False

    has_q_pro = bool(re.search(r"\bpro\b", q_lower)) and not has_q_pro_max
    has_c_pro = bool(re.search(r"\bpro\b", c_lower)) and not has_c_pro_max
    if not has_q_pro and has_c_pro:
        return False

    # Only enforce ANC vs non-ANC distinction for AirPods 4 (where Apple sells two separate SKUs)
    if "airpods" in q_lower and re.search(r"\b4\b", q_lower):
        has_q_anc = bool(re.search(r"\banc\b", q_lower)) or "active noise cancellation" in q_lower
        has_c_anc = bool(re.search(r"\banc\b", c_lower)) or "active noise cancellation" in c_lower
        if not has_q_anc and has_c_anc:
            return False

    has_q_ultra = bool(re.search(r"\bultra\b", q_lower))
    has_c_ultra = bool(re.search(r"\bultra\b", c_lower))
    if not has_q_ultra and has_c_ultra:
        return False

    return True


def score_candidate(candidate_title: str, query: str) -> float:
    """Scores a matched candidate title so the closest, cleanest product match ranks first."""
    c_lower = candidate_title.lower().strip()
    q_lower = query.lower().strip()
    compact_c = re.sub(r"[^a-z0-9]", "", c_lower)
    compact_q = re.sub(r"[^a-z0-9]", "", q_lower)

    score = 0.0

    # Exact substring phrase match
    if q_lower in c_lower:
        score += 100.0
    elif compact_q and compact_q in compact_c:
        score += 85.0

    # Exact token matches (especially digits & alphanumeric model codes)
    q_tokens = [t for t in re.findall(r"[a-z0-9]+", q_lower) if len(t) > 1 or t.isdigit()]
    for token in q_tokens:
        if token.isdigit():
            if re.search(r"(?<![a-z0-9])" + re.escape(token) + r"(?![a-z0-9])", c_lower):
                score += 30.0
            else:
                score += 15.0  # ordinal match
        elif re.search(r"[a-z]", token) and re.search(r"[0-9]", token):
            score += 35.0
        elif re.search(r"\b" + re.escape(token) + r"\b", c_lower):
            score += 12.0

    # Mild preference for cleaner titles closer in length to query
    extra_len = max(0, len(c_lower) - len(q_lower))
    score -= min(extra_len * 0.15, 20.0)

    return round(score, 2)


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
