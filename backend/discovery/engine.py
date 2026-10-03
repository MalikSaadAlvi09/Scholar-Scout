"""
ScholarScout Autonomous Discovery & Research Engine.
Executes cached search provider queries, performs institutional deduplication and domain isolation,
enforces country/subject filters, manages quota limits, tracks query provenance,
and compiles comprehensive coverage reports.
"""

import hashlib
import json
import re
from typing import List, Dict, Any, Optional, Set, Tuple
from urllib.parse import urlparse
from backend.logging_utils import logger
from backend.discovery.search_providers.base import SearchProvider, SearchResponse, SearchResultItem
from backend.discovery.search_providers.factory import get_search_provider
from backend.discovery.query_generator import generate_discovery_queries
from backend.discovery.url_normalizer import (
    normalize_url,
    get_root_institutional_domain,
    classify_domain_type,
    RECOGNIZED_SCHOLARSHIP_PROVIDERS
)
from backend.database import (
    get_cached_search,
    set_cached_search
)

# Common commercial aggregator domains to treat as third-party leads rather than official institutions
COMMERCIAL_AGGREGATORS = {
    "findaphd.com", "findamasters.com", "scholarshipowl.com", "fastweb.com",
    "scholarships.com", "postgrad.com", "studyportals.com", "mastersportal.com",
    "bachelorsportal.com", "phdportal.com", "topuniversities.com", "timeshighereducation.com",
    "usnews.com", "educations.com", "scholarshipportal.com", "goabroad.com",
    "wemakescholars.com", "internationalscholarships.com", "profellow.com"
}

def is_academic_domain(domain: str) -> bool:
    """Checks whether a domain belongs to an educational/research institution."""
    d = domain.lower()
    if any(d.endswith(suffix) for suffix in [
        ".edu", ".ac.uk", ".edu.au", ".ac.jp", ".edu.sg", ".ac.in", ".ac.nz",
        ".edu.cn", ".ac.kr", ".edu.hk", ".edu.my", ".edu.pk", ".edu.eg",
        ".ac.za", ".edu.tw", ".edu.br", ".edu.mx", ".edu.tr", ".edu.co"
    ]):
        return True
    # European universities often use .de, .ch, .se, .nl, .fr with 'uni-' or university name
    if any(keyword in d for keyword in ["uni-", "univ-", "tu-", "rwth-", "ethz", "epfl", "kit.edu", "ox.ac.uk", "cam.ac.uk", "tum.de", "lmu.de", "inria.fr", "cnrs.fr"]):
        return True
    return False

def guess_country_from_domain(domain: str) -> str:
    """Guesses country of an institution from domain TLD."""
    d = domain.lower()
    if d.endswith(".edu") or d.endswith(".us"):
        return "United States"
    if d.endswith(".ac.uk") or d.endswith(".uk"):
        return "United Kingdom"
    if d.endswith(".de"):
        return "Germany"
    if d.endswith(".ca"):
        return "Canada"
    if d.endswith(".edu.au") or d.endswith(".au"):
        return "Australia"
    if d.endswith(".ch"):
        return "Switzerland"
    if d.endswith(".se"):
        return "Sweden"
    if d.endswith(".nl"):
        return "Netherlands"
    if d.endswith(".ac.jp") or d.endswith(".jp"):
        return "Japan"
    if d.endswith(".edu.sg") or d.endswith(".sg"):
        return "Singapore"
    if d.endswith(".fr"):
        return "France"
    if d.endswith(".ie"):
        return "Ireland"
    return "Unknown"

def clean_institution_name(raw_title: str, domain: str) -> str:
    """Extracts a clean, human-readable institution name from search result title and domain."""
    # Strip common suffixes like '| Computer Science', '- Department', etc.
    cleaned = raw_title
    for sep in [" | ", " - ", " – ", " — ", ": "]:
        if sep in cleaned:
            parts = cleaned.split(sep)
            # Pick the part mentioning University/College/Institute or shortest
            uni_parts = [p for p in parts if any(k in p.lower() for k in ["university", "college", "institute", "school", "faculty", "academy", "polytechnic"])]
            if uni_parts:
                cleaned = uni_parts[0]
            else:
                cleaned = parts[0]
            break

    cleaned = cleaned.strip()
    # Fallback to domain root if title is too generic
    if len(cleaned) < 4 or cleaned.lower() in ("home", "index", "overview", "scholarships", "department"):
        root = domain.split(".")[0].replace("www.", "").replace("-", " ")
        cleaned = root.title() + " University"
    return cleaned

class DiscoveryEngine:
    """
    Coordinates multi-query execution, search caching, lead filtering,
    institutional deduplication, and coverage reporting.
    """

    def __init__(
        self,
        search_provider: Optional[SearchProvider] = None,
        max_queries: int = 5,
        max_results_per_query: int = 10,
        max_universities: int = 5
    ):
        self.provider = search_provider or get_search_provider()
        self.max_queries = max_queries
        self.max_results_per_query = max_results_per_query
        self.max_universities = max_universities

    def hash_query(self, query: str) -> str:
        """Calculates deterministic hash for query caching."""
        key_str = f"{self.provider.provider_name}:{query.strip().lower()}"
        return hashlib.sha256(key_str.encode("utf-8")).hexdigest()

    async def execute_cached_search(self, query: str, country: Optional[str] = None) -> SearchResponse:
        """Executes a search query checking SQLite cache first."""
        q_hash = self.hash_query(query)
        cached = get_cached_search(q_hash, max_age_days=7)

        if cached:
            logger.info(f"[Discovery] Cache hit for query: '{query}' ({len(cached['results'])} results)")
            return SearchResponse(
                query=query,
                results=[
                    SearchResultItem(
                        title=r.get("title", ""),
                        url=r.get("url", ""),
                        snippet=r.get("snippet", ""),
                        source_domain=r.get("source_domain", ""),
                        published_date=r.get("published_date")
                    )
                    for r in cached.get("results", [])
                ],
                total_results_count=cached.get("result_count", len(cached.get("results", []))),
                provider_name=self.provider.provider_name,
                credits_used=0,
                is_cached=True
            )

        # Fresh provider query
        logger.info(f"[Discovery] Executing provider search ({self.provider.provider_name}) for: '{query}'")
        resp = await self.provider.search(
            query=query,
            max_results=self.max_results_per_query,
            country=country
        )

        if resp.results and not resp.error_message:
            # Store in cache
            dict_results = [
                {
                    "title": r.title,
                    "url": r.url,
                    "snippet": r.snippet,
                    "source_domain": r.source_domain,
                    "published_date": r.published_date
                }
                for r in resp.results
            ]
            set_cached_search(
                query_hash=q_hash,
                query_text=query,
                provider=self.provider.provider_name,
                results=dict_results,
                count=len(dict_results)
            )

        return resp

    async def discover_institutions(
        self,
        profile: Dict[str, Any],
        custom_queries: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Executes discovery workflow for candidate profile.
        Returns discovered institutions, leads, and comprehensive coverage statistics.
        """
        if not self.provider.is_configured():
            return {
                "success": False,
                "error": "No search provider is configured. Please configure an API key for Tavily, SerpAPI, or Brave, or enter university URLs directly.",
                "discovered_institutions": [],
                "coverage_report": self._empty_coverage_report("No search provider configured.")
            }

        # 1. Generate or use custom queries
        queries = custom_queries or generate_discovery_queries(profile, max_queries=self.max_queries)
        queries = queries[:self.max_queries]

        preferred_countries = [c.lower() for c in profile.get("preferred_countries", [])] if isinstance(profile.get("preferred_countries"), list) else []
        excluded_countries = [c.lower() for c in profile.get("excluded_countries", [])] if isinstance(profile.get("excluded_countries"), list) else []

        discovered_institutions: List[Dict[str, Any]] = []
        seen_domains: Set[str] = set()
        
        executed_queries_meta: List[Dict[str, Any]] = []
        skipped_institutions: List[Dict[str, Any]] = []
        external_leads: List[Dict[str, Any]] = []

        total_results_found = 0
        quota_reached = False

        # 2. Execute Queries
        for q_item in queries:
            query_str = q_item["query"]
            query_country = q_item.get("country")
            
            resp = await self.execute_cached_search(query_str, country=query_country)
            executed_queries_meta.append({
                "query": query_str,
                "intent": q_item.get("intent", "general"),
                "category": q_item.get("category", "Search"),
                "results_count": len(resp.results),
                "is_cached": resp.is_cached,
                "error": resp.error_message
            })

            if resp.error_message:
                logger.warning(f"[Discovery] Query failed: '{query_str}' - {resp.error_message}")
                continue

            total_results_found += len(resp.results)

            # 3. Process each search result lead
            for result in resp.results:
                lead_url = normalize_url(result.url)
                if not lead_url:
                    continue

                parsed = urlparse(lead_url)
                host = parsed.netloc.lower().replace("www.", "")
                root_domain = get_root_institutional_domain(host)

                # Check if it is a commercial aggregator (e.g. findaphd.com)
                if any(agg in host for agg in COMMERCIAL_AGGREGATORS):
                    skipped_institutions.append({
                        "domain": host,
                        "url": lead_url,
                        "title": result.title,
                        "reason": "Commercial aggregator - treated as lead only, not official university source",
                        "discovered_via_query": query_str
                    })
                    external_leads.append({
                        "domain": host,
                        "url": lead_url,
                        "lead_title": result.title,
                        "lead_type": "aggregator_lead",
                        "context_snippet": result.snippet,
                        "source_query": query_str
                    })
                    continue

                # Check recognized external scholarship agencies (e.g. daad.de, fulbrightonline.org)
                domain_type, provider_name = classify_domain_type(lead_url, base_domain=root_domain)
                if domain_type == "external_scholarship_provider":
                    external_leads.append({
                        "domain": host,
                        "url": lead_url,
                        "lead_title": result.title,
                        "lead_type": "national_scholarship_agency",
                        "context_snippet": result.snippet,
                        "source_query": query_str
                    })
                    # We also allow the crawler to inspect official agency portals
                    if root_domain not in seen_domains:
                        seen_domains.add(root_domain)
                        discovered_institutions.append({
                            "institution_name": provider_name,
                            "root_domain": root_domain,
                            "lead_url": lead_url,
                            "country": guess_country_from_domain(root_domain),
                            "institution_type": "national_funding_agency",
                            "discovered_via_query": query_str,
                            "query_intent": q_item.get("intent", "general"),
                            "snippet": result.snippet
                        })
                    continue

                # Check if academic domain
                if not is_academic_domain(root_domain):
                    # Could be a research organization or institute
                    if not any(sub in host for sub in [".gov", ".org", "research", "lab", "institute", "hospital", "center"]):
                        skipped_institutions.append({
                            "domain": host,
                            "url": lead_url,
                            "title": result.title,
                            "reason": "Non-academic domain",
                            "discovered_via_query": query_str
                        })
                        continue

                # Check Country Preferences & Exclusions
                guessed_country = guess_country_from_domain(root_domain)
                if excluded_countries and guessed_country.lower() in excluded_countries:
                    skipped_institutions.append({
                        "domain": root_domain,
                        "url": lead_url,
                        "title": result.title,
                        "reason": f"Excluded country filter ({guessed_country})",
                        "discovered_via_query": query_str
                    })
                    continue

                # Deduplicate by root domain
                if root_domain in seen_domains:
                    continue

                # Check University Limits Cap
                if len(discovered_institutions) >= self.max_universities:
                    quota_reached = True
                    skipped_institutions.append({
                        "domain": root_domain,
                        "url": lead_url,
                        "title": result.title,
                        "reason": f"Max university limit reached ({self.max_universities})",
                        "discovered_via_query": query_str
                    })
                    continue

                seen_domains.add(root_domain)
                clean_name = clean_institution_name(result.title, root_domain)

                discovered_institutions.append({
                    "institution_name": clean_name,
                    "root_domain": root_domain,
                    "lead_url": lead_url,
                    "country": guessed_country,
                    "institution_type": "academic_institution",
                    "discovered_via_query": query_str,
                    "query_intent": q_item.get("intent", "general"),
                    "snippet": result.snippet
                })

        # 4. Assemble Coverage Report
        coverage_report = {
            "disclaimer": (
                "ScholarScout performs targeted discovery across configured search providers "
                "and official academic portals. It does not claim exhaustive indexing of every university worldwide."
            ),
            "summary": {
                "queries_planned": len(queries),
                "queries_executed": len(executed_queries_meta),
                "total_results_found": total_results_found,
                "discovered_institutions_count": len(discovered_institutions),
                "skipped_count": len(skipped_institutions),
                "external_leads_count": len(external_leads),
                "quota_cap_reached": quota_reached
            },
            "queries": executed_queries_meta,
            "discovered_institutions": discovered_institutions,
            "skipped_institutions": skipped_institutions,
            "external_leads": external_leads,
            "quota_caps": {
                "max_queries": self.max_queries,
                "max_results_per_query": self.max_results_per_query,
                "max_universities": self.max_universities
            }
        }

        return {
            "success": True,
            "discovered_institutions": discovered_institutions,
            "external_leads": external_leads,
            "coverage_report": coverage_report,
            "quota_reached": quota_reached
        }

    def _empty_coverage_report(self, reason: str) -> Dict[str, Any]:
        return {
            "disclaimer": "ScholarScout performs targeted discovery. It does not claim exhaustive indexing of every university worldwide.",
            "summary": {
                "queries_planned": 0,
                "queries_executed": 0,
                "total_results_found": 0,
                "discovered_institutions_count": 0,
                "skipped_count": 0,
                "external_leads_count": 0,
                "quota_cap_reached": False,
                "status_note": reason
            },
            "queries": [],
            "discovered_institutions": [],
            "skipped_institutions": [],
            "external_leads": []
        }
