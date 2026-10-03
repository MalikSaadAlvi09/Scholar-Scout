"""
Tests for Global Countries and Universities Directory.
Validates 195+ sovereign countries catalog, normalization,
academic domain mapping, and directory API endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.discovery.global_directory import (
    ALL_COUNTRIES_DATA,
    GLOBAL_UNIVERSITIES_CATALOG,
    COUNTRY_NORMALIZATION_MAP,
    COUNTRY_TLD_MAP,
    normalize_country_name,
    get_all_global_countries,
    get_global_universities_by_country,
)

client = TestClient(app)

def test_global_countries_coverage():
    """Verify full global coverage with at least 195 sovereign countries and territories."""
    assert len(ALL_COUNTRIES_DATA) >= 195
    country_names = {c["name"] for c in ALL_COUNTRIES_DATA}
    assert "United States" in country_names
    assert "United Kingdom" in country_names
    assert "Germany" in country_names
    assert "Canada" in country_names
    assert "Australia" in country_names
    assert "Japan" in country_names
    assert "Singapore" in country_names
    assert "Saudi Arabia" in country_names
    assert "Brazil" in country_names
    assert "South Africa" in country_names

def test_country_normalization():
    """Verify alias normalization to canonical standard names."""
    assert normalize_country_name("usa") == "United States"
    assert normalize_country_name("US") == "United States"
    assert normalize_country_name("u.s.a.") == "United States"
    assert normalize_country_name("UK") == "United Kingdom"
    assert normalize_country_name("great britain") == "United Kingdom"
    assert normalize_country_name("UAE") == "United Arab Emirates"
    assert normalize_country_name("South Korea") == "South Korea"
    assert normalize_country_name("viet nam") == "Vietnam"
    assert normalize_country_name("unknown") == "Unknown"
    assert normalize_country_name(None) == "Unknown"

def test_academic_tld_map():
    """Verify academic search filters are defined for key regions."""
    assert COUNTRY_TLD_MAP["united states"] == "site:.edu"
    assert COUNTRY_TLD_MAP["united kingdom"] == "site:.ac.uk"
    assert COUNTRY_TLD_MAP["canada"] == "site:.ca"
    assert COUNTRY_TLD_MAP["germany"] == "site:.de"
    assert COUNTRY_TLD_MAP["australia"] == "site:.edu.au"

def test_global_universities_catalog():
    """Verify premier research universities catalog across multiple continents."""
    assert len(GLOBAL_UNIVERSITIES_CATALOG) >= 150
    countries_with_unis = {u["country"] for u in GLOBAL_UNIVERSITIES_CATALOG}
    assert "United States" in countries_with_unis
    assert "United Kingdom" in countries_with_unis
    assert "Canada" in countries_with_unis
    assert "Germany" in countries_with_unis
    assert "Switzerland" in countries_with_unis
    assert "Japan" in countries_with_unis
    assert "Australia" in countries_with_unis
    assert "India" in countries_with_unis
    assert "Saudi Arabia" in countries_with_unis
    assert "South Africa" in countries_with_unis

def test_api_directory_countries():
    """Verify GET /api/directory/countries endpoint returns structured list with flags and counts."""
    response = client.get("/api/directory/countries")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 195
    assert any(c["name"] == "United States" and c["flag"] == "🇺🇸" for c in data)
    assert any(c["name"] == "Germany" and c["flag"] == "🇩🇪" for c in data)

def test_api_directory_universities():
    """Verify GET /api/directory/universities endpoint with filtering."""
    response = client.get("/api/directory/universities?country=Germany")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert all(u["country"] == "Germany" for u in data)

    # Search filter test
    search_res = client.get("/api/directory/universities?search=Oxford")
    assert search_res.status_code == 200
    search_data = search_res.json()
    assert len(search_data) >= 1
    assert "Oxford" in search_data[0]["name"]

def test_api_universities_random_sample_and_country_filtering():
    """Verify GET /api/universities supports random sampling across all countries and specific country filtering."""
    # 1. Test Country Filter: Germany
    res_de = client.get("/api/universities?country=Germany")
    assert res_de.status_code == 200
    data_de = res_de.json()
    assert len(data_de) >= 5
    assert all(u["country"] == "Germany" for u in data_de)

    # 2. Test Country Filter: United Kingdom
    res_uk = client.get("/api/universities?country=United%20Kingdom")
    assert res_uk.status_code == 200
    data_uk = res_uk.json()
    assert len(data_uk) >= 5
    assert all(u["country"] == "United Kingdom" for u in data_uk)

    # 3. Test Random Sample across All Countries
    res_rand = client.get("/api/universities?randomize=true")
    assert res_rand.status_code == 200
    data_rand = res_rand.json()
    assert len(data_rand) >= 10
    # Random sampling across all countries produces universities from multiple different countries
    countries_sample = {u["country"] for u in data_rand}
    assert len(countries_sample) >= 3

def test_api_universities_management_crud():
    """Verify POST, PUT, DELETE, and 1-click launch research on universities directory."""
    test_domain = "tum-test-uni.de"
    
    # 1. Create custom university
    create_payload = {
        "university_name": "Technical University of Munich Test",
        "lead_url": "https://www.tum-test.de",
        "domain": test_domain,
        "country": "Germany",
        "notes": "Renowned for AI and robotics. Application deadline Jan 15.",
        "is_shortlisted": True
    }
    create_res = client.post("/api/universities", json=create_payload)
    assert create_res.status_code == 200
    create_data = create_res.json()
    assert create_data["success"] is True

    # 2. Verify it appears in GET /api/universities?search=tum-test-uni.de
    fetch_res = client.get(f"/api/universities?search={test_domain}")
    assert fetch_res.status_code == 200
    matches = fetch_res.json()
    assert len(matches) >= 1
    target_uni = next((u for u in matches if u["domain"] == test_domain), None)
    assert target_uni is not None
    assert target_uni["university_name"] == "Technical University of Munich Test"
    assert target_uni["is_shortlisted"] == 1 or target_uni["is_shortlisted"] is True

    # 3. Update university
    update_payload = {
        "university_name": "TUM Munich Advanced Institute",
        "country": "Germany",
        "notes": "Updated note: Offers full DAAD scholarship support.",
        "is_shortlisted": False
    }
    update_res = client.put(f"/api/universities/{test_domain}", json=update_payload)
    assert update_res.status_code == 200

    # 4. Launch 1-click research crawl
    launch_res = client.post(f"/api/universities/{test_domain}/launch-research")
    assert launch_res.status_code == 200
    launch_data = launch_res.json()
    assert launch_data["success"] is True
    assert "job_id" in launch_data

    # 5. Delete / untrack university
    del_res = client.delete(f"/api/universities/{test_domain}")
    assert del_res.status_code == 200
    del_data = del_res.json()
    assert del_data["success"] is True

