import os
import io
import tempfile
from pathlib import Path
from PIL import Image
import pytest

from scraper_app.media.image_downloader import ImageDownloader, sanitize_filename


def test_sanitize_filename():
    assert sanitize_filename('iPhone 16 Pro / Max: "Desert" *Special*? <Edition>') == "iPhone 16 Pro Max Desert Special Edition"
    assert sanitize_filename('Samsung Galaxy S24 | Ultra\\Test') == "Samsung Galaxy S24 Ultra Test"
    assert sanitize_filename("") == "product"


def test_image_deduplication_and_rgba_to_jpeg():
    with tempfile.TemporaryDirectory() as tmpdir:
        downloader = ImageDownloader(tmpdir)

        # Create a mock transparent RGBA image in memory
        rgba_img = Image.new("RGBA", (200, 200), (255, 0, 0, 128))
        buf = io.BytesIO()
        rgba_img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        # Mock requests session
        class MockResponse:
            def __init__(self, content, status_code=200):
                self.content = content
                self.status_code = status_code

        class MockSession:
            def get(self, url, headers=None, timeout=None):
                return MockResponse(png_bytes)

        # Download with duplicates: same bytes passed under two different URLs
        urls = [
            "https://example.com/img1.png",
            "https://example.com/img1_duplicate.png",
            "https://example.com/img1_variant.png",
        ]

        folder, saved_paths = downloader.download_product_images(
            product_name="Test Phone",
            image_urls=urls,
            session=MockSession(),
        )

        assert os.path.exists(folder)
        # All 3 URLs had identical image bytes -> must save only 1 unique image!
        assert len(saved_paths) == 1

        saved_file = Path(saved_paths[0])
        assert saved_file.suffix.lower() == ".jpg"

        # Verify saved JPEG properties
        with Image.open(saved_file) as loaded_jpg:
            assert loaded_jpg.format == "JPEG"
            assert loaded_jpg.mode == "RGB"  # Converted from RGBA without transparency
            assert loaded_jpg.size == (200, 200)  # Preserved 100% full original resolution
