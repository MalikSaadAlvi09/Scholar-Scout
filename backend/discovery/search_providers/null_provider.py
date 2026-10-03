"""
Null Search Provider for unconfigured environments.
Strictly informs users that no search provider is active, directing to configure API keys
or use single/batch university URL mode without simulating search or scraping.
"""

from typing import Optional, Dict, Any
from backend.discovery.search_providers.base import SearchProvider, SearchResponse

class NullSearchProvider(SearchProvider):
    """
    Fallback provider when no search API is configured.
    Returns clear explanations and disables discovery gracefully.
    """

    @property
    def provider_name(self) -> str:
        return "none"

    @property
    def display_name(self) -> str:
        return "No Search Provider Configured"

    def is_configured(self) -> bool:
        return False

    async def search(
        self,
        query: str,
        max_results: int = 10,
        country: Optional[str] = None
    ) -> SearchResponse:
        return SearchResponse(
            query=query,
            results=[],
            total_results_count=0,
            provider_name=self.provider_name,
            error_message=(
                "No search provider configured. To use Discovery Mode, please configure a supported Search API "
                "(Tavily, SerpAPI, or Brave Search) in backend settings, or use University URL Mode to enter/import university domains directly."
            )
        )

    async def validate_credentials(self) -> Dict[str, Any]:
        return {
            "success": False,
            "valid": False,
            "provider": self.provider_name,
            "provider_name": self.provider_name,
            "error_type": "missing_credentials",
            "message": "No search provider configured. Please add an API key for Tavily, SerpAPI, or Brave Search."
        }
