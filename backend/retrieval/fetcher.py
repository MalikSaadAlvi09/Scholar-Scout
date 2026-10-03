"""
HTTP Page Retrieval, PDF Parsing & Playwright Fallback for ScholarScout.
Combines fast async HTTP, SSRF security guards, robots.txt compliance,
per-domain rate limiting, page caching, and text-based PDF extraction.
"""

import re
import io
from typing import Dict, Any, Optional, List, Tuple
from urllib.parse import urljoin, urlparse
import httpx
from bs4 import BeautifulSoup

try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

from backend.config import config
from backend.logging_utils import logger
from backend.retrieval.ssrf_guard import is_safe_target_url, validate_redirect_target
from backend.retrieval.robots import robots_manager
from backend.retrieval.rate_limiter import domain_rate_limiter
from backend.retrieval.cache import get_cached_page, set_cached_page, compute_content_hash
from backend.retrieval.playwright_fallback import fetch_page_with_playwright
from backend.discovery.url_normalizer import normalize_url

DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 ScholarScout/1.0 (+https://scholarscout.academic/research; bot@scholarscout.academic)"

DEFAULT_HEADERS = {
    "User-Agent": DEFAULT_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf;q=0.8,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# Bot detection / login wall signatures
CHALLENGE_PATTERNS = [
    r"cf-turnstile",
    r"challenges\.cloudflare\.com",
    r"just a moment\.\.\.",
    r"checking your browser before accessing",
    r"access denied\s*\|\s*cloudflare",
    r"attention required!\s*\|\s*cloudflare",
    r"distil_identification_block",
    r"incapsula_resource",
    r"perimeterx",
    r"datadome",
    r"please verify you are a human",
    r"enter the captcha"
]

LOGIN_PATTERNS = [
    r"shibboleth\.sso",
    r"/cas/login",
    r"login\.microsoftonline\.com",
    r"accounts\.google\.com/signin",
    r"university single sign-on",
    r"institutional login required"
]

class RetrievedPage:
    def __init__(
        self,
        url: str,
        status_code: int,
        title: str,
        text_content: str,
        html_content: str,
        links: List[Dict[str, str]],
        emails: List[str],
        retrieval_method: str = "http",
        page_status: str = "success",
        status_reason: str = "Retrieved successfully",
        content_hash: str = "",
        byte_size: int = 0
    ):
        self.url = url
        self.normalized_url = normalize_url(url)
        self.status_code = status_code
        self.title = title
        self.text_content = text_content
        self.html_content = html_content
        self.links = links
        self.emails = emails
        self.retrieval_method = retrieval_method
        self.page_status = page_status  # success, blocked, inaccessible, failed, scanned_document, skipped
        self.status_reason = status_reason
        self.content_hash = content_hash or compute_content_hash(text_content or html_content)
        self.byte_size = byte_size or len(text_content.encode("utf-8", errors="ignore"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "normalized_url": self.normalized_url,
            "status_code": self.status_code,
            "title": self.title,
            "text_preview": self.text_content[:300] if self.text_content else "",
            "links_count": len(self.links),
            "emails": self.emails,
            "retrieval_method": self.retrieval_method,
            "page_status": self.page_status,
            "status_reason": self.status_reason,
            "content_hash": self.content_hash,
            "byte_size": self.byte_size
        }

def extract_emails_from_text_and_html(text: str, html: str) -> List[str]:
    """Finds publicly listed academic emails via regex and mailto: links."""
    emails = set()

    # 1. Regex search for standard emails
    email_regex = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
    for match in email_regex.findall(text):
        email_clean = match.strip().lower()
        if not email_clean.endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp')):
            emails.add(email_clean)

    # 2. Extract from mailto: links
    if html:
        try:
            soup = BeautifulSoup(html, "html.parser")
            for mailto_tag in soup.find_all("a", href=re.compile(r"^mailto:", re.I)):
                href = mailto_tag.get("href", "")
                parts = href.split(":", 1)
                if len(parts) > 1:
                    clean_email = parts[1].split("?")[0].strip().lower()
                    if "@" in clean_email:
                        emails.add(clean_email)
        except Exception:
            pass

    return sorted(list(emails))

def clean_extracted_text(soup: BeautifulSoup) -> str:
    """Strips boilerplate, navigation, scripts, and formats clean readable text."""
    # Remove unwanted tags
    for element in soup(["script", "style", "noscript", "svg", "header", "footer", "nav", "aside", "form"]):
        element.decompose()

    # Find main content if available
    main_content = soup.find("main") or soup.find("article") or soup.find("div", class_=re.compile(r"(content|main|body|page-content)", re.I)) or soup.body
    
    if not main_content:
        return ""

    # Extract text with smart spacing
    lines = []
    for element in main_content.find_all(["h1", "h2", "h3", "h4", "p", "li", "td", "th", "dt", "dd"]):
        txt = element.get_text(strip=True)
        if txt and len(txt) > 3:
            lines.append(txt)

    if not lines:
        return main_content.get_text(separator="\n", strip=True)

    return "\n".join(lines)

def extract_page_links(base_url: str, soup: BeautifulSoup) -> List[Dict[str, str]]:
    """Extracts and resolves all valid HTTP(S) links on the page."""
    from backend.discovery.url_normalizer import normalize_url
    discovered = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href or href.startswith(("#", "javascript:", "tel:", "mailto:")):
            continue

        resolved = urljoin(base_url, href)
        parsed = urlparse(resolved)
        
        # Keep only HTTP / HTTPS
        if parsed.scheme not in ("http", "https"):
            continue

        # Clean URL
        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if parsed.query:
            clean_url += f"?{parsed.query}"

        norm = normalize_url(clean_url)
        if norm in seen:
            continue
        seen.add(norm)

        anchor_text = a.get_text(strip=True)
        discovered.append({
            "url": clean_url,
            "normalized_url": norm,
            "text": anchor_text
        })

    return discovered

def detect_challenge_or_login(html: str, url: str) -> Optional[str]:
    """Detects CAPTCHA challenges or login walls."""
    html_lower = html.lower()
    for pattern in CHALLENGE_PATTERNS:
        if re.search(pattern, html_lower, re.I):
            return "CAPTCHA / Cloudflare Challenge Wall detected (bypassing disabled)"
    for pattern in LOGIN_PATTERNS:
        if re.search(pattern, html_lower, re.I) or re.search(pattern, url.lower(), re.I):
            return "Institutional Single Sign-On / Login Wall required"
    return None

def parse_pdf_document(pdf_bytes: Any, url: str = "") -> RetrievedPage:
    """Parses a text-based PDF document or identifies image-only scanned files."""
    if isinstance(pdf_bytes, str) and isinstance(url, (bytes, bytearray)):
        pdf_bytes, url = url, pdf_bytes
    if not isinstance(url, str):
        url = str(url or "")
    if not HAS_FITZ:
        return RetrievedPage(
            url=url,
            status_code=200,
            title="PDF Document",
            text_content="",
            html_content="",
            links=[],
            emails=[],
            retrieval_method="pdf",
            page_status="failed",
            status_reason="PyMuPDF not installed on backend."
        )

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        total_pages = len(doc)
        full_text = []
        has_images = False
        pdf_links = []

        for page_num in range(min(total_pages, 25)):  # Limit to first 25 pages
            page = doc[page_num]
            txt = page.get_text()
            if txt and txt.strip():
                full_text.append(txt.strip())
            if len(page.get_images()) > 0:
                has_images = True
            for link in page.get_links():
                if link.get("uri"):
                    pdf_links.append({"url": link["uri"], "text": "PDF Reference Link"})

        combined = "\n\n".join(full_text).strip()
        doc_title = doc.metadata.get("title") or url.split("/")[-1]

        if len(combined) < 50:
            if has_images:
                return RetrievedPage(
                    url=url,
                    status_code=200,
                    title=f"[Scanned] {doc_title}",
                    text_content="",
                    html_content="",
                    links=[],
                    emails=[],
                    retrieval_method="pdf",
                    page_status="scanned_document",
                    status_reason="Scanned image-only PDF without selectable text."
                )
            else:
                return RetrievedPage(
                    url=url,
                    status_code=200,
                    title=doc_title,
                    text_content="",
                    html_content="",
                    links=[],
                    emails=[],
                    retrieval_method="pdf",
                    page_status="failed",
                    status_reason="PDF document contains empty or unreadable content."
                )

        emails = extract_emails_from_text_and_html(combined, "")
        return RetrievedPage(
            url=url,
            status_code=200,
            title=f"[PDF] {doc_title}",
            text_content=combined,
            html_content="",
            links=pdf_links,
            emails=emails,
            retrieval_method="pdf",
            page_status="success",
            status_reason="Text-based PDF successfully parsed",
            byte_size=len(pdf_bytes)
        )

    except Exception as e:
        logger.error(f"[Fetcher] PDF parsing failed for {url}: {e}")
        return RetrievedPage(
            url=url,
            status_code=200,
            title="PDF Document",
            text_content="",
            html_content="",
            links=[],
            emails=[],
            retrieval_method="pdf",
            page_status="failed",
            status_reason=f"Failed to parse PDF: {str(e)}"
        )

parse_pdf_bytes = parse_pdf_document

async def fetch_page(
    url: str,
    use_playwright_fallback: bool = True,
    use_cache: bool = True,
    max_download_size_bytes: int = 5 * 1024 * 1024,
    custom_delay: Optional[float] = None
) -> RetrievedPage:
    """
    Fetches a web page or PDF document safely with SSRF protection, robots.txt compliance,
    per-domain rate limiting, and automated Playwright fallback.
    """
    timeout = config.crawl_timeout
    from backend.discovery.url_normalizer import normalize_url
    url_norm = normalize_url(url)

    # 1. SSRF Protection Validation
    is_safe, ssrf_reason = is_safe_target_url(url)
    if not is_safe:
        logger.warning(f"[Fetcher] SSRF Guard blocked URL '{url}': {ssrf_reason}")
        return RetrievedPage(
            url=url,
            status_code=400,
            title="Blocked URL",
            text_content="",
            html_content="",
            links=[],
            emails=[],
            page_status="skipped",
            status_reason=f"Security Policy: {ssrf_reason}"
        )

    # 2. Check Cache
    if use_cache:
        cached = get_cached_page(url_norm)
        if cached:
            return RetrievedPage(
                url=url,
                status_code=cached["status_code"],
                title=cached["title"],
                text_content=cached["text_content"],
                html_content=cached["html_content"],
                links=cached["links"],
                emails=cached["emails"],
                retrieval_method="cache",
                page_status="success",
                status_reason="Loaded from local page cache",
                content_hash=cached["content_hash"]
            )

    # 3. Robots.txt Compliance Check
    is_allowed, crawl_delay, robots_reason = await robots_manager.can_fetch(url)
    if not is_allowed:
        logger.info(f"[Fetcher] Robots.txt disallowed '{url}': {robots_reason}")
        return RetrievedPage(
            url=url,
            status_code=403,
            title="Access Restricted",
            text_content="",
            html_content="",
            links=[],
            emails=[],
            page_status="blocked",
            status_reason=robots_reason
        )

    # 4. Polite Per-Domain Rate Limiting
    delay = crawl_delay if crawl_delay is not None else custom_delay
    await domain_rate_limiter.wait_for_domain(url, custom_delay=delay)

    # 5. Handle Direct PDF URLs
    if url.lower().endswith(".pdf"):
        try:
            async with httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=timeout, follow_redirects=True, verify=False) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    page_obj = parse_pdf_document(resp.content, url)
                    if page_obj.page_status == "success" and use_cache:
                        set_cached_page(url_norm, page_obj.status_code, page_obj.title, page_obj.text_content, "", page_obj.links, page_obj.emails, "pdf", page_obj.content_hash)
                    return page_obj
                else:
                    return RetrievedPage(
                        url=url,
                        status_code=resp.status_code,
                        title="PDF Document",
                        text_content="",
                        html_content="",
                        links=[],
                        emails=[],
                        retrieval_method="pdf",
                        page_status="inaccessible" if resp.status_code == 404 else "failed",
                        status_reason=f"HTTP {resp.status_code}"
                    )
        except Exception as e:
            return RetrievedPage(
                url=url,
                status_code=0,
                title="PDF Document",
                text_content="",
                html_content="",
                links=[],
                emails=[],
                retrieval_method="pdf",
                page_status="failed",
                status_reason=str(e)
            )

    # 6. Standard Async HTTP Retrieval with Streaming Size Limit & Redirect Revalidation
    status_code = 0
    html_content = ""
    retrieval_method = "http"
    page_status = "success"
    status_reason = "Retrieved via HTTP"

    try:
        async with httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=timeout, follow_redirects=False, verify=False) as client:
            current_target = url
            redirect_count = 0
            max_redirects = 5

            while redirect_count < max_redirects:
                # Revalidate SSRF on each hop
                safe_hop, hop_reason = is_safe_target_url(current_target)
                if not safe_hop:
                    return RetrievedPage(
                        url=url,
                        status_code=400,
                        title="Blocked Redirect",
                        text_content="",
                        html_content="",
                        links=[],
                        emails=[],
                        page_status="skipped",
                        status_reason=f"SSRF Redirect Block: {hop_reason}"
                    )

                resp = await client.get(current_target)
                status_code = resp.status_code

                # Handle Redirects manually to ensure SSRF revalidation
                if resp.is_redirect and "location" in resp.headers:
                    redirect_target = resp.headers["location"]
                    is_safe_redir, resolved_redir, r_reason = validate_redirect_target(current_target, redirect_target)
                    if not is_safe_redir:
                        return RetrievedPage(
                            url=url,
                            status_code=status_code,
                            title="Blocked Redirect Target",
                            text_content="",
                            html_content="",
                            links=[],
                            emails=[],
                            page_status="skipped",
                            status_reason=f"Security Policy: {r_reason}"
                        )
                    current_target = resolved_redir
                    redirect_count += 1
                    continue
                else:
                    # Check Content-Type for PDF
                    c_type = resp.headers.get("content-type", "").lower()
                    if "application/pdf" in c_type:
                        page_obj = parse_pdf_document(resp.content, current_target)
                        if page_obj.page_status == "success" and use_cache:
                            set_cached_page(url_norm, page_obj.status_code, page_obj.title, page_obj.text_content, "", page_obj.links, page_obj.emails, "pdf", page_obj.content_hash)
                        return page_obj

                    # Check Content-Length size
                    c_len = int(resp.headers.get("content-length", 0))
                    if c_len > max_download_size_bytes or len(resp.content) > max_download_size_bytes:
                        return RetrievedPage(
                            url=url,
                            status_code=status_code,
                            title="Large File",
                            text_content="",
                            html_content="",
                            links=[],
                            emails=[],
                            page_status="skipped",
                            status_reason=f"Download size exceeded limit ({max_download_size_bytes} bytes)."
                        )

                    html_content = resp.text
                    break

    except httpx.ConnectTimeout:
        return RetrievedPage(url=url, status_code=0, title="", text_content="", html_content="", links=[], emails=[], page_status="inaccessible", status_reason="Connection timed out.")
    except httpx.ConnectError as e:
        return RetrievedPage(url=url, status_code=0, title="", text_content="", html_content="", links=[], emails=[], page_status="inaccessible", status_reason=f"Connection failed: {e}")
    except Exception as e:
        logger.warning(f"[Fetcher] HTTP fetch exception for {url}: {e}")
        page_status = "failed"
        status_reason = f"HTTP Error: {str(e)}"

    # 7. Check for Access Restrictions & Challenge Walls
    if html_content:
        challenge_reason = detect_challenge_or_login(html_content, url)
        if challenge_reason:
            logger.info(f"[Fetcher] Access restriction detected on {url}: {challenge_reason}")
            return RetrievedPage(
                url=url,
                status_code=status_code or 403,
                title="Access Restricted",
                text_content="",
                html_content=html_content,
                links=[],
                emails=[],
                page_status="blocked",
                status_reason=challenge_reason
            )

    # 8. Check if Playwright Fallback is needed (JavaScript SPA or empty body)
    is_spa_or_js_rendered = len(html_content.strip()) < 1500 or "<div id=\"root\"></div>" in html_content or "<div id=\"app\"></div>" in html_content
    
    if (status_code != 200 or is_spa_or_js_rendered) and use_playwright_fallback and page_status != "blocked":
        logger.info(f"[Fetcher] Triggering Playwright fallback for {url} (HTTP status: {status_code})")
        pw_html, pw_title, pw_status = await fetch_page_with_playwright(url, timeout_seconds=timeout)
        if pw_html and len(pw_html) > len(html_content):
            # Check Playwright output for challenge/login
            pw_challenge = detect_challenge_or_login(pw_html, url)
            if pw_challenge:
                return RetrievedPage(
                    url=url,
                    status_code=pw_status,
                    title="Access Restricted",
                    text_content="",
                    html_content=pw_html,
                    links=[],
                    emails=[],
                    retrieval_method="playwright",
                    page_status="blocked",
                    status_reason=pw_challenge
                )
            html_content = pw_html
            status_code = pw_status
            retrieval_method = "playwright"
            page_status = "success"
            status_reason = "Retrieved via Playwright Browser"

    if not html_content:
        return RetrievedPage(
            url=url,
            status_code=status_code,
            title="",
            text_content="",
            html_content="",
            links=[],
            emails=[],
            page_status="inaccessible" if status_code == 404 else "failed",
            status_reason=status_reason or f"Empty response (Status: {status_code})"
        )

    # 9. Parse HTML Content
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        text = clean_extracted_text(soup)
        links = extract_page_links(url, soup)
        emails = extract_emails_from_text_and_html(text, html_content)
        chash = compute_content_hash(text or html_content)

        page_obj = RetrievedPage(
            url=url,
            status_code=status_code,
            title=title,
            text_content=text,
            html_content=html_content,
            links=links,
            emails=emails,
            retrieval_method=retrieval_method,
            page_status=page_status,
            status_reason=status_reason,
            content_hash=chash,
            byte_size=len(html_content.encode("utf-8", errors="ignore"))
        )

        if use_cache and page_status == "success" and text:
            set_cached_page(url_norm, status_code, title, text, html_content, links, emails, retrieval_method, chash)

        return page_obj

    except Exception as e:
        logger.error(f"[Fetcher] Failed to parse HTML from {url}: {e}")
        return RetrievedPage(
            url=url,
            status_code=status_code,
            title="Parse Error",
            text_content="",
            html_content=html_content,
            links=[],
            emails=[],
            page_status="failed",
            status_reason=f"HTML parsing exception: {e}"
        )
