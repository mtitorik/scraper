import os
import sys
import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional


def get_default_app_dir() -> Path:
    """Returns platform-specific application support directory, with fallback to local app_data."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    
    app_dir = Path(base) / "Scraper"
    try:
        app_dir.mkdir(parents=True, exist_ok=True)
        return app_dir
    except (PermissionError, OSError):
        # Fallback to local directory inside workspace
        fallback = Path(__file__).resolve().parent.parent.parent / "app_data"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


@dataclass
class AppSettings:
    # Websites hierarchy (starts completely blank)
    websites: List[str] = field(default_factory=list)
    
    # Storage and file paths
    input_mode: str = "file"  # "file" or "manual"
    manual_products_text: str = ""
    root_image_folder: str = ""
    last_input_xlsx: str = ""
    last_output_xlsx: str = ""
    
    # Browser configuration
    browser_mode: str = "auto"  # "auto", "chrome", "msedge", "brave", "bundled", "custom"
    custom_browser_path: str = ""
    
    # Resource limiting
    max_cpu_cores: int = 2
    max_cpu_percent: int = 40
    max_ram_gb: float = 2.0
    
    # Scraping behavior
    search_missing_official_unofficial_pair: bool = True  # Option C
    skip_preowned_devices: bool = True
    
    # Gemini AI configuration
    enable_gemini: bool = True
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"  # "gemini-2.5-flash" (default/free-tier friendly) or "gemini-2.5-pro"
    gemini_structure_preset: str = "standard"  # "standard", "short", "detailed", "custom"
    gemini_custom_structure: str = ""
    
    # Brand details (starts completely blank for white-label public release)
    brand_name: str = ""
    brand_url: str = ""
    store_address: str = ""
    selling_points: str = ""
    custom_rules: str = ""
    
    # UI preferences
    theme: str = "dark"  # "dark" or "light"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppSettings":
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


class SettingsManager:
    def __init__(self, config_path: Optional[Path] = None):
        self.app_dir = get_default_app_dir()
        self.config_path = config_path or (self.app_dir / "config.json")
        self.settings: AppSettings = self.load()

    def load(self) -> AppSettings:
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return AppSettings.from_dict(data)
            except Exception as e:
                print(f"[SettingsManager] Warning: failed to load {self.config_path}: {e}")
        return AppSettings()

    def save(self, settings: Optional[AppSettings] = None) -> bool:
        if settings is not None:
            self.settings = settings
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.settings.to_dict(), f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[SettingsManager] Error saving {self.config_path}: {e}")
            return False

    def update(self, **kwargs) -> bool:
        current_dict = self.settings.to_dict()
        for k, v in kwargs.items():
            if k in current_dict:
                current_dict[k] = v
        self.settings = AppSettings.from_dict(current_dict)
        return self.save()
