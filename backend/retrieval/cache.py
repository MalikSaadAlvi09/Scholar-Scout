"""
Page Cache & SHA-256 Content Hashing for ScholarScout.
Provides persistent caching of retrieved HTML/PDF pages with content hashing
to prevent duplicate fetches and record data lineage.
"""

import hashlib
import json
import time
from typing import Optional, Dict, Any, Union
from backend.database import get_db_connection
from backend.logging_utils import logger

def compute_content_hash(content: Union[str, bytes]) -> str:
    """Computes a SHA-256 cryptographic hash of page content."""
    if isinstance(content, str):
        content_bytes = content.encode("utf-8", errors="replace")
    else:
        content_bytes = content
    return hashlib.sha256(content_bytes).hexdigest()

def get_cached_page(url: str, max_age_seconds: int = 86400) -> Optional[Dict[str, Any]]:
    """
    Retrieves a cached web page if it exists and has not expired.
    """
    try:
        conn = get_db_connection()
        row = conn.execute("""
        SELECT * FROM page_cache WHERE url = ?
        """, (url,)).fetchone()
        conn.close()

        if not row:
            return None

        # Check age
        created_at_epoch = row["created_at_epoch"]
        if time.time() - created_at_epoch > max_age_seconds:
            return None

        links = json.loads(row["links_json"]) if row["links_json"] else []
        emails = json.loads(row["emails_json"]) if row["emails_json"] else []

        return {
            "url": row["url"],
            "status_code": row["status_code"],
            "title": row["page_title"] or "",
            "text_content": row["text_content"] or "",
            "html_content": row["html_content"] or "",
            "links": links,
            "emails": emails,
            "content_hash": row["content_hash"],
            "retrieval_method": row["retrieval_method"] or "cache",
            "is_cache_hit": True
        }
    except Exception as e:
        logger.debug(f"[Cache] Lookup failed for {url}: {e}")
        return None

def set_cached_page(
    url: str,
    status_code: int,
    title: str,
    text_content: str,
    html_content: str,
    links: list,
    emails: list,
    retrieval_method: str = "http",
    content_hash: Optional[str] = None
) -> None:
    """
    Persists a retrieved web page to the SQLite cache with SHA-256 hash.
    """
    try:
        chash = content_hash or compute_content_hash(text_content or html_content)
        links_json = json.dumps(links) if links else "[]"
        emails_json = json.dumps(emails) if emails else "[]"
        now = time.time()

        conn = get_db_connection()
        conn.execute("""
        INSERT OR REPLACE INTO page_cache (
            url, content_hash, status_code, page_title, text_content, html_content,
            links_json, emails_json, retrieval_method, created_at_epoch
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            url, chash, status_code, title[:500] if title else "",
            text_content, html_content[:200000] if html_content else "",
            links_json, emails_json, retrieval_method, now
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.debug(f"[Cache] Failed to cache {url}: {e}")
