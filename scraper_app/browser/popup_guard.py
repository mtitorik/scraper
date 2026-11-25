import asyncio
from typing import Optional, List
from playwright.async_api import Page


class PopupGuard:
    """Detects and dismisses promotional popups, cookie consent banners,
    and detects human verification (Cloudflare Turnstile, reCAPTCHA, etc.) challenges.
    """

    PROMO_CLOSE_SELECTORS: List[str] = [
        "button[aria-label*='close' i]",
        "button[aria-label*='dismiss' i]",
        "button[aria-label*='cancel' i]",
        ".modal-close",
        ".popup-close",
        ".dialog-close",
        ".newsletter-popup .close",
        ".modal .close",
        "[data-dismiss='modal']",
        ".btn-close",
        "#close-popup",
        ".popup-overlay .close-btn",
        "button:has-text('No thanks')",
        "button:has-text('Later')",
        "button:has-text('Dismiss')",
        "button:has-text('Accept All')",
        "button:has-text('I Agree')",
        "button:has-text('Got it')",
        "a.close-btn",
    ]

    HUMAN_CHALLENGE_KEYWORDS: List[str] = [
        "verify you are human",
        "just a moment...",
        "checking your browser",
        "attention required! | cloudflare",
        "cloudflare turnstile",
        "hcaptcha",
        "recaptcha",
        "security check",
        "confirm you are human",
        "challenge-running",
    ]

    @classmethod
    async def dismiss_promotional_popups(cls, page: Page) -> bool:
        """Attempts to find and click promotional or cookie overlays (including Tailwind fixed modals)
        without breaking page state.
        """
        dismissed_any = False
        for selector in cls.PROMO_CLOSE_SELECTORS:
            try:
                locator = page.locator(selector).first
                if await locator.is_visible(timeout=250):
                    await locator.click(timeout=800)
                    dismissed_any = True
                    await asyncio.sleep(0.25)
            except Exception:
                continue

        # Also handle Tailwind/Next.js fixed modal popups (e.g. promo banner with SVG X button)
        try:
            closed_fixed = await page.evaluate(r"""() => {
                let closed = false;
                const overlays = Array.from(document.querySelectorAll("[role='dialog'], div.fixed, div[class*='modal' i], div[class*='popup' i]"));
                for (const ov of overlays) {
                    const style = window.getComputedStyle(ov);
                    const z = parseInt(style.zIndex, 10) || 0;
                    const rect = ov.getBoundingClientRect();
                    if ((style.position === "fixed" && z >= 20 && rect.width > 200 && rect.height > 200) || ov.getAttribute("role") === "dialog") {
                        const btns = Array.from(ov.querySelectorAll("button, a[role='button']"));
                        // Look for small close button (usually an X icon with little/no text)
                        const closeBtn = btns.find(b => {
                            const txt = (b.innerText || "").trim();
                            return txt === "" || txt === "×" || txt === "✕" || /^close|dismiss|cancel|skip$/i.test(txt);
                        });
                        if (closeBtn) {
                            closeBtn.click();
                            closed = true;
                        }
                    }
                }
                return closed;
            }""")
            if closed_fixed:
                dismissed_any = True
                await asyncio.sleep(0.3)
        except Exception:
            pass

        # Press Escape as a safe final modal dismissal
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass

        return dismissed_any

    @classmethod
    async def detect_human_verification(cls, page: Page) -> bool:
        """Detects if page is currently blocked by a CAPTCHA or anti-bot challenge screen."""
        try:
            # Check page title
            title = (await page.title()).lower()
            for kw in cls.HUMAN_CHALLENGE_KEYWORDS:
                if kw in title:
                    return True

            # Check page text content snippet
            body_text = (await page.evaluate("() => document.body ? document.body.innerText.slice(0, 800).toLowerCase() : ''"))
            for kw in cls.HUMAN_CHALLENGE_KEYWORDS:
                if kw in body_text:
                    return True

            # Check common challenge iframes/containers
            challenge_selectors = [
                "iframe[src*='cloudflare']",
                "iframe[src*='recaptcha']",
                "iframe[src*='hcaptcha']",
                "#challenge-running",
                "#cf-turnstile-wrapper",
            ]
            for sel in challenge_selectors:
                try:
                    if await page.locator(sel).first.is_visible(timeout=150):
                        return True
                except Exception:
                    pass
        except Exception:
            pass
        return False
