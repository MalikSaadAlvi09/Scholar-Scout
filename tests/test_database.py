"""
Database and Safety Verification Tests for ScholarScout.
Verifies schema, persistent job queue transitions, and email safety flags.
"""

import pytest
import os
from backend.database import (
    init_db,
    save_profile,
    get_active_profile,
    enqueue_research_job,
    get_job,
    update_job_status,
    insert_scholarships,
    get_scholarships,
    insert_professors,
    get_professors,
    save_email_draft,
    get_email_drafts
)

def test_database_initialization():
    """Ensure database schema initializes properly."""
    init_db()
    profile = get_active_profile()
    assert profile is not None
    assert "name" in profile

def test_profile_crud():
    """Test saving and retrieving an academic profile."""
    test_data = {
        "name": "Jane Doe",
        "target_degree": "Ph.D.",
        "current_major": "Artificial Intelligence",
        "target_field": "Computer Science",
        "research_interests": "Reinforcement Learning, Robotics",
        "gpa": "3.95 / 4.0",
        "country_of_origin": "International",
        "background_summary": "Published in NeurIPS workshop",
        "is_active": 1
    }
    pid = save_profile(test_data)
    assert pid > 0
    active = get_active_profile()
    assert active["name"] == "Jane Doe"
    assert active["target_degree"] == "Ph.D."

def test_research_job_queue():
    """Test persistent research job queue transitions."""
    job_id = enqueue_research_job("https://cs.cmu.edu", university_name="Carnegie Mellon University")
    assert job_id > 0
    
    job = get_job(job_id)
    assert job["status"] == "queued"
    assert job["university_url"] == "https://cs.cmu.edu"

    # Update status to running
    update_job_status(job_id, status="running", current_step="Crawling pages", progress_pct=30)
    job_updated = get_job(job_id)
    assert job_updated["status"] == "running"
    assert job_updated["progress_pct"] == 30

def test_scholarship_and_evidence_extraction_storage():
    """Test structured scholarship insert and evidence snippet preservation."""
    job_id = enqueue_research_job("https://cs.stanford.edu")
    sample_scholarships = [
        {
            "title": "Stanford Graduate Fellowship",
            "funding_type": "Fellowship",
            "amount": "$45,000 / year + Tuition",
            "currency": "USD",
            "eligibility": "All incoming PhD students",
            "deadline": "December 15",
            "department": "Computer Science",
            "evidence_snippet": "All doctoral students receive guaranteed 5-year fellowship covering full tuition and 12-month stipend.",
            "source_url": "https://cs.stanford.edu/phd-funding",
            "fit_score": 95,
            "fit_reason": "Direct match for Ph.D. target degree."
        }
    ]
    inserted = insert_scholarships(job_id, sample_scholarships)
    assert inserted == 1

    fetched = get_scholarships(job_id=job_id)
    assert len(fetched) >= 1
    assert fetched[0]["title"] == "Stanford Graduate Fellowship"
    assert "guaranteed 5-year fellowship" in fetched[0]["evidence_snippet"]

def test_email_draft_safety_lock():
    """Verify that email drafts are created with sending disabled by default."""
    draft_id = save_email_draft({
        "recipient_name": "Prof. Alan Turing",
        "recipient_email": "aturing@cam.ac.uk",
        "recipient_role": "Faculty / PI",
        "draft_type": "Professor Research Inquiry",
        "subject": "Prospective Ph.D. Inquiry",
        "body_text": "Dear Prof. Turing..."
    })
    assert draft_id > 0

    drafts = get_email_drafts()
    target = next((d for d in drafts if d["id"] == draft_id), None)
    assert target is not None
    # Crucial security test: can_send MUST be 0 (False)
    assert target["can_send"] == 0
    assert "disabled" in target["safety_notice"].lower()
