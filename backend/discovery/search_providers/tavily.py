"""
Tavily Search API Provider for ScholarScout.
https://tavily.com
"""

import httpx
from typing import Optional, Dict, Any
from backend.discovery.search_providers.base import SearchProvider, SearchResponse, SearchResultItem
from backend.logging_utils import logger

class TavilySearchProvider(SearchProvider):
    """
    Search provider using Tavily's AI-optimized search API.
    Uses TAVILY_API_KEY or SEARCH_API_KEY.
    """

    def __init__(self, api_key: Optional[str] = None, timeout: float = 20.0):
        self._api_key = (api_key or "").strip()
        self._timeout = timeout
        self._endpoint = "https://api.tavily.com/search"

    @property
    def provider_name(self) -> str:
        return "tavily"

    @property
    def display_name(self) -> str:
        return "Tavily Search API"

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
                error_message="Tavily API key is not configured. Please set TAVILY_API_KEY or SEARCH_API_KEY in backend settings."
            )

        # Build payload
        payload: Dict[str, Any] = {
            "api_key": self._api_key,
            "query": query,
            "search_depth": "basic",
            "include_answer": False,
            "include_raw_content": False,
            "max_results": max(1, min(max_results, 30))
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(self._endpoint, json=payload)
                
                if response.status_code == 401 or response.status_code == 403:
                    return SearchResponse(
                        query=query,
                        provider_name=self.provider_name,
                        error_message=f"Tavily authentication failed (HTTP {response.status_code}). Please check your API key."
                    )
                
                if response.status_code != 200:
                    return SearchResponse(
                        query=query,
                        provider_name=self.provider_name,
                        error_message=f"Tavily search failed with HTTP status {response.status_code}: {response.text[:200]}"
                    )

                data = response.json()
                raw_results = data.get("results", [])

                results = []
                for item in raw_results:
                    url = item.get("url", "").strip()
                    title = item.get("title", "").strip() or "Untitled Lead"
                    snippet = item.get("content", "").strip()
                    published_date = item.get("published_date")

                    if url:
                        results.append(SearchResultItem(
                            title=title,
                            url=url,
                            snippet=snippet,
                            published_date=published_date,
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
            logger.warning(f"[Tavily] Search timeout for query: {query}")
            return SearchResponse(
                query=query,
                provider_name=self.provider_name,
                error_message="Tavily search request timed out."
            )
        except Exception as e:
            logger.error(f"[Tavily] Search error: {e}")
            return SearchResponse(
                query=query,
                provider_name=self.provider_name,
                error_message=f"Tavily search error: {str(e)}"
            )

    async def validate_credentials(self) -> Dict[str, Any]:
        if not self.is_configured():
            return {
                "success": False,
                "valid": False,
                "provider": self.provider_name,
                "provider_name": self.provider_name,
                "error_type": "missing_credentials",
                "message": "Tavily API key is not set."
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
            "message": f"Successfully authenticated with Tavily ({len(test_res.results)} test results returned)."
        }
