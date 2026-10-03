"""Retrieval package."""
from backend.retrieval.fetcher import fetch_page, RetrievedPage, extract_emails_from_text_and_html
from backend.retrieval.playwright_fallback import fetch_page_with_playwright

__all__ = [
    "fetch_page",
    "RetrievedPage",
    "extract_emails_from_text_and_html",
    "fetch_page_with_playwright"
]
