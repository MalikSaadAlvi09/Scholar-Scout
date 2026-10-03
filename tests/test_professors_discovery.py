"""
Automated Test Suite for ScholarScout Professor & Lab Discovery.
Tests faculty extraction, strict public email verification, lab affiliations,
recruitment status, funding separation, explainable 4-part rubric, deduplication,
and REST API endpoints.
"""

import pytest
import os
import json
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from backend.main import app
from backend.database import init_db, insert_professors, get_professors, enqueue_research_job
from backend.professors.matcher import (
    heuristic_professor_extractor,
    compute_explainable_rubric,
    deduplicate_and_merge_professors,
    extract_contact_instructions_and_recruitment,
    extract_funding_separation,
    match_professors
)
from backend.llm.schemas import ProfessorItem, ProfessorListResponse


@pytest.fixture(autouse=True)
def setup_test_db():
    """Ensure clean test database state."""
    init_db()


@pytest.fixture
def sample_profile():
    return {
        "name": "Alex Rivera",
        "target_degree": "Ph.D.",
        "broad_subject": "Computer Science",
        "target_field": "Artificial Intelligence",
        "specific_interests": "Large Language Models, Multi-Agent Systems, Neural Reasoning",
        "research_interests": "Large Language Models, Multi-Agent Systems, Neural Reasoning",
        "technical_skills": "Python, PyTorch, CUDA, Transformers, FastMCP",
        "projects": "ScholarScout Autonomous Research Agent, LLM Benchmark Suite",
        "publications": "Workshop paper on LLM Agent Evaluation",
        "research_experience": "Undergraduate Research Assistant in NLP Lab (2 years)",
        "portfolio_url": "https://alexrivera.dev",
        "version": 1
    }


def test_strict_public_email_rules(sample_profile):
    """
    STRICT CONTACT RULE:
    Only collect public professional contact details.
    Never guess an email address from naming conventions.
    If absent, display 'Not found'.
    """
    page_text = """
    Department of Computer Science
    Prof. Michael Jordan is a Professor in the Department of EECS.
    His research focuses on statistical machine learning and optimization.
    Office: 421 Soda Hall.
    """
    # No emails found on page
    results = heuristic_professor_extractor(
        page_url="https://eecs.berkeley.edu/faculty/jordan",
        text_content=page_text,
        emails_found=[],
        profile=sample_profile,
        university_name="UC Berkeley"
    )

    assert len(results) > 0
    prof = results[0]
    assert prof["name"] == "Michael Jordan"
    # MUST BE 'Not found', NEVER guessed like 'michael.jordan@berkeley.edu'
    assert prof["email"] == "Not found"
    assert prof["email_source_url"] == ""

    # Now test when email IS explicitly present on page
    page_text_with_email = """
    Prof. Dawn Song, Professor of EECS.
    Research: Deep learning security, LLM safety, blockchain.
    Contact: dawnsong@berkeley.edu
    """
    results_with_email = heuristic_professor_extractor(
        page_url="https://eecs.berkeley.edu/faculty/song",
        text_content=page_text_with_email,
        emails_found=["dawnsong@berkeley.edu"],
        profile=sample_profile,
        university_name="UC Berkeley"
    )
    assert len(results_with_email) > 0
    prof_song = results_with_email[0]
    assert prof_song["name"] == "Dawn Song"
    assert prof_song["email"] == "dawnsong@berkeley.edu"
    assert prof_song["email_source_url"] == "https://eecs.berkeley.edu/faculty/song"
    assert bool(prof_song["email_date_observed"])


def test_lab_discovery_and_affiliation_evidence(sample_profile):
    """
    If a professor's page refers to an external professional lab page,
    preserve the affiliation evidence and source relationship.
    """
    page_text = """
    Prof. Trevor Darrell is Director of the Berkeley Artificial Intelligence Research (BAIR) Lab.
    His laboratory investigates computer vision, multimodal foundation models, and autonomous systems.
    Visit the BAIR Lab website for recent preprints.
    """
    results = heuristic_professor_extractor(
        page_url="https://eecs.berkeley.edu/faculty/darrell",
        text_content=page_text,
        emails_found=[],
        profile=sample_profile,
        university_name="UC Berkeley"
    )

    assert len(results) > 0
    prof = results[0]
    assert "BAIR" in prof["lab_group"] or "Berkeley Artificial Intelligence Research" in prof["lab_group"]
    assert "Affiliated" in prof["affiliation_evidence"] or "profile" in prof["affiliation_evidence"].lower()


def test_recruitment_status_and_contact_instructions():
    """
    Tests detection of recruitment statuses and explicit contact instructions:
    - 'Apply through portal - Do not email'
    - 'Not accepting students'
    - 'Actively recruiting'
    """
    # 1. Portal only / do not email
    text_portal = """
    Prof. Alice Smith
    Prospective Students: Please note that all PhD admissions are handled centrally. 
    Apply through the portal directly to the department. Please do not send email inquiry.
    """
    rec_status, contact_inst, rec_ev = extract_contact_instructions_and_recruitment(text_portal)
    assert rec_status == "Apply through portal"
    assert "portal" in contact_inst.lower()
    assert "portal" in rec_ev.lower()

    # 2. Not accepting students
    text_closed = """
    Prof. Bob Brown
    Notice: I am on sabbatical during 2025-2026 and am not accepting students this cycle.
    """
    rec_status, contact_inst, rec_ev = extract_contact_instructions_and_recruitment(text_closed)
    assert rec_status == "Not accepting students"
    assert "not accepting" in contact_inst.lower()

    # 3. Actively recruiting
    text_active = """
    Prof. Carol White
    We are actively looking for 2 motivated PhD students in multi-agent reinforcement learning for Fall 2025.
    """
    rec_status, contact_inst, rec_ev = extract_contact_instructions_and_recruitment(text_active)
    assert rec_status == "Actively recruiting"
    assert "actively recruiting" in contact_inst.lower()


def test_funding_separation():
    """
    SEPARATE:
    - Research relevance
    - Explicit current recruitment
    - Funding explicitly tied to a position
    - Funding merely available elsewhere at the university
    """
    # 1. Position-tied funding
    text_position_funding = """
    Our group has an open NSF funded GRA position covering full tuition and monthly stipend for LLM security research.
    """
    fund_type, fund_ev = extract_funding_separation(text_position_funding)
    assert fund_type == "Explicit position-tied funding stated"
    assert "nsf funded" in fund_ev.lower()

    # 2. Departmental / University funding only
    text_dept_funding = """
    Admitted graduate students are typically funded via departmental fellowship and university financial aid.
    """
    fund_type, fund_ev = extract_funding_separation(text_dept_funding)
    assert fund_type == "Departmental / University funding only"

    # 3. Unstated
    text_no_funding = "We study abstract algebra and representation theory."
    fund_type, fund_ev = extract_funding_separation(text_no_funding)
    assert fund_type == "Unstated"


def test_explainable_rubric_breakdown(sample_profile):
    """
    Tests 4-part explainable rubric:
    Research Overlap (0-35), Documented Experience (0-25), Degree Fit (0-20), Recruitment Evidence (0-20).
    Verifies heuristic labeling (not admission probability) and missing information checklist.
    """
    prof = {
        "name": "Prof. David Miller",
        "title": "Full Professor & Chair",
        "department": "Department of Computer Science",
        "university": "Carnegie Mellon University",
        "lab_group": "Language Technologies Institute",
        "email": "Not found",
        "research_interests": "Large Language Models, Multi-Agent Systems, Neural Reasoning",
        "publications_projects": "Agentic Reasoning Frameworks (2024)",
        "recruitment_status": "Actively recruiting",
        "recruitment_evidence": "Actively recruiting PhD research assistants in LLM reasoning.",
        "position_funding_type": "Explicit position-tied funding stated",
        "position_funding_evidence": "Funded GRA position available.",
        "contact_instructions": "Email with CV",
        "evidence_snippet": "Prof. Miller leads the Language Technologies Institute."
    }

    rubric = compute_explainable_rubric(prof, sample_profile)

    # Check bounds and components
    assert rubric["is_heuristic_score"] is True
    assert 0 <= rubric["match_score"] <= 100
    assert 0 <= rubric["research_overlap_score"] <= 35
    assert 0 <= rubric["experience_fit_score"] <= 25
    assert 0 <= rubric["degree_fit_score"] <= 20
    assert 0 <= rubric["recruitment_fit_score"] <= 20

    # High match expected due to strong topic overlap and active recruitment
    assert rubric["match_score"] >= 75
    assert len(rubric["match_reasons"]) > 0
    # Missing information checklist should flag missing email
    assert any("email" in m.lower() for m in rubric["missing_information"])


def test_explainable_rubric_penalty_for_closed_recruitment(sample_profile):
    """A professor who is explicitly not accepting students receives a heavy penalty."""
    prof_closed = {
        "name": "Prof. Evelyn Reed",
        "title": "Professor",
        "department": "Computer Science",
        "research_interests": "Large Language Models",
        "recruitment_status": "Not accepting students",
        "recruitment_evidence": "Not taking new students this cycle.",
        "position_funding_type": "Unstated",
        "email": "Not found"
    }

    rubric = compute_explainable_rubric(prof_closed, sample_profile)
    assert rubric["recruitment_fit_score"] == -20
    assert any("not accepting" in m.lower() for m in rubric["missing_information"])


def test_deduplication_and_multi_affiliation_merging():
    """
    Deduplicate professors and contacts while preserving multiple affiliations where appropriate.
    """
    p1 = {
        "name": "Trevor Darrell",
        "title": "Professor",
        "department": "Computer Science Division",
        "lab_group": "BAIR Lab",
        "email": "Not found",
        "publications_projects": "Vision-Language Models",
        "match_score": 75,
        "source_url": "https://cs.berkeley.edu/faculty"
    }
    p2 = {
        "name": "Prof. Trevor Darrell",
        "title": "Professor",
        "department": "Department of Electrical Engineering",
        "lab_group": "Center for Human-Compatible AI",
        "email": "trevor@eecs.berkeley.edu",
        "publications_projects": "Autonomous Driving Systems",
        "match_score": 88,
        "source_url": "https://bair.berkeley.edu/director"
    }

    merged = deduplicate_and_merge_professors([p1], [p2])
    assert len(merged) == 1
    m = merged[0]
    # Affiliations merged
    assert "Computer Science" in m["department"] and "Electrical Engineering" in m["department"]
    assert "BAIR" in m["lab_group"] and "Human-Compatible" in m["lab_group"]
    # Email updated from second sighting
    assert m["email"] == "trevor@eecs.berkeley.edu"
    # Higher score retained
    assert m["match_score"] == 88


def test_database_professor_crud_and_filters():
    """Tests SQLite persistence, deduplication on insertion, and rich query filtering."""
    job_id = enqueue_research_job(
        university_url="https://cs.cmu.edu",
        university_name="Carnegie Mellon University",
        scope="faculty"
    )

    profs_data = [
        {
            "name": "William Cohen",
            "title": "Professor",
            "department": "Machine Learning Department",
            "university": "Carnegie Mellon University",
            "lab_group": "Language Technologies Institute",
            "email": "wcohen@cs.cmu.edu",
            "research_interests": "Information Extraction, Neural Reasoning",
            "publications_projects": "TensorLog Neural Database",
            "recruitment_status": "Actively recruiting",
            "recruitment_evidence": "Looking for PhD students in knowledge graphs.",
            "position_funding_type": "Explicit position-tied funding stated",
            "position_funding_evidence": "Funded RA position.",
            "contact_instructions": "Email with CV and transcripts",
            "match_score": 92,
            "research_overlap_score": 32,
            "experience_fit_score": 22,
            "degree_fit_score": 20,
            "recruitment_fit_score": 18,
            "match_reasons": ["Strong topic overlap in Neural Reasoning", "Active recruitment verified"],
            "missing_information": [],
            "score_breakdown": {"research_overlap": {"score": 32, "max": 35}},
            "source_url": "https://cs.cmu.edu/~wcohen"
        },
        {
            "name": "Tom Mitchell",
            "title": "Founding Chair & Professor",
            "department": "Machine Learning Department",
            "university": "Carnegie Mellon University",
            "lab_group": "Brain Image Analysis Group",
            "email": "Not found",
            "research_interests": "Machine Learning, Brain Imaging",
            "publications_projects": "Never-Ending Language Learning",
            "recruitment_status": "Unstated",
            "recruitment_evidence": "None stated in source",
            "position_funding_type": "Unstated",
            "contact_instructions": "Standard academic inquiry",
            "match_score": 60,
            "research_overlap_score": 20,
            "experience_fit_score": 10,
            "degree_fit_score": 20,
            "recruitment_fit_score": 10,
            "match_reasons": ["Faculty in target field"],
            "missing_information": ["Public email not found"],
            "score_breakdown": {},
            "source_url": "https://cs.cmu.edu/~tom"
        }
    ]

    inserted = insert_professors(job_id, profs_data)
    assert inserted == 2

    # 1. Query all for job
    all_job_profs = get_professors(job_id=job_id)
    assert len(all_job_profs) == 2
    assert isinstance(all_job_profs[0]["match_reasons"], list)

    # 2. Filter by min match score
    high_synergy = get_professors(job_id=job_id, min_match_score=80)
    assert len(high_synergy) == 1
    assert "William Cohen" in high_synergy[0]["name"]

    # 3. Filter by recruitment status
    recruiting = get_professors(job_id=job_id, recruitment_status="actively recruiting")
    assert len(recruiting) == 1
    assert "William Cohen" in recruiting[0]["name"]

    # 4. Filter by email presence
    with_email = get_professors(job_id=job_id, has_email=True)
    assert len(with_email) == 1
    assert "William Cohen" in with_email[0]["name"]

    no_email = get_professors(job_id=job_id, has_email=False)
    assert len(no_email) == 1
    assert no_email[0]["name"] == "Tom Mitchell"


def test_api_professors_endpoint():
    """Tests the /api/professors REST endpoint."""
    client = TestClient(app)
    response = client.get("/api/professors")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_pydantic_schema_strict_email_cleaning():
    """Pydantic schema validator must clean empty/unknown email to 'Not found'."""
    p1 = ProfessorItem(name="Jane Doe", email="unknown")
    assert p1.email == "Not found"

    p2 = ProfessorItem(name="John Smith", email="none")
    assert p2.email == "Not found"

    p3 = ProfessorItem(name="Alice Wang", email="alice@stanford.edu")
    assert p3.email == "alice@stanford.edu"
