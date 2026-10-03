import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.database import (
    enqueue_research_job,
    insert_scholarships,
    insert_professors,
    get_db_connection
)

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def sample_data():
    """Seeds test research run with scholarships and faculty for dashboard testing."""
    job_id = enqueue_research_job(
        university_url="https://cs.cmu.edu",
        university_name="Carnegie Mellon University",
        scope="all"
    )
    insert_scholarships(job_id, [
        {
            "title": "Graduate Fellowship in AI",
            "university": "Carnegie Mellon University",
            "country": "United States",
            "program": "Computer Science PhD",
            "degree_level": "Ph.D.",
            "funding_category": "Explicit full tuition plus living support",
            "amount": "Full Tuition + $38,000/yr",
            "deadline": "December 15, 2025",
            "deadline_date": "2025-12-15",
            "eligibility_status": "Appears eligible",
            "source_url": "https://cs.cmu.edu/fellowships",
            "fit_score": 95,
            "fit_reason": "Matches AI interest and full funding needs"
        }
    ])
    insert_professors(job_id, [
        {
            "name": "Dr. Sarah Chen",
            "title": "Associate Professor",
            "department": "Computer Science Department",
            "university": "Carnegie Mellon University",
            "email": "schen@cs.cmu.edu",
            "research_interests": "Multi-Agent Systems, Neural Reasoning",
            "recruitment_status": "Actively recruiting",
            "match_score": 92,
            "source_url": "https://cs.cmu.edu/~schen"
        }
    ])
    return job_id

def test_overview_endpoint(client, sample_data):
    res = client.get("/api/overview")
    assert res.status_code == 200
    data = res.json()
    assert "stats" in data
    assert "total_universities_tracked" in data
    assert "shortlist_counts" in data
    assert "recent_jobs" in data
    assert "top_scholarships" in data
    assert "top_professors" in data
    assert data["stats"]["jobs_count"] >= 1

def test_universities_endpoint_and_shortlisting(client, sample_data):
    # List universities
    res = client.get("/api/universities")
    assert res.status_code == 200
    univs = res.json()
    assert len(univs) >= 1
    cmu = next((u for u in univs if "cmu" in u["domain"] or "Carnegie" in u["university_name"]), None)
    assert cmu is not None

    domain = cmu["domain"]
    
    # Toggle shortlist
    res_short = client.post(f"/api/universities/{domain}/shortlist", json={"is_shortlisted": True})
    assert res_short.status_code == 200
    assert res_short.json()["is_shortlisted"] is True

    # Save notes
    res_notes = client.post(f"/api/universities/{domain}/notes", json={"notes": "Top choice for Fall 2026 application"})
    assert res_notes.status_code == 200
    assert res_notes.json()["notes"] == "Top choice for Fall 2026 application"

    # Verify shortlist listing
    res_shortlist = client.get("/api/shortlist")
    assert res_shortlist.status_code == 200
    sl_data = res_shortlist.json()
    assert any(u["domain"] == domain for u in sl_data["universities"])

def test_scholarship_shortlist_and_notes(client, sample_data):
    # Fetch scholarships
    res = client.get("/api/scholarships")
    assert res.status_code == 200
    schol_list = res.json()
    assert len(schol_list) >= 1
    s_id = schol_list[0]["id"]

    # Shortlist scholarship
    res_sl = client.post(f"/api/scholarships/{s_id}/shortlist", json={"is_shortlisted": True})
    assert res_sl.status_code == 200
    assert res_sl.json()["is_shortlisted"] is True

    # Save notes
    res_n = client.post(f"/api/scholarships/{s_id}/notes", json={"notes": "Need to prepare research proposal for this"})
    assert res_n.status_code == 200

    # Verify filtered listing
    res_filter = client.get("/api/scholarships?is_shortlisted=true")
    assert res_filter.status_code == 200
    assert any(s["id"] == s_id for s in res_filter.json())

def test_professor_shortlist_and_notes(client, sample_data):
    # Fetch professors
    res = client.get("/api/professors")
    assert res.status_code == 200
    profs = res.json()
    assert len(profs) >= 1
    p_id = profs[0]["id"]

    # Shortlist professor
    res_sl = client.post(f"/api/professors/{p_id}/shortlist", json={"is_shortlisted": True})
    assert res_sl.status_code == 200
    assert res_sl.json()["is_shortlisted"] is True

    # Save notes
    res_n = client.post(f"/api/professors/{p_id}/notes", json={"notes": "Contact in early October with updated CV"})
    assert res_n.status_code == 200

    # Verify shortlist endpoint
    res_shortlist = client.get("/api/shortlist")
    assert res_shortlist.status_code == 200
    assert any(p["id"] == p_id for p in res_shortlist.json()["professors"])
