import pytest
from scraper_app.scraper.matcher import (
    is_accessory,
    is_preowned_or_used,
    matches_model_name,
    score_candidate,
    classify_official_unofficial,
    extract_region,
    extract_storage,
    parse_price,
)


def test_parse_price():
    assert parse_price("৳ 125,000") == 125000
    assert parse_price("BDT 135000.00") == 135000
    assert parse_price("$999") == 999
    assert parse_price("149,999 Tk") == 149999
    assert parse_price("Out of Stock") is None
    assert parse_price("") is None


def test_is_accessory():
    # Searching for phone: accessories should be filtered out
    assert is_accessory("iPhone 16 Pro Max Clear Case with MagSafe", "iPhone 16 Pro Max") is True
    assert is_accessory("iPhone 16 Tempered Glass Screen Protector", "iPhone 16") is True
    assert is_accessory("Apple 20W USB-C Power Adapter Charger", "iPhone 16") is True

    # Real phone should NOT be marked as an accessory
    assert is_accessory("iPhone 16 Pro Max", "iPhone 16 Pro Max") is False
    assert is_accessory("Samsung Galaxy S24 Ultra", "Galaxy S24 Ultra") is False

    # If the user explicitly searched for an accessory, do not filter it!
    assert is_accessory("Anker 20W Fast Charger with Cable", "Anker 20W Charger") is False
    assert is_accessory("Apple Silicone Case with MagSafe", "Silicone Case") is False


def test_is_preowned_or_used():
    # Pre-owned filter
    assert is_preowned_or_used("iPhone 15 Pro Max 256GB (Pre-Owned)", "iPhone 15 Pro Max") is True
    assert is_preowned_or_used("iPhone 14 Pro Refurbished", "iPhone 14 Pro") is True
    assert is_preowned_or_used("iPhone 13 128GB Used", "iPhone 13") is True
    assert is_preowned_or_used("Google Pixel 8 Pro - Open Box", "Pixel 8 Pro") is True

    # Brand new should not be flagged
    assert is_preowned_or_used("iPhone 15 Pro Max 256GB Natural Titanium", "iPhone 15 Pro Max") is False

    # If user searched for used, allow it
    assert is_preowned_or_used("iPhone 13 128GB Used", "iPhone 13 Used") is False


def test_matches_model_name():
    # Base model should NOT match Pro or Pro Max or Plus
    assert matches_model_name("iPhone 16 Pro Max 256GB", "iPhone 16") is False
    assert matches_model_name("iPhone 16 Pro 128GB", "iPhone 16") is False
    assert matches_model_name("iPhone 16 Plus 128GB", "iPhone 16") is False
    assert matches_model_name("iPhone 16 128GB Black", "iPhone 16") is True

    # Pro model should NOT match Pro Max
    assert matches_model_name("iPhone 16 Pro Max 256GB", "iPhone 16 Pro") is False
    assert matches_model_name("iPhone 16 Pro 256GB", "iPhone 16 Pro") is True

    # AirPods 4 vs AirPods 4 ANC
    assert matches_model_name("Apple AirPods 4 with Active Noise Cancellation", "AirPods 4") is False
    assert matches_model_name("Apple AirPods 4", "AirPods 4") is True
    assert matches_model_name("Apple AirPods 4 with ANC", "AirPods 4 ANC") is True


def test_classify_official_unofficial():
    assert classify_official_unofficial("iPhone 16 Pro (Apple Authorized Official)") == "Official"
    assert classify_official_unofficial("iPhone 16 Pro (Official)") == "Official"
    assert classify_official_unofficial("iPhone 16 Pro with Brand Warranty") == "Official"

    assert classify_official_unofficial("iPhone 16 Pro (Apple Unauthorized)") == "Unofficial"
    assert classify_official_unofficial("iPhone 16 Pro (Unofficial)") == "Unofficial"
    assert classify_official_unofficial("iPhone 16 Pro (International Version)") == "Unofficial"

    assert classify_official_unofficial("iPhone 16 Pro 128GB") == "not found"


def test_extract_region():
    assert extract_region("iPhone 16 Pro 256GB (USA Physical Dual Sim)") == "USA"
    assert extract_region("iPhone 16 Pro 128GB (SG)") == "SG"
    assert extract_region("iPhone 16 Pro Max (Dubai / UAE)") == "UAE"
    assert extract_region("iPhone 16 Pro (Japan e-Sim)") == "Japan"
    assert extract_region("iPhone 16 Pro (Global)") == "Global"
    assert extract_region("iPhone 16 Pro Black") == "not found"


def test_extract_storage():
    assert extract_storage("iPhone 16 Pro 128GB Black") == "128GB"
    assert extract_storage("iPhone 16 Pro 256 gb Natural") == "256GB"
    assert extract_storage("iPhone 16 Pro Max 1TB Desert") == "1TB"
    assert extract_storage("iPhone 16 Pro Black") == "not found"


def test_airpods_pro_2_never_matches_pro_3_and_allows_charging_case():
    query = "Apple AirPods Pro 2"
    # Real AirPods Pro 2 with Charging Case must NOT be rejected as an accessory
    real_listing = "Apple AirPods Pro 2 (2nd Gen) with MagSafe Charging Case (USB-C)"
    assert is_accessory(real_listing, query) is False
    assert matches_model_name(real_listing, query) is True

    # Standalone silicone case MUST still be rejected as an accessory
    assert is_accessory("Apple AirPods Pro 2 Silicone Case Cover", query) is True

    # AirPods Pro 3 MUST be rejected when searching AirPods Pro 2!
    assert matches_model_name("Apple AirPods Pro 3", query) is False
    assert matches_model_name("Apple AirPods Pro 3 with MagSafe Charging Case", query) is False


def test_joyroom_jr_oe2s_and_anker_r60i_nc_matching():
    # Joyroom JR-OE2S matches both full SKU and prefix-omitted title + charging case
    q_joyroom = "Joyroom JR-OE2S"
    assert is_accessory("Joyroom JR-OE2S Open-Ear Wireless Earbuds with Charging Case", q_joyroom) is False
    assert matches_model_name("Joyroom JR-OE2S Open-Ear Wireless Earbuds with Charging Case", q_joyroom) is True
    assert matches_model_name("Joyroom OE2S Open-Ear Earbuds", q_joyroom) is True

    # Anker Soundcore R60i NC
    q_anker = "Anker Soundcore R60i NC"
    assert is_accessory("Anker Soundcore R60i NC True Wireless Earbuds with Charging Case", q_anker) is False
    assert matches_model_name("Anker Soundcore R60i NC True Wireless Earbuds with Charging Case", q_anker) is True

    # CMF by Nothing Buds Pro 2 (must match titles containing ANC / Hybrid ANC!)
    q_cmf = "CMF by Nothing Buds Pro 2"
    assert matches_model_name("Cmf by Nothing Buds Pro 2 ANC LDAC Audio Earbuds", q_cmf) is True
    assert matches_model_name("CMF by Nothing Buds Pro 2 Hybrid ANC Wireless Earbuds", q_cmf) is True
    assert is_accessory("CMF Buds Pro 2 Case Protector", q_cmf) is True
    assert matches_model_name("CMF by Nothing Buds 2 Plus ANC TWS Earbuds", q_cmf) is False


def test_candidate_scoring_ranks_exact_match_first():
    query = "Apple AirPods Pro 2"
    exact = score_candidate("Apple AirPods Pro 2 (USB-C)", query)
    verbose = score_candidate("Apple AirPods Pro 2nd Generation MagSafe Charging Case International Edition Bundle", query)
    assert exact > verbose
