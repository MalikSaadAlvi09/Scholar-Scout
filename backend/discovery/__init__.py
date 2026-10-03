"""
Discovery package for ScholarScout.
Includes web crawler, URL normalizer, search providers, query generator, and discovery engine.
"""

from backend.discovery.crawler import UniversityCrawler
from backend.discovery.url_normalizer import (
    normalize_url,
    get_root_institutional_domain,
    is_same_institution_domain,
    classify_domain_type
)
from backend.discovery.search_providers import (
    SearchProvider,
    SearchResponse,
    SearchResultItem,
    get_search_provider
)
from backend.discovery.query_generator import generate_discovery_queries
from backend.discovery.engine import DiscoveryEngine

__all__ = [
    "UniversityCrawler",
    "normalize_url",
    "get_root_institutional_domain",
    "is_same_institution_domain",
    "classify_domain_type",
    "SearchProvider",
    "SearchResponse",
    "SearchResultItem",
    "get_search_provider",
    "generate_discovery_queries",
    "DiscoveryEngine"
]
