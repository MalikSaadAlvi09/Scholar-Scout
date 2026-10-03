"""
Base abstractions and data models for ScholarScout pluggable search providers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse

@dataclass
class SearchResultItem:
    """Represents a single search engine result item (lead)."""
    title: str
    url: str
    snippet: str
    source_domain: str = ""
    published_date: Optional[str] = None
    raw_payload: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.source_domain and self.url:
            try:
                self.source_domain = urlparse(self.url).netloc.lower().replace("www.", "")
            except Exception:
                self.source_domain = ""

@dataclass
class SearchResponse:
    """Standardized response container for search provider executions."""
    query: str
    results: List[SearchResultItem] = field(default_factory=list)
    total_results_count: int = 0
    provider_name: str = "unknown"
    credits_used: int = 0
    is_cached: bool = False
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "results": [
                {
                    "title": r.title,
                    "url": r.url,
                    "snippet": r.snippet,
                    "source_domain": r.source_domain,
                    "published_date": r.published_date
                }
                for r in self.results
            ],
            "total_results_count": self.total_results_count,
            "provider_name": self.provider_name,
            "credits_used": self.credits_used,
            "is_cached": self.is_cached,
            "error_message": self.error_message
        }

class SearchProvider(ABC):
    """Abstract base class for all pluggable search providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Returns the unique identifier for the provider (e.g. 'tavily', 'serpapi', 'brave')."""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable provider name."""
        pass

    @abstractmethod
    def is_configured(self) -> bool:
        """Returns True if the provider has the necessary credentials configured."""
        pass

    @abstractmethod
    async def search(
        self,
        query: str,
        max_results: int = 10,
        country: Optional[str] = None
    ) -> SearchResponse:
        """
        Executes a web search query and returns standardized SearchResponse.
        Treats snippets and results as leads only.
        """
        pass

    @abstractmethod
    async def validate_credentials(self) -> Dict[str, Any]:
        """Validates API credentials by running a lightweight test query."""
        pass
