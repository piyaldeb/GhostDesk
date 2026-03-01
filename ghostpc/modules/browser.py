"""
GhostPC Browser Module
Playwright-based browser automation for web scraping, form filling, and searches.
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Services that must be accessed via their native API modules, never via browser.
# Maps URL fragment → recommended module/function to show in the error.
_API_ONLY = {
    "mail.google.com":           "google_services.get_gmail_messages()",
    "gmail.com":                 "google_services.get_gmail_messages() or email.get_emails()",
    "docs.google.com/spreadsheet": "document.read_google_sheet()",
    "docs.google.com/document":  "google_services.read_google_doc()",
    "drive.google.com":          "google_services.list_drive_files()",
    "calendar.google.com":       "google_services.list_calendar_events()",
    "sheets.googleapis.com":     "document.read_google_sheet()",
    "outlook.live.com":          "email.get_emails()",
    "outlook.office.com":        "email.get_emails()",
}


def _api_only_check(url: str) -> Optional[dict]:
    """Return an error dict if this URL belongs to a service with a native API module."""
    u = url.lower()
    for fragment, module in _API_ONLY.items():
        if fragment in u:
            msg = (
                f"⛔ Browser blocked for API-supported service.\n"
                f"Use `{module}` instead — it connects directly without opening a browser."
            )
            return {"success": False, "error": msg, "text": msg}
    return None


def _chromium_exe_path() -> Optional[str]:
    """Return the expected Playwright chromium executable path, or None if not found."""
    try:
        import glob, os
        base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright")
        hits = glob.glob(os.path.join(base, "chromium-*", "chrome-win64", "chrome.exe"))
        if hits:
            return hits[0]
        # Mac / Linux
        hits2 = glob.glob(os.path.join(os.path.expanduser("~"), ".cache", "ms-playwright",
                                        "chromium-*", "chrome-linux", "chrome"))
        return hits2[0] if hits2 else None
    except Exception:
        return None


def _ensure_playwright_browsers():
    """Install Playwright chromium browser if the binary is missing."""
    import subprocess, sys
    # Fast-path: binary already present
    if _chromium_exe_path():
        logger.debug("Playwright chromium already installed — skipping install.")
        return
    logger.info("Playwright chromium not found — installing (this takes ~1 min)...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode == 0:
            logger.info("Playwright chromium installed successfully.")
        else:
            logger.warning(f"playwright install chromium failed:\n{result.stderr[:400]}")
    except Exception as e:
        logger.warning(f"Could not auto-install Playwright browsers: {e}")


async def _get_browser():
    """Launch a Playwright browser instance, auto-installing if needed."""
    import asyncio
    try:
        from playwright.async_api import async_playwright
        p = await async_playwright().start()
        browser = await p.chromium.launch(headless=True)
        return p, browser
    except Exception as first_err:
        # Browser binary missing — try to install and retry once
        if "Executable doesn't exist" in str(first_err) or "playwright install" in str(first_err):
            logger.info("Playwright browser not found — auto-installing chromium...")
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _ensure_playwright_browsers)
            try:
                from playwright.async_api import async_playwright
                p = await async_playwright().start()
                browser = await p.chromium.launch(headless=True)
                return p, browser
            except Exception as retry_err:
                raise RuntimeError(
                    f"Browser still unavailable after install attempt: {retry_err}"
                )
        raise RuntimeError(f"Failed to launch browser: {first_err}")


async def open_url(url: str, headless: bool = False) -> dict:
    """Open a URL in the browser (visible window)."""
    blocked = _api_only_check(url)
    if blocked:
        return blocked
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            try:
                browser = await p.chromium.launch(headless=headless)
            except Exception as launch_err:
                if "Executable doesn't exist" in str(launch_err) or "playwright install" in str(launch_err):
                    await asyncio.get_event_loop().run_in_executor(None, _ensure_playwright_browsers)
                    browser = await p.chromium.launch(headless=headless)
                else:
                    raise
            page = await browser.new_page()
            await page.goto(url, timeout=30000)
            title = await page.title()
            await asyncio.sleep(2)
            await browser.close()
            return {"success": True, "url": url, "title": title, "text": f"✅ Opened: {title}"}
    except Exception as e:
        logger.error(f"open_url error: {e}")
        return {"success": False, "error": str(e)}


async def get_page_text(url: str) -> dict:
    """Fetch a URL and return visible text content."""
    blocked = _api_only_check(url)
    if blocked:
        return blocked
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            text = await page.inner_text("body")
            title = await page.title()
            await browser.close()

            # Clean up whitespace
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            clean_text = "\n".join(lines)[:8000]

            return {
                "success": True,
                "url": url,
                "title": title,
                "text": clean_text,
                "content": clean_text,
            }
    except Exception as e:
        logger.error(f"get_page_text error: {e}")
        return {"success": False, "error": str(e)}


async def search_web(query: str, num_results: int = 5) -> dict:
    """Search Google and return top results."""
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            # Use DuckDuckGo for cleaner results without JS issues
            search_url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"
            await page.goto(search_url, timeout=30000)

            results = []
            result_elements = await page.query_selector_all(".result__body")

            for el in result_elements[:num_results]:
                try:
                    title_el = await el.query_selector(".result__title")
                    snippet_el = await el.query_selector(".result__snippet")
                    link_el = await el.query_selector(".result__url")

                    title = await title_el.inner_text() if title_el else ""
                    snippet = await snippet_el.inner_text() if snippet_el else ""
                    link = await link_el.inner_text() if link_el else ""

                    if title:
                        results.append({
                            "title": title.strip(),
                            "snippet": snippet.strip(),
                            "url": link.strip(),
                        })
                except Exception:
                    pass

            await browser.close()

            if not results:
                return {"success": False, "error": "No results found."}

            lines = [f"🔍 Results for: {query}\n"]
            for r in results:
                lines.append(f"• *{r['title']}*\n  {r['url']}\n  {r['snippet'][:100]}")

            return {
                "success": True,
                "results": results,
                "text": "\n".join(lines),
            }

    except Exception as e:
        logger.error(f"search_web error: {e}")
        return {"success": False, "error": str(e)}


async def scrape_page(url: str, selector: Optional[str] = None) -> dict:
    """Scrape a page and return its content for AI analysis."""
    blocked = _api_only_check(url)
    if blocked:
        return blocked
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, timeout=30000, wait_until="networkidle")

            if selector:
                try:
                    element = await page.query_selector(selector)
                    content = await element.inner_text() if element else ""
                except Exception:
                    content = await page.inner_text("body")
            else:
                content = await page.inner_text("body")

            title = await page.title()
            await browser.close()

            lines = [l.strip() for l in content.split("\n") if l.strip()]
            clean = "\n".join(lines)[:10000]

            return {
                "success": True,
                "url": url,
                "title": title,
                "content": clean,
                "text": clean,
            }
    except Exception as e:
        logger.error(f"scrape_page error: {e}")
        return {"success": False, "error": str(e)}


async def fill_form_on_web(url: str, fields: dict) -> dict:
    """
    Navigate to a URL and fill form fields.
    fields: { "label_or_placeholder_or_selector": "value" }
    """
    blocked = _api_only_check(url)
    if blocked:
        return blocked
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)  # Visible for form filling
            page = await browser.new_page()
            await page.goto(url, timeout=30000)

            filled = []
            failed = []

            for field, value in fields.items():
                try:
                    # Try various selectors
                    filled_this = False
                    for selector in [
                        f'input[placeholder*="{field}"]',
                        f'input[name*="{field}"]',
                        f'input[id*="{field}"]',
                        f'textarea[placeholder*="{field}"]',
                        f'label:has-text("{field}") + input',
                        field,  # Direct CSS selector
                    ]:
                        try:
                            el = await page.query_selector(selector)
                            if el:
                                await el.fill(str(value))
                                filled.append(field)
                                filled_this = True
                                break
                        except Exception:
                            pass

                    if not filled_this:
                        failed.append(field)

                except Exception as e:
                    failed.append(f"{field} ({e})")

            await asyncio.sleep(1)  # Pause before potential close
            await browser.close()

            text = f"✅ Filled: {', '.join(filled)}"
            if failed:
                text += f"\n⚠️ Could not fill: {', '.join(failed)}"

            return {"success": True, "filled": filled, "failed": failed, "text": text}

    except Exception as e:
        logger.error(f"fill_form_on_web error: {e}")
        return {"success": False, "error": str(e)}


async def click_element(url: str, selector: str) -> dict:
    """Navigate to a URL and click an element by CSS selector or text."""
    blocked = _api_only_check(url)
    if blocked:
        return blocked
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page()
            await page.goto(url, timeout=30000)

            # Try CSS selector first, then text
            clicked = False
            try:
                await page.click(selector, timeout=5000)
                clicked = True
            except Exception:
                try:
                    await page.click(f"text={selector}", timeout=5000)
                    clicked = True
                except Exception:
                    pass

            await asyncio.sleep(2)
            await browser.close()

            if clicked:
                return {"success": True, "text": f"✅ Clicked: {selector}"}
            else:
                return {"success": False, "error": f"Element not found: {selector}"}

    except Exception as e:
        logger.error(f"click_element error: {e}")
        return {"success": False, "error": str(e)}


async def take_screenshot_of_url(url: str, output_path: Optional[str] = None) -> dict:
    """Take a screenshot of a web page."""
    blocked = _api_only_check(url)
    if blocked:
        return blocked
    try:
        from playwright.async_api import async_playwright
        from pathlib import Path
        from datetime import datetime

        if not output_path:
            from config import TEMP_DIR
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = str(TEMP_DIR / f"web_screenshot_{ts}.png")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1280, "height": 800})
            await page.goto(url, timeout=30000)
            await page.screenshot(path=output_path, full_page=True)
            await browser.close()

        return {
            "success": True,
            "file_path": output_path,
            "caption": f"Screenshot of {url}",
            "text": f"✅ Screenshot saved: {output_path}",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
