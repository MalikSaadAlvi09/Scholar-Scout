"""
Robots.txt Evaluator & Cache for ScholarScout.
Respects academic web crawling policies, Crawl-delay directives, and path disallow rules.
"""

import time
import asyncio
from typing import Dict, Tuple, Optional
from urllib.parse import urlparse
import urllib.robotparser
import httpx
from backend.logging_utils import logger
from backend.retrieval.ssrf_guard import is_safe_target_url

BOT_USER_AGENTS = ["ScholarScoutAcademicBot/1.0", "ScholarScoutBot", "*"]

class RobotsPolicyManager:
    """
    Asynchronous parser and cache for domain robots.txt files.
    """
    def __init__(self, cache_ttl_seconds: int = 3600):
        self._cache: Dict[str, Tuple[Optional[urllib.robotparser.RobotFileParser], float]] = {}
        self._ttl = cache_ttl_seconds
        self._lock = asyncio.Lock()

    async def can_fetch(
        self,
        url: str,
        user_agent: str = "ScholarScoutAcademicBot/1.0",
        timeout: float = 6.0
    ) -> Tuple[bool, Optional[float], str]:
        """
        Determines if a URL is allowed under the domain's robots.txt.
        Returns (is_allowed: bool, crawl_delay: Optional[float], reason: str).
        """
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return True, None, "Invalid URL structure."

        domain_key = f"{parsed.scheme}://{parsed.netloc}".lower()
        now = time.time()

        parser = None
        async with self._lock:
            if domain_key in self._cache:
                cached_parser, timestamp = self._cache[domain_key]
                if now - timestamp < self._ttl:
                    parser = cached_parser

        if parser is None:
            parser = await self._fetch_robots_txt(domain_key, timeout)
            async with self._lock:
                self._cache[domain_key] = (parser, now)

        if parser is None:
            # If robots.txt cannot be fetched or doesn't exist (404), standard web practice allows crawling
            return True, None, "No robots.txt restrictions found (allowed)."

        # Test user agents in priority order
        allowed = True
        crawl_delay = None

        for ua in [user_agent, "ScholarScoutBot", "*"]:
            try:
                if not parser.can_fetch(ua, url):
                    allowed = False
                    reason = f"Disallowed by robots.txt rule for User-Agent: {ua}"
                    return False, None, reason
                
                # Check crawl delay
                delay = parser.crawl_delay(ua)
                if delay is not None:
                    crawl_delay = float(delay)
            except Exception:
                pass

        return True, crawl_delay, "Permitted by robots.txt policy."

    async def _fetch_robots_txt(self, domain_base: str, timeout: float) -> Optional[urllib.robotparser.RobotFileParser]:
        """Fetches and parses robots.txt for the given domain safely."""
        robots_url = f"{domain_base}/robots.txt"
        
        is_safe, reason = is_safe_target_url(robots_url)
        if not is_safe:
            logger.warning(f"[Robots.txt] Skipped SSRF-restricted domain '{domain_base}': {reason}")
            return None

        try:
            headers = {"User-Agent": "ScholarScoutAcademicBot/1.0 (+https://scholarscout.academic/bot)"}
            async with httpx.AsyncClient(timeout=timeout, verify=False, follow_redirects=True) as client:
                resp = await client.get(robots_url, headers=headers)
                if resp.status_code == 200 and resp.text:
                    rp = urllib.robotparser.RobotFileParser()
                    rp.parse(resp.text.splitlines())
                    return rp
                elif resp.status_code in (401, 403):
                    # If robots.txt is forbidden, treat everything as disallowed
                    rp = urllib.robotparser.RobotFileParser()
                    rp.parse(["User-agent: *", "Disallow: /"])
                    return rp
        except Exception as e:
            logger.debug(f"[Robots.txt] Could not retrieve robots.txt for {domain_base}: {e}")

        return None

robots_manager = RobotsPolicyManager()
