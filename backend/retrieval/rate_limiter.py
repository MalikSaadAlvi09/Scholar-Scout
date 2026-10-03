"""
Per-Domain Rate Limiter & Concurrency Throttler for ScholarScout.
Enforces polite request delays across academic server domains to prevent overloading.
"""

import time
import asyncio
from typing import Dict
from urllib.parse import urlparse
from backend.logging_utils import logger

class DomainRateLimiter:
    """
    Asynchronous rate limiter that ensures minimum time intervals between requests
    to the same internet hostname/domain.
    """
    def __init__(self, default_delay_seconds: float = 0.5):
        self._default_delay = default_delay_seconds
        self._last_request_time: Dict[str, float] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    async def _get_domain_lock(self, domain: str) -> asyncio.Lock:
        async with self._global_lock:
            if domain not in self._locks:
                self._locks[domain] = asyncio.Lock()
            return self._locks[domain]

    async def wait_for_domain(self, url: str, custom_delay: float = None):
        """
        Blocks asynchronously until the required polite delay for the domain has passed.
        """
        try:
            parsed = urlparse(url)
            domain = (parsed.netloc or "default").lower()
        except Exception:
            domain = "default"

        delay = custom_delay if custom_delay is not None else self._default_delay
        lock = await self._get_domain_lock(domain)

        async with lock:
            last_time = self._last_request_time.get(domain, 0.0)
            now = time.time()
            elapsed = now - last_time

            if elapsed < delay:
                sleep_duration = delay - elapsed
                await asyncio.sleep(sleep_duration)

            self._last_request_time[domain] = time.time()

domain_rate_limiter = DomainRateLimiter(default_delay_seconds=0.4)
