"""
Unit and Integration Tests for ScholarScout Academic Profile, Versioning,
Data Minimization, CV Document Parsing, and Completeness Checklist.
"""

import io
import json
import zipfile
import xml.etree.ElementTree as ET
import pytest
from starlette.testclient import TestClient

try:
    import fitz
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

from backend.main import app
from backend.profiles.cv_parser import (
    extract_text_from_pdf,
    extract_text_from_docx,
    heuristic_cv_extractor,
    extract_facts_from_cv
)
from backend.profiles.manager import (
    calculate_completeness,
    get_task_specific_profile,
    get_current_profile,
    update_or_create_profile,
    get_profile_history
)
from backend.database import get_profile_versions, save_profile

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

# --- 1. Document Parsing & Scanned Detection Tests ---

def test_docx_text_extraction():
    """Verify DOCX parser reads word/document.xml without external word processors."""
    # Create an in-memory .docx zip file
    docx_io = io.BytesIO()
    with zipfile.ZipFile(docx_io, "w") as z:
        xml_content = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
            <w:body>
                <w:p><w:r><w:t>Alex Rivera - Curriculum Vitae</w:t></w:r></w:p>
                <w:p><w:r><w:t>Bachelor of Science in Computer Science, Technical University of Munich</w:t></w:r></w:p>
                <w:p><w:r><w:t>GPA: 3.92 / 4.0. Research Interests: Multi-Agent Systems.</w:t></w:r></w:p>
            </w:body>
        </w:document>"""
        z.writestr("word/document.xml", xml_content)
    
    success, text, error = extract_text_from_docx(docx_io.getvalue())
    assert success is True
    assert "Alex Rivera" in text
    assert "3.92 / 4.0" in text
    assert error is None

def test_docx_invalid_format():
    """Verify error handling for invalid or corrupted docx files."""
    success, text, error = extract_text_from_docx(b"not a valid zip")
    assert success is False
    assert "Could not parse DOCX" in error

@pytest.mark.skipif(not HAS_FITZ, reason="PyMuPDF not available")
def test_pdf_text_extraction():
    """Verify PDF extraction extracts clean text."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Alex Rivera\nB.S. in Computer Science\nTechnical University of Munich\nGPA: 8.8 / 10.0\nTOEFL iBT 112\nGitHub: https://github.com/alexrivera-research\nPublications: 1 paper at NeurIPS")
    pdf_bytes = doc.tobytes()
    doc.close()

    success, text, error = extract_text_from_pdf(pdf_bytes)
    assert success is True
    assert "Alex Rivera" in text
    assert "8.8 / 10.0" in text
    assert error is None

@pytest.mark.skipif(not HAS_FITZ, reason="PyMuPDF not available")
def test_pdf_scanned_image_detection():
    """Verify scanned/image-only PDFs trigger informative error messages."""
    import fitz
    # Create empty PDF page with image but no text
    doc = fitz.open()
    page = doc.new_page()
    # Insert a minimal 1x1 pixmap image
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 10, 10), 1)
    page.insert_image(page.rect, pixmap=pix)
    pdf_bytes = doc.tobytes()
    doc.close()

    success, text, error = extract_text_from_pdf(pdf_bytes)
    assert success is False
    assert "Scanned image-only PDF detected" in error

# --- 2. Fact Extraction & GPA Scale Preservation Tests ---

def test_heuristic_cv_fact_extractor_preserves_gpa():
    """Verify GPA scale is preserved verbatim without math conversion or equivalence declarations."""
    cv_sample_10_scale = """
    Jane Doe
    Bachelor of Technology in Electrical Engineering
    Indian Institute of Technology
    CGPA: 8.9 / 10.0
    TOEFL: 108
    Technical Skills: Python, PyTorch, C++
    GitHub: https://github.com/janedoe
    Publications: Deep Learning for Robot Perception
    """
    facts = heuristic_cv_extractor(cv_sample_10_scale)
    assert facts.get("full_name") == "Jane Doe"
    assert facts.get("gpa") == "8.9 / 10.0"  # Original scale preserved!
    assert facts.get("github_url") == "https://github.com/janedoe"
    assert "TOEFL" in facts.get("english_tests", "")

    cv_sample_honors = """
    John Smith
    Master of Science in Artificial Intelligence
    University of Edinburgh
    Grade: First Class Honours with Distinction
    """
    facts_honors = heuristic_cv_extractor(cv_sample_honors)
    assert "First Class Honours" in facts_honors.get("gpa", "")

def test_async_cv_fact_extraction():
    """Verify end-to-end async fact extraction return structure."""
    import asyncio
    async def run_test():
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 50), "Maria Garcia\nBachelor of Science in Robotics\nUniversity of Michigan\nGPA: 3.88 / 4.0\nIELTS 8.5\nTechnical Skills: ROS, C++, Python, OpenCV\nhttps://github.com/mariagarcia")
        pdf_bytes = doc.tobytes()
        doc.close()

        result = await extract_facts_from_cv("maria_cv.pdf", pdf_bytes)
        assert result["success"] is True
        assert "proposed_facts" in result
        facts = result["proposed_facts"]
        assert facts.get("full_name") == "Maria Garcia"
        assert "3.88" in str(facts.get("gpa", ""))
        assert "maria_cv.pdf" in result["filename"]

    asyncio.run(run_test())

# --- 3. Profile Completeness & Checklist Scoring Tests ---

def test_calculate_completeness_incomplete_profile():
    """Verify incomplete profile receives an accurate weighted score without fabricating missing fields."""
    incomplete_profile = {
        "name": "Prospective Student",
        "full_name": "Prospective Student",
        "nationality": "Unknown",
        "current_residence": "Unknown",
        "current_degree": "Unknown",
        "current_institution": "Unknown",
        "gpa": "Unknown",
        "graduation_date": "Unknown",
        "target_degree": "Ph.D.",
        "broad_subject": "Computer Science",
        "specific_interests": "",
        "intended_intake": "Unknown",
        "preferred_countries": [],
        "excluded_countries": [],
        "english_tests": "Unknown",
        "technical_skills": "",
        "projects": "",
        "publications": "",
        "research_experience": "",
        "background_summary": "",
        "funding_needs": [],
        "github_url": "",
        "portfolio_url": "",
        "website_url": ""
    }
    comp = calculate_completeness(incomplete_profile)
    assert comp["score"] < 40
    assert comp["tier_class"] == "low"
    assert "GPA & Original Grading Scale" in comp["missing_items"]
    assert "Nationality / Citizenship" in comp["missing_items"]

def test_calculate_completeness_comprehensive_profile():
    """Verify complete profile scores high (>85%) with all pillars checked."""
    comprehensive_profile = {
        "name": "Alex Rivera",
        "full_name": "Alex Rivera",
        "nationality": "Germany",
        "current_residence": "Germany",
        "current_degree": "B.S. in Computer Science",
        "current_institution": "Technical University of Munich",
        "gpa": "3.92 / 4.0",
        "graduation_date": "June 2025",
        "target_degree": "Ph.D.",
        "broad_subject": "Computer Science",
        "target_field": "Computer Science",
        "specific_interests": "Multi-Agent Systems, LLMs",
        "research_interests": "Multi-Agent Systems, LLMs",
        "intended_intake": "Fall 2025",
        "preferred_countries": ["United States", "Germany"],
        "english_tests": "TOEFL 112",
        "technical_skills": "Python, PyTorch",
        "research_experience": "NLP Lab Undergrad Researcher",
        "background_summary": "Strong foundation in deep learning and compilers.",
        "funding_needs": ["full_tuition", "living_stipend"],
        "github_url": "https://github.com/alexrivera-research"
    }
    comp = calculate_completeness(comprehensive_profile)
    assert comp["score"] >= 85
    assert comp["tier_class"] == "high"
    assert len(comp["missing_items"]) == 0

# --- 4. Data Minimization Task Projections Tests ---

def test_get_task_specific_profile_data_minimization():
    """Verify task-specific projections send only necessary fields to the AI model."""
    full_profile = {
        "name": "Alex Rivera",
        "nationality": "Germany",
        "current_residence": "Germany",
        "current_degree": "B.S. in Computer Science",
        "current_institution": "TUM",
        "gpa": "3.92 / 4.0",
        "target_degree": "Ph.D.",
        "broad_subject": "Computer Science",
        "target_field": "Computer Science",
        "specific_interests": "Multi-Agent Coordination, Reasoning",
        "research_interests": "Multi-Agent Coordination, Reasoning",
        "preferred_countries": ["United States"],
        "intended_intake": "Fall 2025",
        "english_tests": "TOEFL 112",
        "technical_skills": "Python, CUDA, PyTorch",
        "publications": "1 paper in NeurIPS",
        "projects": "ScholarScout Autonomous Agent",
        "research_experience": "NLP Lab",
        "funding_needs": ["full_tuition", "living_stipend"],
        "github_url": "https://github.com/alexrivera",
        "portfolio_url": "https://alexrivera.dev",
        "background_summary": "Top 5% student in CS."
    }

    # 1. Scholarship Eligibility
    scholarship_view = get_task_specific_profile(full_profile, "scholarship_eligibility")
    assert "gpa" in scholarship_view
    assert "nationality" in scholarship_view
    assert "funding_needs" in scholarship_view
    assert "preferred_countries" in scholarship_view
    assert "technical_skills" not in scholarship_view  # Excluded
    assert "portfolio_url" not in scholarship_view  # Excluded

    # 2. Professor Matching
    professor_view = get_task_specific_profile(full_profile, "professor_matching")
    assert "target_degree" in professor_view
    assert "research_interests" in professor_view
    assert "technical_skills" in professor_view
    assert "publications" in professor_view
    assert "gpa" not in professor_view  # Excluded from professor synergy matching
    assert "funding_needs" not in professor_view  # Excluded

    # 3. Email Drafting
    email_view = get_task_specific_profile(full_profile, "email_drafting")
    assert "name" in email_view
    assert "background_summary" in email_view
    assert "research_interests" in email_view
    assert "funding_needs" not in email_view

# --- 5. Versioning & Snapshot Persistence Tests ---

def test_profile_versioning_and_snapshots():
    """Verify profile updates increment version and record immutable snapshots in SQLite."""
    # First save
    p1 = update_or_create_profile({
        "full_name": "Test Student V1",
        "target_degree": "Master's",
        "gpa": "3.80 / 4.0",
        "broad_subject": "Data Science"
    })
    v1_num = p1.get("version", 1)
    
    # Second save with modifications
    p2 = update_or_create_profile({
        "id": p1["id"],
        "full_name": "Test Student V2",
        "target_degree": "Ph.D.",
        "gpa": "3.80 / 4.0",
        "broad_subject": "Artificial Intelligence"
    })
    v2_num = p2.get("version", 2)
    assert v2_num > v1_num

    # Check history (ordered newest first)
    history = get_profile_history(p1["id"])
    assert len(history) >= 2
    assert history[0]["version"] == v2_num
    assert history[0]["snapshot"]["name"] == "Test Student V2"

# --- 6. API Route Integration Tests ---

def test_api_profile_crud_and_privacy_preview(client):
    """Verify REST API /api/profile, /api/profile/versions, and /api/profile/privacy-preview."""
    # 1. GET active profile
    res = client.get("/api/profile")
    assert res.status_code == 200
    p = res.json()
    assert "completeness" in p
    assert "score" in p["completeness"]

    # 2. POST update profile
    res_update = client.post("/api/profile", json={
        "full_name": "Dr. Candidate",
        "nationality": "Canada",
        "current_residence": "Canada",
        "gpa": "3.95 / 4.0",
        "target_degree": "Ph.D.",
        "broad_subject": "Computer Science",
        "preferred_countries": ["Canada", "United States"],
        "funding_needs": ["full_tuition", "living_stipend"]
    })
    assert res_update.status_code == 200
    update_data = res_update.json()
    assert update_data["success"] is True
    assert "version" in update_data

    # 3. GET version history
    res_versions = client.get("/api/profile/versions")
    assert res_versions.status_code == 200
    versions = res_versions.json()
    assert isinstance(versions, list)

    # 4. GET privacy preview
    res_privacy = client.get("/api/profile/privacy-preview")
    assert res_privacy.status_code == 200
    privacy = res_privacy.json()
    assert "scholarship_eligibility" in privacy
    assert "professor_matching" in privacy
    assert "email_drafting" in privacy

def test_api_cv_upload_endpoint(client):
    """Verify /api/profile/upload-cv endpoint parses file and returns proposed facts."""
    # Create mock PDF file
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "David Chen\nB.S. in Computer Engineering\nNational University of Singapore\nGPA: 4.85 / 5.0\nTOEFL: 115\nTechnical Skills: C++, CUDA, Python\nhttps://github.com/davidchen-research")
    pdf_bytes = doc.tobytes()
    doc.close()

    files = {"file": ("david_cv.pdf", pdf_bytes, "application/pdf")}
    res = client.post("/api/profile/upload-cv", files=files)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "proposed_facts" in data
    assert data["proposed_facts"]["full_name"] == "David Chen"
    assert "4.85 / 5.0" in data["proposed_facts"]["gpa"]  # Original 5.0 scale preserved!
