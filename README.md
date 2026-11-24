# Scraper — E-Commerce Intelligence App

A standalone, sleek, cross-platform desktop application for **macOS** and **Windows** designed to automate product catalog extraction, variant pricing, deduplicated image downloads, and AI-powered copy generation from unlimited e-commerce websites.

Built with **Python 3.12**, **PyWebView** (Native UI window), **Playwright** (Always-Visible Incognito Browser), **openpyxl** (Dynamic 2-Sheet Excel), **Pillow** (Max-Quality JPEG Converter), and **Google Gemini AI** (`google-genai` SDK).

---

## 🌟 Key Features

1. **Unlimited Website Waterfall Search:**
   - Configure websites in priority order (`Website 1 -> Website 2 -> Website 3 ...`).
   - Searches Website 1 first, records details, and checks next websites only for missing rows or missing variants (Option C).
   - Automatically skips accessories and **Pre-Owned / Used / Refurbished** listings.
   - Stops early and notifies the user as soon as all rows are complete!

2. **Always-Visible Incognito Browser:**
   - Watch the Chromium browser search, navigate, and click variant options live on screen.
   - **Best of both worlds:** Auto-detects installed Google Chrome, Microsoft Edge, or Brave, with a 1-click **"Install Built-in Browser"** fallback inside the app!
   - Isolated temporary Incognito profile (never touches personal tabs or passwords).
   - Automatically closes promotional popups and pauses for user confirmation if a CAPTCHA challenge is encountered.

3. **Interactive Resource Limiter (`psutil`):**
   - **Max CPU Cores Slider:** Limits worker concurrency and OS process affinity.
   - **Max CPU Usage % Slider:** Dynamically injects micro-pauses between browser clicks if CPU crosses threshold.
   - **Max RAM Limit (GB) Slider:** Automatically recycles the browser context between products when memory exceeds 85% of ceiling to flush cached DOM memory.

4. **Dynamic 2-Sheet `.xlsx` Output & Live Table View:**
   - **Sheet 1 (`Products`):** One row per product with dynamic CMS-safe columns: `Product name`, `page link`, `Image Folder` (clickable local hyperlink), `Regular Price`, `[Discounted Price]` (placed immediately to its right), `Colour 1` ... `Region 1` ... `specification`, `description`, `Status`.
   - **Sheet 2 (`All Variant Combinations`):** Lossless breakdown of every exact option combination clicked (`Type | Region | Storage | Colour | Regular Price | Discounted Price | Stock`).
   - Output file is created **immediately on Start** (all product names pre-populated) and saved incrementally after every product with Windows Excel lock protection.
   - **In-App Live Spreadsheet View:** Live cell-by-cell updates on screen with Sheet 1 / Sheet 2 tab switching!
   - **Resume Support:** Resume from any existing partially completed output `.xlsx` seamlessly.

5. **Deduplicated Max-Quality Image Pipeline:**
   - Saves into `[Root Folder]/[Sanitized Product Name]/`.
   - Computes SHA-256 hash of downloaded image bytes: **zero duplicate images saved**.
   - Converts all formats to full-resolution `.jpg` with `quality=95`, `subsampling=0`, and clean white backgrounds for transparent PNGs/WebPs.

6. **Google Gemini AI Content Engine (`Flash` & `Pro`):**
   - Free-tier friendly with rate-limit pacing and retry backoff.
   - **Skips Gemini completely** for `"Not Found"` products (saves quota!).
   - Works in AI-free mode if toggled off or if no API key is provided.
   - Customizable **Description HTML Structure / Presets** (Standard, Short, Detailed, or Custom Outline).
   - Strips all competitor names/URLs/phones and inserts your configured store brand and custom rules.

---

## 🚀 Running from Source (Development)

### Prerequisites
- Python 3.12+
- Homebrew (macOS) or standard Python installer (Windows)

### Installation
```bash
# 1. Clone repository
git clone https://github.com/your-username/Scraper.git
cd Scraper

# 2. Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run test suite
pytest -v tests/

# 5. Launch Scraper desktop app
python main.py
```

---

## 🔑 Getting a Free Google Gemini API Key

1. Go to [Google AI Studio](https://aistudio.google.com/).
2. Sign in with any Google account.
3. Click **"Get API key"** -> **"Create API key"**.
4. Paste the key into Scraper under **Brand & Gemini AI** tab (auto-saved locally on your computer).

---

## 📦 Building Standalone Binaries for Employees & Public

### macOS (.app & .dmg)
```bash
chmod +x packaging/build_macos.sh
./packaging/build_macos.sh
```
Outputs: `dist/Scraper-macOS.dmg`

### Windows (.exe & .zip)
Double-click `packaging\build_windows.bat` or run:
```cmd
packaging\build_windows.bat
```
Outputs: `dist\Scraper-Windows-x64.zip`

### Automated GitHub Releases (Zero Setup for Staff)
Pushing a tag (e.g. `git tag v1.0.0 && git push origin v1.0.0`) automatically triggers `.github/workflows/release.yml`, building:
- `Scraper-macOS-arm64.dmg` (Apple Silicon M1-M4)
- `Scraper-macOS-x64.dmg` (Intel Mac)
- `Scraper-Windows-x64.zip` (Windows 10/11 64-bit)

Employees can simply download the release file from GitHub, unzip/open, and start scraping!
