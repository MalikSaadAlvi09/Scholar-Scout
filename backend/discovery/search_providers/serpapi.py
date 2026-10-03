"""
SerpAPI (Google Search) Provider for ScholarScout.
https://serpapi.com
"""

import httpx
from typing import Optional, Dict, Any
from backend.discovery.search_providers.base import SearchProvider, SearchResponse, SearchResultItem
from backend.logging_utils import logger

class SerpApiProvider(SearchProvider):
    """
    Search provider using SerpAPI for structured Google Search results.
    Uses SERPAPI_API_KEY or SEARCH_API_KEY.
    """

    def __init__(self, api_key: Optional[str] = None, timeout: float = 20.0):
        self._api_key = (api_key or "").strip()
        self._timeout = timeout
        self._endpoint = "https://serpapi.com/search.json"

    @property
    def provider_name(self) -> str:
        return "serpapi"

    @property
    def display_name(self) -> str:
        return "SerpAPI (Google Search)"

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
                error_message="SerpAPI API key is not configured. Please set SERPAPI_API_KEY or SEARCH_API_KEY in backend settings."
            )

        params: Dict[str, Any] = {
            "api_key": self._api_key,
            "engine": "google",
            "q": query,
            "num": max(1, min(max_results, 30)),
            "output": "json"
        }
        if country:
            params["gl"] = country.lower()

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(self._endpoint, params=params)

                if response.status_code == 401 or response.status_code == 403:
                    return SearchResponse(
                        query=query,
                        provider_name=self.provider_name,
                        error_message=f"SerpAPI authentication failed (HTTP {response.status_code}). Please check your API key."
                    )

                if response.status_code != 200:
                    return SearchResponse(
                        query=query,
                        provider_name=self.provider_name,
                        error_message=f"SerpAPI search failed with HTTP status {response.status_code}: {response.text[:200]}"
                    )

                data = response.json()
                if "error" in data:
                    return SearchResponse(
                        query=query,
                        provider_name=self.provider_name,
                        error_message=f"SerpAPI returned error: {data['error']}"
                    )

                organic_results = data.get("organic_results", [])
                results = []
                for item in organic_results:
                    url = item.get("link", "").strip()
                    title = item.get("title", "").strip() or "Untitled Lead"
                    snippet = item.get("snippet", "").strip()
                    date_val = item.get("date")

                    if url:
                        results.append(SearchResultItem(
                            title=title,
                            url=url,
                            snippet=snippet,
                            published_date=date_val,
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
            logger.warning(f"[SerpAPI] Search timeout for query: {query}")
            return SearchResponse(
                query=query,
                provider_name=self.provider_name,
                error_message="SerpAPI search request timed out."
            )
        except Exception as e:
            logger.error(f"[SerpAPI] Search error: {e}")
            return SearchResponse(
                query=query,
                provider_name=self.provider_name,
                error_message=f"SerpAPI search error: {str(e)}"
            )

    async def validate_credentials(self) -> Dict[str, Any]:
        if not self.is_configured():
            return {
                "success": False,
                "valid": False,
                "provider": self.provider_name,
                "provider_name": self.provider_name,
                "error_type": "missing_credentials",
                "message": "SerpAPI API key is not set."
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
            "message": f"Successfully authenticated with SerpAPI ({len(test_res.results)} test results returned)."
        }
