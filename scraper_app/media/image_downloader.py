import os
import re
import io
import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Tuple, Set, Optional

import requests
from requests.adapters import HTTPAdapter
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
        # Persistent connection-pooled session reused across products
        self._session = requests.Session()
        adapter = HTTPAdapter(pool_connections=8, pool_maxsize=12)
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)

    def _fetch_one(self, req_session: requests.Session, url: str) -> Optional[bytes]:
        if not url or not url.startswith("http"):
            return None
        try:
            resp = req_session.get(url, headers=self.HEADERS, timeout=15)
            if resp.status_code == 200 and resp.content:
                return resp.content
        except Exception as e:
            print(f"[ImageDownloader] Warning downloading {url}: {e}")
        return None

    def download_product_images(
        self,
        product_name: str,
        image_urls: List[str],
        session: Optional[requests.Session] = None,
    ) -> Tuple[str, List[str]]:
        """Downloads all unique images into [root_folder]/[product_name]/ concurrently
        while preserving exact gallery order, SHA-256 deduplication, and max-quality JPEG conversion.
        Returns (folder_path, list_of_saved_jpeg_paths).
        """
        clean_name = sanitize_filename(product_name)
        product_dir = self.root_folder / clean_name
        product_dir.mkdir(parents=True, exist_ok=True)

        req_session = session or self._session
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
        valid_urls = [u for u in image_urls if u and u.startswith("http")]
        if not valid_urls:
            return str(product_dir), saved_paths

        # Fetch concurrently (max 4 workers) while preserving exact gallery order
        if len(valid_urls) > 1 and session is None:
            with ThreadPoolExecutor(max_workers=min(4, len(valid_urls))) as pool:
                raw_results = list(pool.map(lambda u: self._fetch_one(req_session, u), valid_urls))
        else:
            raw_results = [self._fetch_one(req_session, u) for u in valid_urls]

        for url, raw_bytes in zip(valid_urls, raw_results):
            if not raw_bytes:
                continue

            try:
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
                        bg = Image.new("RGB", rgba_img.size, (255, 255, 255))
                        bg.paste(rgba_img, mask=rgba_img.split()[3])
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
                print(f"[ImageDownloader] Warning processing {url}: {e}")
                continue

        return str(product_dir), saved_paths
