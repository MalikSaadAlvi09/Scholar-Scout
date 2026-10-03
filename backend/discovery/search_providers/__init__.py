"""
Search providers package for ScholarScout discovery mode.
"""

from backend.discovery.search_providers.base import SearchProvider, SearchResponse, SearchResultItem
from backend.discovery.search_providers.tavily import TavilySearchProvider
from backend.discovery.search_providers.serpapi import SerpApiProvider
from backend.discovery.search_providers.brave import BraveSearchProvider
from backend.discovery.search_providers.null_provider import NullSearchProvider
from backend.discovery.search_providers.factory import get_search_provider

__all__ = [
    "SearchProvider",
    "SearchResponse",
    "SearchResultItem",
    "TavilySearchProvider",
    "SerpApiProvider",
    "BraveSearchProvider",
    "NullSearchProvider",
    "get_search_provider"
]
