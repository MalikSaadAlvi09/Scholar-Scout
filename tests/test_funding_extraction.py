"""
Comprehensive Test Suite for Evidence-Based Scholarship & Funding Extraction.
Tests:
1. 5 canonical funding categories (Full tuition + living, Tuition-only, Partial funding, Conditional assistantship, Unclear funding)
2. Opportunity statuses (open, upcoming, closed, unknown) against reference date 2026-09-29
3. Date-only deadline normalization (YYYY-MM-DD without invented closing times)
4. Candidate eligibility boundary evaluations (Appears eligible, Appears ineligible, Needs clarification)
5. Mandatory admissions disclaimer inclusion
6. Verbatim claims evidence dictionary mapping
7. Database persistence and rich API filtering
8. Pydantic schema validation and bounds
"""

import pytest
from datetime import date
from backend.funding.extractor import (
    parse_date_only,
    compute_opportunity_status,
    classify_funding_category,
    evaluate_candidate_eligibility,
    extract_claims_evidence_dict,
    heuristic_funding_extractor,
    CURRENT_REFERENCE_DATE
)
from backend.llm.schemas import ScholarshipItem, ScholarshipListResponse
from backend.database import init_db, insert_scholarships, get_scholarships, enqueue_research_job

@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()

# --- 1. Funding Category Classification Tests ---

def test_classify_full_tuition_plus_living_support():
    text = "The Presidential Fellowship provides 100% full tuition waiver plus an annual living stipend of $38,000 for 4 years."
    category = classify_funding_category(
        text=text,
        tuition_coverage="100% full tuition waiver",
        stipend_amount="$38,000/year",
        funding_type="Fellowship"
    )
    assert category == "Explicit full tuition plus living support"

def test_classify_tuition_only_support():
    text = "The Dean's Award covers 100% full tuition waiver for graduate study. Living expenses and housing are excluded."
    category = classify_funding_category(
        text=text,
        tuition_coverage="100% full tuition waiver",
        stipend_amount="None",
        funding_type="Tuition Waiver"
    )
    assert category == "Tuition-only support"

def test_classify_partial_funding():
    text = "International students receive a $5,000 merit award applied towards first-year fees. Partial tuition grant."
    category = classify_funding_category(
        text=text,
        tuition_coverage="Partial grant",
        stipend_amount="None",
        funding_type="Merit Award"
    )
    assert category == "Partial funding"

def test_classify_conditional_assistantship():
    text = "Graduate Teaching Assistantships (GTA) require 20 hours/week teaching service and are conditional upon departmental grant allocation and 3.5 GPA maintenance."
    category = classify_funding_category(
        text=text,
        tuition_coverage="Full tuition waiver",
        stipend_amount="$28,000",
        obligations="20 hours/week GTA teaching duties",
        funding_type="Assistantship (GRA/GTA)"
    )
    assert category == "Conditional assistantship"

def test_classify_unclear_funding_vague_mention():
    text = "Departmental scholarships are available for eligible candidates. Financial aid may be provided depending on availability."
    category = classify_funding_category(
        text=text,
        tuition_coverage="Unknown",
        stipend_amount="Unknown",
        funding_type="Unknown"
    )
    assert category == "Unclear funding"

# --- 2. Date-Only Deadline Normalization (No Invented Times) ---

def test_parse_date_only_iso():
    assert parse_date_only("2026-12-15") == "2026-12-15"
    assert parse_date_only("Deadline: 2027-01-15 23:59:59") == "2027-01-15"

def test_parse_date_only_month_day_year():
    assert parse_date_only("December 15, 2026") == "2026-12-15"
    assert parse_date_only("Dec 15 2026") == "2026-12-15"
    assert parse_date_only("January 5th, 2027 at 11:59 PM EST") == "2027-01-05"
    assert parse_date_only("1st of November 2026") == "2026-11-01"

def test_parse_date_only_day_month_year():
    assert parse_date_only("15 December 2026") == "2026-12-15"
    assert parse_date_only("28 Feb 2027") == "2027-02-28"

def test_parse_date_only_slash_format():
    assert parse_date_only("12/15/2026") == "2026-12-15"
    assert parse_date_only("15/12/2026") == "2026-12-15"

def test_parse_date_only_inferred_year():
    # Today is 2026-09-29
    ref = date(2026, 9, 29)
    # December 1 is later in 2026
    assert parse_date_only("December 1", ref_date=ref) == "2026-12-01"
    # January 15 is in next year (2027)
    assert parse_date_only("January 15", ref_date=ref) == "2027-01-15"

def test_parse_date_only_never_invents_time():
    res = parse_date_only("December 15, 2026")
    assert res == "2026-12-15"
    assert ":" not in res
    assert "T" not in res
    assert " " not in res

def test_parse_date_only_unknown():
    assert parse_date_only("Unknown") is None
    assert parse_date_only("Rolling admissions") is None
    assert parse_date_only("") is None

# --- 3. Opportunity Status Computation (Reference Date 2026-09-29) ---

def test_opportunity_status_expired_deadline():
    # Past date
    status = compute_opportunity_status(
        deadline_str="May 1, 2026",
        deadline_date_iso="2026-05-01",
        ref_date=date(2026, 9, 29)
    )
    assert status == "closed"

def test_opportunity_status_future_open_deadline():
    # Future date
    status = compute_opportunity_status(
        deadline_str="December 15, 2026",
        deadline_date_iso="2026-12-15",
        ref_date=date(2026, 9, 29)
    )
    assert status == "open"

def test_opportunity_status_upcoming_cycle():
    # Explicit upcoming intake/opening
    status = compute_opportunity_status(
        deadline_str="January 15, 2027",
        deadline_date_iso="2027-01-15",
        text_context="Applications open in November 2026 for Fall 2027 cycle.",
        ref_date=date(2026, 9, 29)
    )
    assert status == "upcoming"

def test_opportunity_status_rolling():
    status = compute_opportunity_status(
        deadline_str="Rolling admissions until filled",
        deadline_date_iso=None,
        ref_date=date(2026, 9, 29)
    )
    assert status == "open"

def test_opportunity_status_unknown():
    status = compute_opportunity_status(
        deadline_str="Check back later for deadlines",
        deadline_date_iso=None,
        ref_date=date(2026, 9, 29)
    )
    assert status == "unknown"

# --- 4. Candidate Eligibility Boundaries & Admissions Disclaimer ---

def test_eligibility_appears_eligible():
    criteria = "Open to all nationalities applying for Ph.D. programs with a minimum 3.5 GPA."
    profile = {
        "target_degree": "Ph.D.",
        "gpa": "3.85 / 4.0",
        "nationality": "International"
    }
    status, explanation = evaluate_candidate_eligibility(criteria, profile)
    assert status == "Appears eligible"
    assert "meets or exceeds minimum requirement" in explanation
    assert "not an official university admission decision" in explanation

def test_eligibility_appears_ineligible_due_to_gpa():
    criteria = "Applicants must hold at least a 3.7 GPA for fellowship consideration."
    profile = {
        "target_degree": "Ph.D.",
        "gpa": "3.30 / 4.0",
        "nationality": "International"
    }
    status, explanation = evaluate_candidate_eligibility(criteria, profile)
    assert status == "Appears ineligible"
    assert "is below published minimum" in explanation
    assert "not an official university admission decision" in explanation

def test_eligibility_appears_ineligible_due_to_nationality():
    criteria = "This grant is restricted to domestic US citizens only."
    profile = {
        "target_degree": "Ph.D.",
        "gpa": "3.90 / 4.0",
        "nationality": "Canada"
    }
    status, explanation = evaluate_candidate_eligibility(criteria, profile)
    assert status == "Appears ineligible"
    assert "Restricted to domestic applicants" in explanation
    assert "not an official university admission decision" in explanation

def test_eligibility_needs_clarification_missing_details():
    criteria = "Funding decisions are made by the graduate committee based on overall file quality."
    profile = {
        "target_degree": "Ph.D.",
        "gpa": "3.75",
        "nationality": "International"
    }
    status, explanation = evaluate_candidate_eligibility(criteria, profile)
    assert status == "Needs clarification"
    assert "Specific minimum academic cutoff not explicitly stated" in explanation or "Criteria require departmental review" in explanation
    assert "not an official university admission decision" in explanation

# --- 5. Claims Evidence Mapping ---

def test_extract_claims_evidence_dict():
    paragraph = (
        "Full tuition waiver is granted to all admitted doctoral students. "
        "Students receive a $36,000 annual living stipend paid monthly. "
        "Applicants must possess a minimum 3.5 GPA and submit GRE scores. "
        "The application deadline is December 15, 2026. "
        "GTA positions involve 20 hours/week teaching duties. "
        "Comprehensive health insurance and a $1,500 travel grant are provided."
    )
    claims = extract_claims_evidence_dict(paragraph, "https://cs.university.edu/funding")
    
    assert "tuition" in claims
    assert "Full tuition waiver" in claims["tuition"]
    
    assert "stipend" in claims
    assert "$36,000" in claims["stipend"]
    
    assert "eligibility" in claims
    assert "3.5 GPA" in claims["eligibility"]
    
    assert "deadline" in claims
    assert "December 15, 2026" in claims["deadline"]
    
    assert "obligations" in claims
    assert "20 hours/week" in claims["obligations"]
    
    assert "insurance_travel" in claims
    assert "health insurance" in claims["insurance_travel"].lower()

# --- 6. End-to-End Heuristic Extractor Tests ---

def test_heuristic_extractor_full_award():
    text = """
    The Dean's Doctoral Fellowship provides a 100% full tuition waiver and a $36,000 annual stipend for 4 years.
    Open to international applicants applying for Ph.D. in Computer Science with a minimum 3.5 GPA.
    Applications close December 15, 2026. Includes full health insurance and travel award.
    """
    profile = {
        "target_degree": "Ph.D.",
        "target_field": "Computer Science",
        "gpa": "3.80 / 4.0",
        "nationality": "International"
    }
    items = heuristic_funding_extractor("https://mit.edu/admissions/funding", text, profile)
    assert len(items) >= 1
    item = items[0]
    
    assert item["funding_category"] == "Explicit full tuition plus living support"
    assert item["opportunity_status"] == "open"
    assert item["deadline_date"] == "2026-12-15"
    assert item["eligibility_status"] == "Appears eligible"
    assert "not an official university admission decision" in item["eligibility_explanation"]
    assert "tuition" in item["claims_evidence"]
    assert "stipend" in item["claims_evidence"]
    assert item["tuition_coverage"] == "100% full tuition waiver"
    assert item["stipend_currency"] == "USD"

def test_heuristic_extractor_expired_partial_award():
    text = """
    Global Merit Award: $5,000 partial entrance grant for Master's students.
    Deadline was January 15, 2026. Applicants must have minimum 3.2 GPA.
    """
    profile = {
        "target_degree": "Master's",
        "target_field": "Data Science",
        "gpa": "3.60",
        "nationality": "International"
    }
    items = heuristic_funding_extractor("https://ox.ac.uk/funding", text, profile)
    assert len(items) >= 1
    item = items[0]
    
    assert item["funding_category"] == "Partial funding"
    assert item["opportunity_status"] == "closed"
    assert item["deadline_date"] == "2026-01-15"
    assert item["eligibility_status"] == "Appears eligible"

def test_heuristic_extractor_conditional_assistantship():
    text = """
    Graduate Research Assistantships (GRA) cover full tuition plus $2,400 monthly stipend.
    Requires 20 hours/week research duties in faculty laboratory, conditional on grant funding.
    Priority deadline: December 1, 2026.
    """
    profile = {
        "target_degree": "Ph.D.",
        "target_field": "Robotics",
        "gpa": "3.90",
        "nationality": "International"
    }
    items = heuristic_funding_extractor("https://cmu.edu/funding", text, profile)
    assert len(items) >= 1
    item = items[0]
    
    assert item["funding_category"] == "Conditional assistantship"
    assert "20 Hours/Week" in item["obligations"]
    assert item["opportunity_status"] == "open"
    assert item["deadline_date"] == "2026-12-01"

# --- 7. Database Persistence & Rich Filtering Tests ---

def test_database_insert_and_filter_scholarships():
    job_id = enqueue_research_job("https://stanford.edu/grad-funding", scope="funding")
    
    scholarships_data = [
        {
            "title": "Stanford Knight-Hennessy Scholars",
            "university": "Stanford University",
            "country": "USA",
            "program": "Computer Science",
            "degree_level": "Ph.D.",
            "funding_category": "Explicit full tuition plus living support",
            "funding_type": "Fellowship",
            "intake_and_year": "Fall 2027",
            "international_eligibility": "Open to International & Domestic",
            "nationality_restrictions": "None stated",
            "academic_requirements": "High academic distinction",
            "tuition_coverage": "100% full tuition",
            "stipend_amount": "$45,000",
            "stipend_currency": "USD",
            "stipend_frequency": "Annual",
            "amount": "$45,000/yr + full tuition",
            "currency": "USD",
            "funding_duration": "3 years",
            "insurance_and_travel": "Full health insurance and travel stipend",
            "other_costs": "Living stipend covers books and supplies",
            "obligations": "No teaching obligations",
            "renewal_conditions": "Maintain 3.5 GPA",
            "application_fee": "Waiver available",
            "deadline": "October 14, 2026 at 13:00 PST",
            "deadline_date": "2026-10-14",
            "opportunity_status": "open",
            "application_route": "Separate scholarship portal",
            "official_url": "https://knight-hennessy.stanford.edu",
            "eligibility_status": "Appears eligible",
            "eligibility_explanation": "Applicant meets leadership and Ph.D. criteria. Preliminary eligibility check based on published criteria; not an official university admission decision.",
            "claims_evidence": {"tuition": "Full tuition covered", "stipend": "$45,000 annual living stipend"},
            "source_url": "https://knight-hennessy.stanford.edu",
            "fit_score": 95,
            "fit_reason": "Exceptional fit for doctoral candidate"
        },
        {
            "title": "Departmental GTA Teaching Award",
            "university": "Stanford University",
            "country": "USA",
            "program": "Computer Science",
            "degree_level": "Ph.D.",
            "funding_category": "Conditional assistantship",
            "funding_type": "Assistantship (GRA/GTA)",
            "intake_and_year": "2026-2027",
            "international_eligibility": "Open to International & Domestic",
            "tuition_coverage": "Full tuition waiver",
            "stipend_amount": "$32,000",
            "obligations": "20 hrs/week teaching assistant",
            "deadline": "May 1, 2026",
            "deadline_date": "2026-05-01",
            "opportunity_status": "closed",
            "eligibility_status": "Needs clarification",
            "eligibility_explanation": "Requires faculty assignment. Preliminary eligibility check based on published criteria; not an official university admission decision.",
            "source_url": "https://cs.stanford.edu/gta",
            "fit_score": 75
        }
    ]
    
    inserted = insert_scholarships(job_id, scholarships_data)
    assert inserted == 2
    
    # Query all
    all_items = get_scholarships(job_id=job_id)
    assert len(all_items) == 2
    assert isinstance(all_items[0]["claims_evidence"], dict)
    assert all_items[0]["claims_evidence"].get("tuition") == "Full tuition covered"
    
    # Filter by Funding Category
    full_items = get_scholarships(job_id=job_id, funding_category="Explicit full tuition plus living support")
    assert len(full_items) == 1
    assert full_items[0]["title"] == "Stanford Knight-Hennessy Scholars"
    
    asst_items = get_scholarships(job_id=job_id, funding_category="Conditional assistantship")
    assert len(asst_items) == 1
    assert asst_items[0]["title"] == "Departmental GTA Teaching Award"
    
    # Filter by Opportunity Status
    open_items = get_scholarships(job_id=job_id, opportunity_status="open")
    assert len(open_items) == 1
    assert open_items[0]["opportunity_status"] == "open"
    
    closed_items = get_scholarships(job_id=job_id, opportunity_status="closed")
    assert len(closed_items) == 1
    assert closed_items[0]["opportunity_status"] == "closed"
    
    # Filter by Eligibility Status
    eligible_items = get_scholarships(job_id=job_id, eligibility_status="Appears eligible")
    assert len(eligible_items) == 1
    assert eligible_items[0]["eligibility_status"] == "Appears eligible"

# --- 8. Pydantic Schema Typed Validation Tests ---

def test_pydantic_scholarship_item_validation():
    valid_data = {
        "title": "Gates Cambridge Scholarship",
        "university": "University of Cambridge",
        "country": "United Kingdom",
        "program": "All Graduate Programs",
        "degree_level": "Ph.D.",
        "funding_category": "Explicit full tuition plus living support",
        "funding_type": "Fellowship",
        "intake_and_year": "October 2027",
        "international_eligibility": "International Only",
        "nationality_restrictions": "Citizens of countries outside the UK",
        "academic_requirements": "First-class honors or minimum 3.8 GPA",
        "tuition_coverage": "100% University Composition Fee",
        "stipend_amount": "£20,000",
        "stipend_currency": "GBP",
        "stipend_frequency": "Annual",
        "amount": "£20,000 maintenance + full fees",
        "currency": "GBP",
        "funding_duration": "4 years",
        "insurance_and_travel": "Airfare and visa fees covered",
        "other_costs": "Academic development funding up to £2,000",
        "obligations": "No service obligations",
        "renewal_conditions": "Satisfactory academic progress",
        "application_fee": "£75",
        "deadline": "December 3, 2026 at 23:59 GMT",
        "deadline_date": "2026-12-03",
        "opportunity_status": "open",
        "application_route": "Integrated with university application portal",
        "official_url": "https://www.gatescambridge.org",
        "eligibility_status": "Appears eligible",
        "eligibility_explanation": "Candidate is international and has 3.9 GPA. Preliminary eligibility check based on published criteria; not an official university admission decision.",
        "department": "University-wide",
        "evidence_snippet": "A Gates Cambridge Scholarship covers the full cost of studying at Cambridge.",
        "claims_evidence": {
            "tuition": "Covers the full University Composition Fee",
            "stipend": "Maintenance allowance of £20,000 for 12 months"
        },
        "fit_score": 96,
        "fit_reason": "High leadership and academic synergy"
    }
    
    item = ScholarshipItem(**valid_data)
    assert item.title == "Gates Cambridge Scholarship"
    assert item.funding_category == "Explicit full tuition plus living support"
    assert item.fit_score == 96
    assert item.deadline_date == "2026-12-03"
    
    # Test Root List Container
    list_response = ScholarshipListResponse(scholarships=[item])
    assert len(list_response.scholarships) == 1
    dumped = list_response.model_dump()
    assert dumped["scholarships"][0]["stipend_currency"] == "GBP"
