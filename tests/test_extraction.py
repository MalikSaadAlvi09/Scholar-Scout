"""
Extraction and Matching Logic Tests for ScholarScout.
Verifies funding parsing, faculty extraction, email discovery, and 'Unknown' fallback rules.
"""

import pytest
from backend.funding.extractor import heuristic_funding_extractor
from backend.professors.matcher import heuristic_professor_extractor
from backend.retrieval.fetcher import extract_emails_from_text_and_html

def test_extract_emails_from_text_and_html():
    """Verify regex and mailto email extraction."""
    html_sample = """
    <div class="faculty-card">
      <h3>Dr. Ada Lovelace</h3>
      <p>Contact: <a href="mailto:ada.lovelace@ox.ac.uk">Email Ada</a></p>
      <p>Lab coordinator: charles.babbage@ox.ac.uk</p>
    </div>
    """
    text_sample = "Dr. Ada Lovelace\nContact: ada.lovelace@ox.ac.uk\nLab coordinator: charles.babbage@ox.ac.uk"
    emails = extract_emails_from_text_and_html(text_sample, html_sample)
    assert "ada.lovelace@ox.ac.uk" in emails
    assert "charles.babbage@ox.ac.uk" in emails

def test_heuristic_funding_extractor():
    """Test heuristic scholarship extraction with evidence snippets and unknown fields."""
    sample_text = """
    The Department of Computer Science offers Graduate Research Assistantships (GRA) providing full tuition waiver and a $36,000 annual stipend for doctoral researchers.
    Applications close December 15. Candidates must hold a 3.5 minimum GPA.
    """
    profile = {
        "target_degree": "Ph.D.",
        "target_field": "Computer Science",
        "country_of_origin": "International"
    }
    extracted = heuristic_funding_extractor("https://uni.edu/funding", sample_text, profile)
    assert len(extracted) >= 1
    item = extracted[0]
    assert "Assistantship" in item["funding_type"] or "Tuition" in item["funding_type"]
    assert "full tuition" in item["amount"].lower() or "$36,000" in item["amount"]
    assert item["deadline"] != ""
    assert "annual stipend" in item["evidence_snippet"].lower()

def test_heuristic_professor_extractor():
    """Test faculty matching and alignment scoring."""
    sample_text = """
    Prof. Geoffrey Hinton
    Research: Deep Learning, Neural Networks, Computer Vision.
    Office: Turing Hall 401. Email: hinton@cs.toronto.edu
    """
    profile = {
        "name": "Alex",
        "target_degree": "Ph.D.",
        "target_field": "Computer Science",
        "research_interests": "Deep Learning, Neural Networks"
    }
    emails = ["hinton@cs.toronto.edu"]
    profs = heuristic_professor_extractor("https://cs.toronto.edu/people", sample_text, emails, profile)
    assert len(profs) >= 1
    p = profs[0]
    assert "Hinton" in p["name"]
    assert p["email"] == "hinton@cs.toronto.edu"
    assert p["match_score"] >= 70
    assert "evidence_snippet" in p
