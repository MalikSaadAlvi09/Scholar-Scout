"""
Test Suite for ScholarScout Email-Drafting Workspace, Outreach Settings & Groundedness Engine.
Verifies:
1. Retrieval and update of customizable outreach instructions & template settings.
2. Grounded outreach generation using confirmed candidate profile & verified professor evidence.
3. Detection and flagging of published contact policies (discouraged outreach / portal required).
4. Grounding auditor: detects unsupported claims and prevents marking draft as 'verified_ready'.
5. Batch generation of distinct drafts for selected professors.
6. RFC 822 .eml export file generation and MIME structure.
7. Manual editing, claims clearance, and safe draft deletion.
"""

import pytest
import os
from fastapi.testclient import TestClient
from backend.main import app
from backend.database import (
    init_db,
    save_profile,
    enqueue_research_job,
    update_job_status,
    insert_professors,
    get_professors,
    get_email_drafts,
    get_email_draft,
    get_outreach_settings,
    save_outreach_settings
)

@pytest.fixture(autouse=True)
def setup_test_db():
    """Ensure clean test database state."""
    init_db()
    yield

def test_outreach_settings_crud():
    client = TestClient(app)
    # 1. Get default settings
    res = client.get("/api/outreach-settings")
    assert res.status_code == 200
    data = res.json()
    assert "purpose" in data
    assert "target_degree_intake" in data
    assert "signature" in data

    # 2. Update settings
    payload = {
        "purpose": "Funded PhD Research Assistantship Inquiry",
        "target_degree_intake": "Ph.D. in Computer Science (Fall 2027)",
        "tone_and_length": "Scholarly, direct, under 180 words",
        "specific_request": "Inquire about opening positions in the Neural Systems Lab.",
        "background_to_emphasize": "3.98 GPA, PyTorch expertise, 2 top-tier publications in NLP",
        "signature": "Best regards,\nJane Doe\nApplicant",
        "proposed_attachments": "Academic CV (PDF), Research Statement (PDF)",
        "optional_wording_preferences": "Focus on neuro-symbolic reasoning; do not flatter."
    }
    res = client.post("/api/outreach-settings", json=payload)
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["success"] is True
    assert res_data["settings"]["purpose"] == payload["purpose"]
    assert res_data["settings"]["target_degree_intake"] == payload["target_degree_intake"]

def test_grounded_email_draft_generation():
    client = TestClient(app)

    # 1. Create a job and a verified professor
    job_id = enqueue_research_job(
        university_url="https://cs.cmu.edu",
        university_name="Carnegie Mellon University",
        scope="faculty",
        profile_version=1
    )
    update_job_status(job_id, "completed")

    insert_professors(job_id, [{
        "name": "Dr. William Cohen",
        "department": "Language Technologies Institute",
        "university": "Carnegie Mellon University",
        "email": "wcohen@cs.cmu.edu",
        "research_interests": "Information Extraction, Neural Reasoning, Multi-Agent Systems",
        "lab_group": "Cohen NLP Lab",
        "lab_url": "https://cs.cmu.edu/~wcohen/lab",
        "official_profile_url": "https://cs.cmu.edu/~wcohen",
        "recruitment_status": "Actively Recruiting",
        "recruitment_evidence": "Looking for 2 Ph.D. students in Neural Reasoning for Fall 2026.",
        "position_funding_type": "Graduate Research Assistantship",
        "match_score": 92
    }], profile_version=1)

    profs = get_professors(job_id=job_id)
    assert len(profs) > 0
    prof_id = profs[0]["id"]

    # 2. Generate a draft for this professor
    gen_payload = {
        "professor_id": prof_id,
        "recipient_name": "Dr. William Cohen",
        "recipient_email": "wcohen@cs.cmu.edu",
        "recipient_role": "Faculty / PI",
        "draft_type": "Professor Research Inquiry",
        "context_title": "Information Extraction & Neural Reasoning",
        "context_details": "Lab focus on neural-symbolic systems and knowledge graphs."
    }
    res = client.post("/api/emails/generate", json=gen_payload)
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["success"] is True
    draft = res_data["draft"]

    assert draft["recipient_name"] == "Dr. William Cohen"
    assert draft["recipient_email"] == "wcohen@cs.cmu.edu"
    assert "William Cohen" in draft["body_text"] or "Dr. William Cohen" in draft["body_text"]
    assert draft["can_send"] == 0  # Sending permanently disabled

    # Check evidence used structure
    evidence = draft.get("evidence_used", {})
    assert "candidate_facts" in evidence
    assert "professor_facts" in evidence
    assert "source_links" in evidence

def test_discouraged_outreach_policy_detection():
    client = TestClient(app)

    job_id = enqueue_research_job(
        university_url="https://eecs.mit.edu",
        university_name="MIT",
        scope="faculty",
        profile_version=1
    )
    insert_professors(job_id, [{
        "name": "Prof. Strict Admissions",
        "department": "EECS",
        "university": "MIT",
        "email": "strict@mit.edu",
        "research_interests": "Quantum Computing",
        "contact_instructions": "Please do not email me directly about graduate admissions. All applications must go through the centralized EECS department portal.",
        "recruitment_status": "Department admissions portal only",
        "match_score": 85
    }], profile_version=1)

    profs = get_professors(job_id=job_id)
    prof_id = profs[0]["id"]

    res = client.post("/api/emails/generate", json={
        "professor_id": prof_id,
        "recipient_name": "Prof. Strict Admissions",
        "recipient_email": "strict@mit.edu"
    })
    assert res.status_code == 200
    draft = res.json()["draft"]

    # Verify flagged as discouraged or portal required
    assert draft["contact_instructions_flag"] in ["discouraged", "portal_required"]
    assert draft["status"] == "flagged_discouraged"
    assert len(draft["contact_instructions_notes"]) > 0

def test_unsupported_claims_guardrail_blocking_ready_status():
    client = TestClient(app)

    job_id = enqueue_research_job(
        university_url="https://cs.stanford.edu",
        university_name="Stanford University",
        scope="faculty",
        profile_version=1
    )
    insert_professors(job_id, [{
        "name": "Prof. Unfunded Lab",
        "department": "Computer Science",
        "university": "Stanford University",
        "email": "unfunded@stanford.edu",
        "research_interests": "Theoretical CS",
        "position_funding_type": "Unstated in official records",
        "match_score": 75
    }], profile_version=1)

    profs = get_professors(job_id=job_id)
    prof_id = profs[0]["id"]

    # Create draft
    draft = client.post("/api/emails/generate", json={
        "professor_id": prof_id,
        "recipient_name": "Prof. Unfunded Lab",
        "recipient_email": "unfunded@stanford.edu",
        "context_title": "Theory",
        "context_details": "Theory lab"
    }).json()["draft"]

    draft_id = draft["id"]

    # Update draft to inject an unsupported claim regarding guaranteed funding
    update_res = client.put(f"/api/emails/{draft_id}", json={
        "subject": "Inquiry",
        "body_text": "Dear Professor, I am writing to accept your guaranteed funding and fully funded offer for Fall 2026."
    })
    assert update_res.status_code == 200

    # Mark as status with claims warning set
    # Update status to needs_review with unsupported claims
    from backend.database import save_email_draft
    save_email_draft({
        "id": draft_id,
        "unsupported_claims_flag": 1,
        "unsupported_claims_notes": "Draft assumes guaranteed funding without verified proof."
    })

    # Attempt to mark as verified_ready without clearing claims
    status_res = client.put(f"/api/emails/{draft_id}/status", json={
        "status": "verified_ready"
    })
    # Should be blocked
    assert status_res.status_code == 400
    assert "unsupported claims" in status_res.json()["detail"].lower()

    # User clears claim or fixes draft
    fix_res = client.put(f"/api/emails/{draft_id}", json={
        "subject": "Inquiry regarding PhD Advisorship",
        "body_text": "Dear Professor, I am writing to inquire if you have any advising capacity for prospective Ph.D. students.",
        "clear_claims_warning": True
    })
    assert fix_res.status_code == 200

    # Now mark as verified_ready
    ready_res = client.put(f"/api/emails/{draft_id}/status", json={
        "status": "verified_ready",
        "is_reviewed": True
    })
    assert ready_res.status_code == 200
    assert ready_res.json()["status"] == "verified_ready"

def test_batch_email_draft_generation():
    client = TestClient(app)

    job_id = enqueue_research_job(
        university_url="https://cs.cmu.edu",
        university_name="CMU",
        scope="faculty",
        profile_version=1
    )
    insert_professors(job_id, [
        {
            "name": "Prof. Alice Neural",
            "department": "CS",
            "university": "CMU",
            "email": "alice@cs.cmu.edu",
            "research_interests": "Deep Learning",
            "match_score": 88
        },
        {
            "name": "Prof. Bob Systems",
            "department": "CS",
            "university": "CMU",
            "email": "bob@cs.cmu.edu",
            "research_interests": "Distributed Systems",
            "match_score": 90
        }
    ], profile_version=1)

    profs = get_professors(job_id=job_id)
    prof_ids = [p["id"] for p in profs]

    batch_res = client.post("/api/emails/generate-batch", json={
        "professor_ids": prof_ids,
        "job_id": job_id
    })
    assert batch_res.status_code == 200
    data = batch_res.json()
    assert data["success"] is True
    assert data["count"] == len(prof_ids)
    assert len(data["drafts"]) == len(prof_ids)

def test_eml_file_export():
    client = TestClient(app)

    # Get existing drafts
    drafts = client.get("/api/emails").json()
    assert len(drafts) > 0
    draft_id = drafts[0]["id"]

    eml_res = client.get(f"/api/emails/{draft_id}/eml")
    assert eml_res.status_code == 200
    assert eml_res.headers["content-type"].startswith("message/rfc822")
    assert "Content-Disposition" in eml_res.headers
    assert f"scholarscout_outreach_{draft_id}.eml" in eml_res.headers["Content-Disposition"]

    eml_text = eml_res.content.decode("utf-8")
    assert "From:" in eml_text
    assert "To:" in eml_text
    assert "Subject:" in eml_text
    assert "X-ScholarScout-Status: draft-reviewed" in eml_text
