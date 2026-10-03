"""
Factory for resolving and instantiating Search Providers in ScholarScout.
"""

import os
from typing import Optional
from backend.config import config
from backend.discovery.search_providers.base import SearchProvider
from backend.discovery.search_providers.tavily import TavilySearchProvider
from backend.discovery.search_providers.serpapi import SerpApiProvider
from backend.discovery.search_providers.brave import BraveSearchProvider
from backend.discovery.search_providers.null_provider import NullSearchProvider

def get_search_provider(
    provider_name: Optional[str] = None,
    api_key: Optional[str] = None
) -> SearchProvider:
    """
    Returns an instance of the configured SearchProvider.
    Checks explicit provider parameter, config.search_provider, or environment variables.
    Falls back to NullSearchProvider if unconfigured.
    """
    selected_name = (
        provider_name
        or getattr(config, "search_provider", None)
        or os.getenv("SEARCH_PROVIDER", "")
    ).strip().lower()

    explicit_key = api_key or getattr(config, "search_api_key", None) or os.getenv("SEARCH_API_KEY", "")

    # 1. Tavily
    if selected_name == "tavily" or (not selected_name and (os.getenv("TAVILY_API_KEY") or explicit_key)):
        key = explicit_key or os.getenv("TAVILY_API_KEY", "")
        if key or selected_name == "tavily":
            return TavilySearchProvider(api_key=key)

    # 2. SerpAPI
    if selected_name in ("serpapi", "google") or (not selected_name and os.getenv("SERPAPI_API_KEY")):
        key = explicit_key or os.getenv("SERPAPI_API_KEY", "")
        if key or selected_name in ("serpapi", "google"):
            return SerpApiProvider(api_key=key)

    # 3. Brave Search
    if selected_name == "brave" or (not selected_name and os.getenv("BRAVE_SEARCH_API_KEY")):
        key = explicit_key or os.getenv("BRAVE_SEARCH_API_KEY", "")
        if key or selected_name == "brave":
            return BraveSearchProvider(api_key=key)

    # Default to NullSearchProvider (graceful fallback)
    return NullSearchProvider()
