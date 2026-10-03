"""
Brave Search API Provider for ScholarScout.
https://brave.com/search/api/
"""

import httpx
from typing import Optional, Dict, Any
from backend.discovery.search_providers.base import SearchProvider, SearchResponse, SearchResultItem
from backend.logging_utils import logger

class BraveSearchProvider(SearchProvider):
    """
    Search provider using Brave Search API.
    Uses BRAVE_SEARCH_API_KEY or SEARCH_API_KEY.
    """

    def __init__(self, api_key: Optional[str] = None, timeout: float = 20.0):
        self._api_key = (api_key or "").strip()
        self._timeout = timeout
        self._endpoint = "https://api.search.brave.com/res/v1/web/search"

    @property
    def provider_name(self) -> str:
        return "brave"

    @property
    def display_name(self) -> str:
        return "Brave Search API"

    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def search(
        self,
        query: str,
        max_results: int = 10,
        country: Optional[str] = None
    ) -> SearchResponse:
        if not self.is_configured():
            return SearchResponse(
                query=query,
                provider_name=self.provider_name,
                error_message="Brave Search API key is not configured. Please set BRAVE_SEARCH_API_KEY or SEARCH_API_KEY in backend settings."
            )

        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self._api_key
        }
        params: Dict[str, Any] = {
            "q": query,
            "count": max(1, min(max_results, 20))
        }
        if country:
            params["country"] = country.upper()

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(self._endpoint, headers=headers, params=params)

                if response.status_code == 401 or response.status_code == 403:
                    return SearchResponse(
                        query=query,
                        provider_name=self.provider_name,
                        error_message=f"Brave Search authentication failed (HTTP {response.status_code}). Please check your API key."
                    )

                if response.status_code != 200:
                    return SearchResponse(
                        query=query,
                        provider_name=self.provider_name,
                        error_message=f"Brave search failed with HTTP status {response.status_code}: {response.text[:200]}"
                    )

                data = response.json()
                web_results = data.get("web", {}).get("results", [])

                results = []
                for item in web_results:
                    url = item.get("url", "").strip()
                    title = item.get("title", "").strip() or "Untitled Lead"
                    snippet = item.get("description", "").strip()
                    page_age = item.get("page_age")

                    if url:
                        results.append(SearchResultItem(
                            title=title,
                            url=url,
                            snippet=snippet,
                            published_date=page_age,
                            raw_payload=item
                        ))

                return SearchResponse(
                    query=query,
                    results=results,
                    total_results_count=len(results),
                    provider_name=self.provider_name,
                    credits_used=1
                )

        except httpx.TimeoutException:
            logger.warning(f"[Brave] Search timeout for query: {query}")
            return SearchResponse(
                query=query,
                provider_name=self.provider_name,
                error_message="Brave search request timed out."
            )
        except Exception as e:
            logger.error(f"[Brave] Search error: {e}")
            return SearchResponse(
                query=query,
                provider_name=self.provider_name,
                error_message=f"Brave search error: {str(e)}"
            )

    async def validate_credentials(self) -> Dict[str, Any]:
        if not self.is_configured():
            return {
                "success": False,
                "valid": False,
                "provider": self.provider_name,
                "provider_name": self.provider_name,
                "error_type": "missing_credentials",
                "message": "Brave Search API key is not set."
            }
        test_res = await self.search("test academic query", max_results=1)
        if test_res.error_message:
            return {
                "success": False,
                "valid": False,
                "provider": self.provider_name,
                "provider_name": self.provider_name,
                "error_type": "auth_failed",
                "message": test_res.error_message
            }
        return {
            "success": True,
            "valid": True,
            "provider": self.provider_name,
            "provider_name": self.provider_name,
            "message": f"Successfully authenticated with Brave Search ({len(test_res.results)} test results returned)."
        }
