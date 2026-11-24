import pytest
from scraper_app.config.settings import AppSettings
from scraper_app.ai.gemini_engine import GeminiEngine


def test_competitor_sanitization():
    engine = GeminiEngine(AppSettings())

    dirty_text = (
        "Visit our store at https://applegadgetsbd.com or call +8801712345678. "
        "Also check www.dazzle.com.bd at Bashundhara City. Authentic Apple product."
    )
    cleaned = engine.sanitize_competitor_content(dirty_text)

    assert "applegadgetsbd.com" not in cleaned
    assert "dazzle.com.bd" not in cleaned
    assert "01712345678" not in cleaned
    assert "Authentic Apple product." in cleaned


@pytest.mark.asyncio
async def test_skip_gemini_on_not_found():
    engine = GeminiEngine(AppSettings(enable_gemini=True, gemini_api_key="fake_key"))

    # When is_found is False, Gemini must be skipped completely
    specs, desc = await engine.process_product_content(
        product_name="Nonexistent Gadget",
        raw_description="",
        specifications="",
        is_found=False,
    )

    assert specs == "not found"
    assert desc == "not found"


def test_clean_html_wrapper():
    engine = GeminiEngine(AppSettings())

    raw_response = """```html
<html>
<body>
  <h2>iPhone 16 Pro Overview</h2>
  <p>The latest flagship from Apple.</p>
</body>
</html>
```"""

    cleaned = engine._clean_html_wrapper(raw_response)
    assert "```" not in cleaned
    assert "<html>" not in cleaned
    assert "<body>" not in cleaned
    assert "<h2>iPhone 16 Pro Overview</h2>" in cleaned
    assert "<p>The latest flagship from Apple.</p>" in cleaned
