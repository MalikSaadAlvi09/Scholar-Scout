"""
Playwright Headless Browser Fallback.
Used when standard HTTP requests encounter JavaScript single-page rendering,
bot challenges, or require dynamic DOM evaluation.
"""

from typing import Optional, Tuple
from backend.logging_utils import logger
from backend.retrieval.ssrf_guard import is_safe_target_url

async def fetch_page_with_playwright(url: str, timeout_seconds: int = 15) -> Tuple[Optional[str], Optional[str], int]:
    """
    Fetches dynamic webpage using Playwright headless Chromium.
    Enforces SSRF validation on target URL and all browser subrequests.
    Returns (html_content, page_title, status_code).
    """
    is_safe, reason = is_safe_target_url(url)
    if not is_safe:
        logger.warning(f"[Playwright SSRF Guard] Target URL blocked: {url} ({reason})")
        return None, None, 403

    try:
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            # Launch headless browser with lightweight arguments
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 ScholarScout/1.0",
                viewport={"width": 1280, "height": 800}
            )
            page = await context.new_page()
            
            # Intercept and revalidate all browser subrequests to prevent SSRF
            async def handle_subrequest(route, request):
                req_url = request.url
                if req_url.startswith("data:") or req_url.startswith("about:") or req_url.startswith("blob:"):
                    await route.continue_()
                    return
                safe, _ = is_safe_target_url(req_url)
                if not safe:
                    await route.abort()
                else:
                    await route.continue_()

            await page.route("**/*", handle_subrequest)
            
            # Set timeout
            page.set_default_timeout(timeout_seconds * 1000)
            
            # Navigate to URL
            response = await page.goto(url, wait_until="domcontentloaded")
            
            # Wait briefly for dynamic JS rendering
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass # Proceed even if networkidle times out
                
            status_code = response.status if response else 200
            html = await page.content()
            title = await page.title()
            
            await browser.close()
            logger.info(f"[Playwright Fallback] Successfully fetched dynamic page: {url} (Status: {status_code})")
            return html, title, status_code
            
    except Exception as e:
        logger.warning(f"[Playwright Fallback] Playwright retrieval failed for {url}: {e}")
        return None, None, 500
