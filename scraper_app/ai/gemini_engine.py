import re
import time
import asyncio
from typing import Optional, Dict, Any, Tuple

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

from ..config.settings import AppSettings


class GeminiEngine:
    """Handles Google Gemini AI text rewriting and generation.
    Supports Gemini 2.5 Flash and Pro, 3-case logic (raw desc -> specs -> Search Grounding),
    customizable description templates, and strict competitor sanitization.
    """

    STRUCTURE_PRESETS = {
        "standard": """
Follow this semantic HTML structure:
<p>[Compelling 2-3 sentence introduction about the product]</p>
<h3>Key Features</h3>
<ul>
  <li><strong>Feature Title:</strong> Brief explanation</li>
  <li><strong>Feature Title:</strong> Brief explanation</li>
  <li><strong>Feature Title:</strong> Brief explanation</li>
</ul>
<h3>Why Buy from {brand_name}</h3>
<p>[Highlight store credibility, warranty, genuine product guarantee, and selling points]</p>
""",
        "short": """
Follow this concise semantic HTML structure:
<p>[Short, punchy 2-sentence product overview]</p>
<ul>
  <li><strong>Highlight 1:</strong> Detail</li>
  <li><strong>Highlight 2:</strong> Detail</li>
  <li><strong>Highlight 3:</strong> Detail</li>
  <li><strong>Highlight 4:</strong> Detail</li>
</ul>
<p>[One sentence concluding remark mentioning {brand_name}]</p>
""",
        "detailed": """
Follow this detailed semantic HTML structure:
<p>[Detailed introductory overview]</p>
<h3>Design & Build</h3>
<p>[Design highlights, materials, and form factor]</p>
<h3>Performance & Features</h3>
<p>[Processor, speed, battery, and capabilities]</p>
<h3>Key Specifications Highlights</h3>
<ul>
  <li><strong>Specs Point:</strong> Detail</li>
  <li><strong>Specs Point:</strong> Detail</li>
</ul>
<h3>Why Choose {brand_name}</h3>
<p>[Selling points, authentic guarantee, and service promise]</p>
""",
    }

    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.client = None
        self._init_client()

    def _init_client(self):
        if genai and self.settings.gemini_api_key:
            try:
                self.client = genai.Client(api_key=self.settings.gemini_api_key.strip())
            except Exception as e:
                print(f"[GeminiEngine] Error initializing Gemini Client: {e}")
                self.client = None
        else:
            self.client = None

    def update_settings(self, settings: AppSettings):
        self.settings = settings
        self._init_client()

    def sanitize_competitor_content(self, text: str) -> str:
        """Removes competitor URLs, phone numbers, and physical addresses from text."""
        if not text:
            return ""
        # Remove URLs
        cleaned = re.sub(r"https?://[^\s]+", "", text)
        cleaned = re.sub(r"www\.[^\s]+", "", cleaned)
        # Remove Bangladeshi / international phone numbers
        cleaned = re.sub(r"(\+?88)?01[3-9]\d{8}", "", cleaned)
        cleaned = re.sub(r"\+?\d{1,3}[-.\s]?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}", "", cleaned)
        return cleaned.strip()

    def _get_structure_instructions(self) -> str:
        preset = self.settings.gemini_structure_preset
        brand = self.settings.brand_name or "our store"

        if preset == "custom" and self.settings.gemini_custom_structure.strip():
            return f"\nRequired HTML Structure Outline:\n{self.settings.gemini_custom_structure.strip()}\n"

        template = self.STRUCTURE_PRESETS.get(preset, self.STRUCTURE_PRESETS["standard"])
        return f"\nRequired HTML Structure:\n{template.format(brand_name=brand)}\n"

    def _build_system_instruction(self) -> str:
        brand = self.settings.brand_name or "our store"
        url = self.settings.brand_url or ""
        address = self.settings.store_address or ""
        points = self.settings.selling_points or ""
        custom_rules = self.settings.custom_rules or ""

        inst = f"""You are an expert e-commerce copywriter for {brand} ({url}).
Your job is to generate clean, user-friendly, authentic product descriptions and specifications.

STRICT RULES:
1. OUTPUT ONLY a clean semantic HTML fragment for descriptions (e.g. <h2>, <h3>, <p>, <ul>, <li>, <strong>).
2. DO NOT output ```html code blocks, <html>, <head>, <body>, <script>, or <style> tags.
3. NEVER mention any other competitor store names, competitor URLs, phone numbers, or competitor addresses.
4. Always speak from the perspective of {brand}.
"""
        if address:
            inst += f"Store Address: {address}\n"
        if points:
            inst += f"Key Selling Points to Emphasize:\n{points}\n"
        if custom_rules:
            inst += f"Custom Store Rules:\n{custom_rules}\n"

        inst += self._get_structure_instructions()
        return inst

    async def process_product_content(
        self,
        product_name: str,
        raw_description: str,
        specifications: str,
        is_found: bool,
    ) -> Tuple[str, str]:
        """Runs the 3-case AI logic.
        Returns (final_specifications, clean_html_description).
        """
        # If product was not found on any site, skip Gemini completely!
        if not is_found:
            return "not found", "not found"

        # If Gemini is disabled or no API key, return sanitized raw content formatted into clean <p> blocks
        if not self.settings.enable_gemini or not self.client:
            clean_specs = self.sanitize_competitor_content(specifications) or "not found"
            clean_raw = self.sanitize_competitor_content(raw_description)
            if clean_raw:
                paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\n", clean_raw) if p.strip()]
                clean_html = "\n".join(f"<p>{p}</p>" for p in paragraphs)
            else:
                clean_html = "not found"
            return clean_specs, clean_html

        model_name = self.settings.gemini_model or "gemini-2.5-flash"
        sys_instruction = self._build_system_instruction()

        has_desc = bool(raw_description and raw_description.strip() and raw_description.strip() != "not found")
        has_specs = bool(specifications and specifications.strip() and specifications.strip() != "not found")

        # CASE 1: Raw description exists -> Rewrite into clean HTML
        if has_desc:
            prompt = f"""Rewrite the following raw product description for '{product_name}' into our required clean HTML format:

RAW DESCRIPTION:
{raw_description[:3000]}

SPECIFICATIONS (for reference):
{specifications[:1500] if has_specs else 'N/A'}
"""
            desc_html = await self._generate_with_retry(model_name, sys_instruction, prompt)
            return self.sanitize_competitor_content(specifications), desc_html

        # CASE 2: No raw description, but specifications exist -> Generate HTML description from specs
        elif has_specs:
            prompt = f"""Generate an engaging, user-friendly HTML product description for '{product_name}' based on these specifications:

SPECIFICATIONS:
{specifications[:3000]}
"""
            desc_html = await self._generate_with_retry(model_name, sys_instruction, prompt)
            return self.sanitize_competitor_content(specifications), desc_html

        # CASE 3: Neither description nor specifications exist -> Use Search Grounding!
        else:
            prompt = f"""Search Google for official specifications and product overview for '{product_name}'.
First, provide a clean plain-text specifications list under '---SPECIFICATIONS---'.
Then, provide the clean semantic HTML product description under '---DESCRIPTION---'.
"""
            response_text = await self._generate_with_retry(
                model_name, sys_instruction, prompt, use_search_grounding=True
            )

            # Parse split output
            if "---DESCRIPTION---" in response_text:
                parts = response_text.split("---DESCRIPTION---")
                specs_part = parts[0].replace("---SPECIFICATIONS---", "").strip()
                desc_part = parts[1].strip()
                return (
                    self.sanitize_competitor_content(specs_part) or "not found",
                    self._clean_html_wrapper(desc_part),
                )
            else:
                return (
                    "not found",
                    self._clean_html_wrapper(response_text),
                )

    async def _generate_with_retry(
        self,
        model_name: str,
        sys_instruction: str,
        prompt: str,
        use_search_grounding: bool = False,
    ) -> str:
        """Calls Gemini API with exponential backoff on 429 rate limits."""
        for attempt in range(3):
            try:
                config_kwargs: Dict[str, Any] = {
                    "system_instruction": sys_instruction,
                }
                if use_search_grounding and types:
                    config_kwargs["tools"] = [types.Tool(google_search=types.GoogleSearch())]

                config = types.GenerateContentConfig(**config_kwargs) if types else None

                response = await asyncio.to_thread(
                    self.client.models.generate_content,
                    model=model_name,
                    contents=prompt,
                    config=config,
                )
                text = response.text or ""
                return self._clean_html_wrapper(text)
            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "quota" in err_str or "rate" in err_str:
                    wait_sec = (attempt + 1) * 3
                    print(f"[GeminiEngine] Rate limit hit, backing off for {wait_sec}s...")
                    await asyncio.sleep(wait_sec)
                else:
                    print(f"[GeminiEngine] Generation error: {e}")
                    break
        return "not found"

    def _clean_html_wrapper(self, raw_html: str) -> str:
        """Strips markdown code fences, html/body tags, and cleans extra whitespace."""
        cleaned = re.sub(r"^```html\s*", "", raw_html, flags=re.IGNORECASE)
        cleaned = re.sub(r"^```\s*", "", cleaned)
        cleaned = re.sub(r"```$", "", cleaned)
        cleaned = re.sub(r"</?(html|body|head|meta|doctype)[^>]*>", "", cleaned, flags=re.IGNORECASE)
        cleaned = self.sanitize_competitor_content(cleaned)
        return cleaned.strip()
