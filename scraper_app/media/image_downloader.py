import os
import re
import io
import hashlib
from pathlib import Path
from typing import List, Tuple, Set, Optional

import requests
from PIL import Image


def sanitize_filename(name: str) -> str:
    """Removes invalid characters for Windows and macOS file/folder names."""
    # Replace invalid chars: \ / : * ? " < > |
    sanitized = re.sub(r'[\\/*?:"<>|]', " ", name)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    return sanitized[:120] if sanitized else "product"


class ImageDownloader:
    """Downloads all unique images for a product, deduplicates them via SHA-256 hash,
    and converts them to maximum-quality JPEG without resizing, compositing transparent
    layers onto clean white backgrounds.
    """

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    }

    def __init__(self, root_folder: str):
        self.root_folder = Path(root_folder).resolve()
        self.root_folder.mkdir(parents=True, exist_ok=True)

    def download_product_images(
        self,
        product_name: str,
        image_urls: List[str],
        session: Optional[requests.Session] = None,
    ) -> Tuple[str, List[str]]:
        """Downloads all unique images into [root_folder]/[product_name]/
        Returns (folder_path, list_of_saved_jpeg_paths).
        """
        clean_name = sanitize_filename(product_name)
        product_dir = self.root_folder / clean_name
        product_dir.mkdir(parents=True, exist_ok=True)

        req_session = session or requests.Session()
        saved_paths: List[str] = []
        seen_hashes: Set[str] = set()

        # Check existing images in folder for hashes to avoid re-downloading if resuming
        for existing in product_dir.glob("*.jpg"):
            try:
                with open(existing, "rb") as f:
                    seen_hashes.add(hashlib.sha256(f.read()).hexdigest())
                saved_paths.append(str(existing))
            except Exception:
                pass

        saved_count = len(saved_paths)

        for url in image_urls:
            if not url or not url.startswith("http"):
                continue

            try:
                resp = req_session.get(url, headers=self.HEADERS, timeout=15)
                if resp.status_code != 200 or not resp.content:
                    continue

                raw_bytes = resp.content
                img_hash = hashlib.sha256(raw_bytes).hexdigest()

                # Deduplication check
                if img_hash in seen_hashes:
                    continue

                seen_hashes.add(img_hash)

                # Convert to high-quality JPEG using Pillow
                with Image.open(io.BytesIO(raw_bytes)) as pil_img:
                    # Ignore tiny icons / spacers under 80px
                    if pil_img.width < 80 or pil_img.height < 80:
                        continue

                    # Handle transparency: RGBA, LA, or P with transparency
                    if pil_img.mode in ("RGBA", "LA") or (pil_img.mode == "P" and "transparency" in pil_img.info):
                        rgba_img = pil_img.convert("RGBA")
                        # Create white background image of exact same dimensions
                        bg = Image.new("RGB", rgba_img.size, (255, 255, 255))
                        bg.paste(rgba_img, mask=rgba_img.split()[3])  # 3 is the alpha channel
                        final_img = bg
                    else:
                        final_img = pil_img.convert("RGB")

                    saved_count += 1
                    target_file = product_dir / f"{clean_name}_{saved_count}.jpg"

                    # Save with max quality, zero resizing, no subsampling
                    final_img.save(
                        target_file,
                        format="JPEG",
                        quality=95,
                        subsampling=0,
                        optimize=True,
                    )
                    saved_paths.append(str(target_file))

            except Exception as e:
                print(f"[ImageDownloader] Warning downloading {url}: {e}")
                continue

        return str(product_dir), saved_paths
