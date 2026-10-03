"""
Automated Test Suite for ScholarScout Discovery Mode & Search Providers.
Tests pluggable search providers, query generator, search caching,
institutional deduplication, quota caps, pause/resume, and coverage reports.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from backend.discovery.search_providers.base import SearchResultItem, SearchResponse
from backend.discovery.search_providers.null_provider import NullSearchProvider
from backend.discovery.search_providers.tavily import TavilySearchProvider
from backend.discovery.search_providers.serpapi import SerpApiProvider
from backend.discovery.search_providers.brave import BraveSearchProvider
from backend.discovery.search_providers.factory import get_search_provider
from backend.discovery.query_generator import generate_discovery_queries, parse_list_field
from backend.discovery.engine import DiscoveryEngine, clean_institution_name, is_academic_domain, guess_country_from_domain
from backend.database import (
    init_db,
    get_cached_search,
    set_cached_search,
    enqueue_research_job,
    get_job,
    pause_job,
    resume_job,
    update_job_coverage,
    get_job_coverage,
    insert_scholarships,
    get_scholarships,
    insert_professors,
    get_professors
)

@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()

# --- 1. Search Providers Unit Tests ---

def test_null_search_provider():
    provider = NullSearchProvider()
    assert not provider.is_configured()
    assert provider.provider_name == "none"

    # Async search returns empty results with explanation
    res = asyncio.run(provider.search("test query"))
    assert len(res.results) == 0
    assert "No search provider configured" in res.error_message

def test_tavily_search_provider_mock():
    provider = TavilySearchProvider(api_key="tvly-mock-key-12345")
    assert provider.is_configured()
    assert provider.provider_name == "tavily"

    mock_resp_data = {
        "results": [
            {
                "title": "CMU Computer Science Graduate Admissions & Assistantships",
                "url": "https://cs.cmu.edu/academics/phd/funding",
                "content": "All admitted Ph.D. students receive full tuition and living stipend through Graduate Research Assistantships (GRA)."
            },
            {
                "title": "Oxford University Scholarships",
                "url": "https://ox.ac.uk/admissions/graduate/fees-and-funding/oxford-scholarships",
                "content": "Fully funded Clarendon and departmental awards for graduate research."
            }
        ]
    }

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_resp_data

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        res = asyncio.run(provider.search("Computer Science PhD fully funded", max_results=5))

        assert res.total_results_count == 2
        assert len(res.results) == 2
        assert res.results[0].source_domain == "cs.cmu.edu"
        assert "Graduate Research Assistantships" in res.results[0].snippet

def test_serpapi_search_provider_mock():
    provider = SerpApiProvider(api_key="serp-mock-key-12345")
    assert provider.is_configured()
    assert provider.provider_name == "serpapi"

    mock_resp_data = {
        "organic_results": [
            {
                "title": "MIT EECS Graduate Funding & Fellowships",
                "link": "https://eecs.mit.edu/academics/graduate-programs/admission-process/",
                "snippet": "Financial support is provided in the form of research assistantships, teaching assistantships, or fellowships."
            }
        ]
    }

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_resp_data

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        res = asyncio.run(provider.search("MIT EECS funding", max_results=3))

        assert res.total_results_count == 1
        assert res.results[0].url == "https://eecs.mit.edu/academics/graduate-programs/admission-process/"
        assert res.results[0].source_domain == "eecs.mit.edu"

def test_brave_search_provider_mock():
    provider = BraveSearchProvider(api_key="brave-mock-key-12345")
    assert provider.is_configured()
    assert provider.provider_name == "brave"

    mock_resp_data = {
        "web": {
            "results": [
                {
                    "title": "TUM Informatics Doctoral Positions",
                    "url": "https://www.cit.tum.de/en/cit/studies/degree-programs/phd-informatics/",
                    "description": "Doctoral candidates at TUM receive salaried employment as research assistants (TV-L E13)."
                }
            ]
        }
    }

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_resp_data

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        res = asyncio.run(provider.search("TUM Informatics PhD position", max_results=2))

        assert res.total_results_count == 1
        assert "TUM" in res.results[0].title

def test_search_provider_factory():
    # Test Null fallback
    with patch("backend.config.config.search_provider", ""), patch("os.getenv", return_value=""):
        p_null = get_search_provider()
        assert isinstance(p_null, NullSearchProvider)

    # Test explicit Tavily instantiation
    p_tavily = get_search_provider("tavily", api_key="tvly-test")
    assert isinstance(p_tavily, TavilySearchProvider)
    assert p_tavily.is_configured()

# --- 2. Query Generator Unit Tests ---

def test_generate_discovery_queries_full_profile():
    profile = {
        "target_degree": "Ph.D.",
        "broad_subject": "Computer Science",
        "specific_interests": "Large Language Models, Multi-Agent Systems",
        "preferred_countries": ["United States", "Germany", "United Kingdom"],
        "intended_intake": "Fall 2026",
        "funding_needs": ["full_tuition", "living_stipend"]
    }

    queries = generate_discovery_queries(profile, max_queries=6)
    assert len(queries) >= 3

    query_texts = [q["query"] for q in queries]
    full_text = " ".join(query_texts)

    # Must contain key academic terms
    assert "Computer Science" in full_text
    assert "Ph.D." in full_text
    assert any("assistantship" in q_t.lower() or "scholarship" in q_t.lower() or "funding" in q_t.lower() for q_t in query_texts)

def test_generate_discovery_queries_minimal_profile():
    profile = {
        "target_degree": "Master's",
        "broad_subject": "Robotics"
    }

    queries = generate_discovery_queries(profile, max_queries=4)
    assert len(queries) >= 1
    assert "Robotics" in queries[0]["query"]

# --- 3. Search Caching & Deduplication Tests ---

def test_search_cache_roundtrip():
    q_hash = "mock_hash_12345"
    q_text = "site:.edu 'Robotics' fully funded"
    results = [
        {"title": "CMU Robotics PhD", "url": "https://ri.cmu.edu", "snippet": "Fully funded GRA positions."}
    ]

    set_cached_search(
        query_hash=q_hash,
        query_text=q_text,
        provider="tavily",
        results=results,
        count=1
    )

    cached = get_cached_search(q_hash, max_age_days=7)
    assert cached is not None
    assert cached["query_text"] == q_text
    assert len(cached["results"]) == 1
    assert cached["results"][0]["url"] == "https://ri.cmu.edu"

# --- 4. Discovery Engine & Institutional Deduplication ---

def test_discovery_engine_lead_deduplication_and_filtering():
    # Mock search provider returning multiple leads with duplicates, subdomains, and aggregators
    mock_provider = MagicMock(spec=TavilySearchProvider)
    mock_provider.is_configured.return_value = True
    mock_provider.provider_name = "mock_provider"
    mock_provider.display_name = "Mock Provider"

    mock_results = [
        SearchResultItem(
            title="CMU Computer Science Department | Graduate Aid",
            url="https://cs.cmu.edu/graduate/funding",
            snippet="Full tuition and stipend."
        ),
        SearchResultItem(
            title="Carnegie Mellon University Robotics Institute",
            url="https://ri.cmu.edu/academics/phd",
            snippet="GRA openings in robotics."
        ),
        SearchResultItem(
            title="FindAPhD Computer Science Listings",
            url="https://www.findaphd.com/phd-programmes/cs-degrees",
            snippet="Find scholarships worldwide."
        ),
        SearchResultItem(
            title="Oxford University CS Department",
            url="https://www.cs.ox.ac.uk/admissions/graduate",
            snippet="Clarendon scholarships."
        )
    ]

    mock_provider.search = AsyncMock(return_value=SearchResponse(
        query="test query",
        results=mock_results,
        total_results_count=4,
        provider_name="mock_provider"
    ))

    engine = DiscoveryEngine(
        search_provider=mock_provider,
        max_queries=2,
        max_universities=5
    )

    profile = {
        "target_degree": "Ph.D.",
        "broad_subject": "Computer Science",
        "preferred_countries": ["United States", "United Kingdom"]
    }

    res = asyncio.run(engine.discover_institutions(profile))
    assert res["success"] is True

    discovered = res["discovered_institutions"]
    discovered_domains = [d["root_domain"] for d in discovered]

    # CMU should only appear ONCE despite cs.cmu.edu and ri.cmu.edu
    assert discovered_domains.count("cmu.edu") == 1
    assert "ox.ac.uk" in discovered_domains

    # findaphd.com should NOT be in discovered institutions (it is a commercial aggregator)
    assert "findaphd.com" not in discovered_domains

    # Coverage report must have disclaimer
    coverage = res["coverage_report"]
    assert "ScholarScout performs targeted discovery" in coverage["disclaimer"]
    assert coverage["summary"]["discovered_institutions_count"] == len(discovered)

# --- 5. Pause & Resume Mechanics ---

def test_pause_and_resume_jobs():
    job_id = enqueue_research_job(
        university_url="https://cs.stanford.edu",
        university_name="Stanford University",
        job_type="url_research"
    )

    job_before = get_job(job_id)
    assert job_before["status"] == "queued"
    assert job_before["is_paused"] == 0

    # Pause
    paused = pause_job(job_id, reason="Monthly search credit quota threshold reached")
    assert paused is True

    job_paused = get_job(job_id)
    assert job_paused["status"] == "paused"
    assert job_paused["is_paused"] == 1
    assert "quota threshold" in job_paused["pause_reason"]

    # Resume
    resumed = resume_job(job_id)
    assert resumed is True

    job_resumed = get_job(job_id)
    assert job_resumed["status"] == "queued"
    assert job_resumed["is_paused"] == 0

# --- 6. Provenance Preservation ---

def test_provenance_preservation_scholarships_and_professors():
    job_id = enqueue_research_job(
        university_url="https://cs.cmu.edu",
        job_type="discovery_job"
    )

    query_provenance = "site:.edu 'Computer Science' PhD 'GRA' 2026"

    # Insert scholarship with query provenance
    scholarship_data = [{
        "title": "Graduate Research Assistantship (GRA)",
        "university": "Carnegie Mellon University",
        "funding_category": "Explicit full tuition plus living support",
        "tuition_coverage": "100%",
        "stipend_amount": "$38,000 / year",
        "source_url": "https://cs.cmu.edu/funding",
        "discovered_via_query": query_provenance
    }]
    insert_scholarships(job_id, scholarship_data)

    saved_s = get_scholarships(job_id=job_id)
    assert len(saved_s) == 1
    assert saved_s[0]["discovered_via_query"] == query_provenance

    # Insert professor with query provenance
    prof_data = [{
        "name": "Dr. Geoffrey Hinton",
        "title": "Professor",
        "department": "Computer Science",
        "university": "Carnegie Mellon University",
        "email": "hinton@cmu.edu",
        "email_source_url": "https://cs.cmu.edu/faculty/hinton",
        "email_date_observed": "2026-09-29",
        "recruitment_status": "Actively seeking PhD students",
        "source_url": "https://cs.cmu.edu/faculty/hinton",
        "discovered_via_query": query_provenance
    }]
    insert_professors(job_id, prof_data)

    saved_p = get_professors(job_id=job_id)
    assert len(saved_p) == 1
    assert saved_p[0]["discovered_via_query"] == query_provenance

# --- 7. Discovery API Endpoints Tests ---

def test_discovery_api_endpoints():
    from fastapi.testclient import TestClient
    from backend.main import app

    client = TestClient(app)

    # 1. Search instructions
    res_inst = client.get("/api/settings/search-instructions")
    assert res_inst.status_code == 200
    data_inst = res_inst.json()
    assert "supported_providers" in data_inst
    assert len(data_inst["supported_providers"]) == 3
    assert any(p["id"] == "tavily" for p in data_inst["supported_providers"])

    # 2. Test search connection endpoint
    res_test = client.post("/api/settings/test-search")
    assert res_test.status_code == 200
    assert "provider_name" in res_test.json()

    # 3. Generate queries endpoint
    res_queries = client.post("/api/discovery/generate-queries", json={
        "custom_keywords": "Robotics Institute",
        "max_queries": 4
    })
    assert res_queries.status_code == 200
    data_queries = res_queries.json()
    assert data_queries["success"] is True
    assert len(data_queries["queries"]) >= 1

    # 4. Preview discovery leads endpoint
    with patch("backend.api.routes.get_search_provider") as mock_prov_fn, \
         patch("backend.discovery.engine.DiscoveryEngine.discover_institutions", new_callable=AsyncMock) as mock_disc:
        mock_p = MagicMock()
        mock_p.is_configured.return_value = True
        mock_prov_fn.return_value = mock_p

        mock_disc.return_value = {
            "success": True,
            "discovered_institutions": [
                {
                    "institution_name": "Carnegie Mellon University",
                    "root_domain": "cmu.edu",
                    "lead_url": "https://cs.cmu.edu",
                    "country": "United States",
                    "discovered_via_query": "test query"
                }
            ],
            "coverage_report": {
                "disclaimer": "ScholarScout performs targeted discovery.",
                "summary": {"total_results_found": 1}
            }
        }
        res_prev = client.post("/api/discovery/preview", json={
            "queries": [{"query": "CS PhD fully funded", "category": "funding", "intent": "funding"}],
            "max_queries": 1
        })
        assert res_prev.status_code == 200
        assert len(res_prev.json()["discovered_institutions"]) == 1

    # 5. Start discovery job endpoint
    with patch("backend.api.routes.get_search_provider") as mock_prov_fn:
        mock_p = MagicMock()
        mock_p.is_configured.return_value = True
        mock_p.provider_name = "tavily"
        mock_p.display_name = "Tavily Search API"
        mock_prov_fn.return_value = mock_p
        
        res_start = client.post("/api/discovery/start", json={
            "max_queries": 3,
            "max_universities": 3
        })
        assert res_start.status_code == 200
        job_id = res_start.json()["job_id"]
        assert job_id is not None

        # 6. Pause & resume via API
        res_pause = client.post(f"/api/jobs/{job_id}/pause")
        assert res_pause.status_code == 200
        assert res_pause.json()["success"] is True

        res_resume = client.post(f"/api/jobs/{job_id}/resume")
        assert res_resume.status_code == 200
        assert res_resume.json()["success"] is True

        # 7. Coverage report endpoint
        res_cov = client.get(f"/api/jobs/{job_id}/coverage")
        assert res_cov.status_code == 200
        assert "disclaimer" in res_cov.json()

