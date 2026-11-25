"""Permanent regression tests locking in all accuracy & speed fixes from the 10-site, 300-product audit."""
import io
import tempfile
from pathlib import Path
from PIL import Image

from scraper_app.scraper.site_scraper import SiteScraper
from scraper_app.browser.browser_manager import BrowserManager
from scraper_app.media.image_downloader import ImageDownloader


def test_fallback_queries_ignore_english_hyphens_and_shorten_long_titles():
    # Must NOT treat '3-in-1' or 'Type-C' or 'On-Ear' as a model SKU
    fb_3in1 = SiteScraper._build_fallback_queries("Qualitell E3 Electric Mosquito Swatter | 3-in-1 UV Trap Rechargeable")
    assert "in-1" not in fb_3in1
    assert "3-in-1" not in fb_3in1
    assert any(q.startswith("Qualitell E3 Electric Mosquito") for q in fb_3in1)

    # Real hyphenated SKU still generates clean SKU + prefix-stripped fallbacks
    fb_sku = SiteScraper._build_fallback_queries("Joyroom JR-OE2S Openfree Wireless Earbuds")
    assert "JR-OE2S" in fb_sku
    assert any("OE2S" in q for q in fb_sku)

    # Short 3-word query with no SKU produces no unnecessary fallbacks
    assert SiteScraper._build_fallback_queries("Apple AirPods Pro") == []


def test_tracker_blocklist_contains_analytics_not_storefronts():
    domains = BrowserManager.TRACKER_DOMAINS
    assert "googletagmanager.com" in domains
    assert "connect.facebook.net" in domains
    assert not any(store in d for d in domains for store in ("startech", "applegadgets", "anker", "sumashtech"))


def test_concurrent_image_downloader_preserves_order_and_deduplicates():
    def make_png_bytes(color):
        buf = io.BytesIO()
        img = Image.new("RGBA", (120, 120), color)
        img.save(buf, format="PNG")
        return buf.getvalue()

    img_red = make_png_bytes((255, 0, 0, 255))
    img_blue = make_png_bytes((0, 0, 255, 128))

    class FakeResp:
        def __init__(self, content):
            self.status_code = 200
            self.content = content

    class FakeSession:
        def get(self, url, headers=None, timeout=15):
            if "red" in url:
                return FakeResp(img_red)
            return FakeResp(img_blue)

    with tempfile.TemporaryDirectory() as tmpd:
        dl = ImageDownloader(tmpd)
        # Pass red, duplicate red, then blue -> should save exactly 2 JPEGs in order
        folder, paths = dl.download_product_images(
            "Test Product",
            ["https://example.com/red1.png", "https://example.com/red2.png", "https://example.com/blue.png"],
            session=FakeSession(),
        )
        assert Path(folder).exists()
        assert len(paths) == 2
        assert paths[0].endswith("_1.jpg")
        assert paths[1].endswith("_2.jpg")
        with Image.open(paths[1]) as saved_blue:
            assert saved_blue.mode == "RGB"
            assert saved_blue.size == (120, 120)
