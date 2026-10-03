"""
Pydantic Schemas for Structured Output Validation in ScholarScout.
Ensures strict typed validation and bounds for extracted scholarships,
faculty matches, outreach email drafts, and token usage metrics.
"""

from typing import List, Optional, Generic, TypeVar, Any, Dict
from pydantic import BaseModel, Field, field_validator

T = TypeVar("T")

class UsageMetrics(BaseModel):
    """Token usage tracking for AI calls."""
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)

    @classmethod
    def from_provider_response(cls, usage: Any) -> "UsageMetrics":
        """Extracts token counts safely from OpenAI-compatible completion usage."""
        if not usage:
            return cls()
        if isinstance(usage, dict):
            p = usage.get("prompt_tokens", 0) or 0
            c = usage.get("completion_tokens", 0) or 0
            t = usage.get("total_tokens", p + c) or (p + c)
            return cls(prompt_tokens=p, completion_tokens=c, total_tokens=t)
        p = getattr(usage, "prompt_tokens", 0) or 0
        c = getattr(usage, "completion_tokens", 0) or 0
        t = getattr(usage, "total_tokens", p + c) or (p + c)
        return cls(prompt_tokens=p, completion_tokens=c, total_tokens=t)

class LLMResult(BaseModel, Generic[T]):
    """Standard container for AI client structured and text responses."""
    data: Optional[T] = None
    raw_text: str = ""
    usage: UsageMetrics = Field(default_factory=UsageMetrics)
    model: str = ""
    latency_ms: float = 0.0
    repaired: bool = False
    finish_reason: Optional[str] = None

class ScholarshipItem(BaseModel):
    """Single evidence-based scholarship or financial aid opportunity."""
    title: str = Field(..., min_length=2, description="Title of the scholarship or funding opportunity")
    university: str = Field(default="Unknown", description="University or institution name")
    country: str = Field(default="Unknown", description="Country location of the university")
    program: str = Field(default="Unknown", description="Academic program or department")
    degree_level: str = Field(default="Unknown", description="Degree level: Ph.D., Master's, Bachelor's, Postdoc, Unknown")
    funding_category: str = Field(
        default="Unclear funding",
        description="One of: 'Explicit full tuition plus living support', 'Tuition-only support', 'Partial funding', 'Conditional assistantship', 'Unclear funding'"
    )
    funding_type: str = Field(default="Unknown", description="Specific funding type: Fellowship, Assistantship (GRA/GTA), Tuition Waiver, Merit Award, etc.")
    intake_and_year: str = Field(default="Unknown", description="Intake and academic year, e.g. 'Fall 2027', '2026-2027'")
    international_eligibility: str = Field(default="Unknown", description="International applicant eligibility, e.g. 'Open to International & Domestic', 'Domestic Only'")
    nationality_restrictions: str = Field(default="None stated", description="Nationality restrictions or 'None stated'")
    academic_requirements: str = Field(default="Unknown", description="Academic & language requirements (GPA, TOEFL, IELTS)")
    tuition_coverage: str = Field(default="Unknown", description="Tuition coverage details, e.g. '100% full tuition waiver', '50% partial'")
    stipend_amount: str = Field(default="Unknown", description="Living stipend amount")
    stipend_currency: str = Field(default="Unknown", description="Stipend currency (USD, GBP, EUR, etc.)")
    stipend_frequency: str = Field(default="Unknown", description="Payment frequency (Annual, Monthly, Bi-weekly, One-time)")
    amount: str = Field(default="Unknown", description="Combined financial value or stipend")
    currency: str = Field(default="Unknown", description="Currency symbol or 3-letter code")
    funding_duration: str = Field(default="Unknown", description="Duration of funding support, e.g. '4 years guaranteed', '1 year renewable'")
    insurance_and_travel: str = Field(default="None stated", description="Insurance and travel grants, e.g. 'Health insurance covered; $1,500 travel award'")
    other_costs: str = Field(default="Unknown", description="Other costs covered or explicitly excluded")
    obligations: str = Field(default="Unknown", description="Research or teaching obligations, e.g. '20 hrs/week GRA'")
    renewal_conditions: str = Field(default="Unknown", description="Renewal criteria, e.g. 'Maintain 3.5 GPA'")
    application_fee: str = Field(default="None stated", description="Application fee or 'None stated'")
    deadline: str = Field(default="Unknown", description="Application deadline with timezone if stated")
    deadline_date: str = Field(default="Unknown", description="Date-only ISO representation (YYYY-MM-DD) or 'Unknown'")
    opportunity_status: str = Field(default="unknown", description="One of: 'open', 'upcoming', 'closed', 'unknown'")
    application_route: str = Field(default="Unknown", description="Application route: Automatic consideration, Separate application, Nomination")
    official_url: str = Field(default="", description="Official scholarship or application URL")
    eligibility: str = Field(default="Unknown", description="General eligibility summary")
    eligibility_status: str = Field(
        default="Needs clarification",
        description="Candidate eligibility result: 'Appears eligible', 'Appears ineligible', 'Needs clarification'"
    )
    eligibility_explanation: str = Field(default="", description="Explanation comparing profile vs criteria. Preliminary check, not an admission decision.")
    department: str = Field(default="Unknown", description="Administering academic department or University-wide")
    evidence_snippet: str = Field(default="Unknown", description="Verbatim quote from source text supporting the opportunity")
    claims_evidence: Dict[str, str] = Field(default_factory=dict, description="Excerpts mapped to specific claims (tuition, stipend, eligibility, deadline)")
    source_url: str = Field(default="", description="Source page URL where found")
    fit_score: int = Field(default=50, ge=0, le=100, description="Match score for candidate profile (0-100)")
    fit_reason: str = Field(default="", description="Reasoning for fit score")

    @field_validator("title", mode="before")
    @classmethod
    def clean_title(cls, v: Any) -> str:
        if not v or not str(v).strip():
            return "Unknown Scholarship"
        return str(v).strip()

    @field_validator("fit_score", mode="before")
    @classmethod
    def parse_fit_score(cls, v: Any) -> int:
        try:
            val = int(v)
            return max(0, min(100, val))
        except (ValueError, TypeError):
            return 50

class ScholarshipListResponse(BaseModel):
    """Root response for scholarship extraction."""
    scholarships: List[ScholarshipItem] = Field(default_factory=list)

class ProfessorItem(BaseModel):
    """Single faculty member match with explainable rubric, lab affiliation, and strict contact verification."""
    name: str = Field(..., min_length=2, description="Full name of professor or faculty researcher")
    title: str = Field(default="Unknown", description="Academic title: Professor, Associate Professor, Assistant Professor, etc.")
    department: str = Field(default="Unknown", description="Academic department or school")
    university: str = Field(default="Unknown", description="University or institution name")
    lab_group: str = Field(default="Unknown", description="Lab, center, research group, or affiliated institute")
    lab_url: str = Field(default="", description="External or internal URL of the research lab website")
    affiliation_evidence: str = Field(default="None stated in source", description="Evidence excerpt confirming lab/department affiliation")
    official_profile_url: str = Field(default="", description="Official faculty profile or directory entry URL")
    email: str = Field(default="Not found", description="Public professional email address, strictly verified from page source. Never guessed.")
    email_source_url: str = Field(default="", description="Page URL where the public email was observed")
    email_date_observed: str = Field(default="", description="ISO date/timestamp when the email was observed")
    research_interests: str = Field(default="Unknown", description="Specific research areas and focus domains")
    publications_projects: str = Field(default="None stated in source", description="Verified research projects or publications mentioned in sources")
    recruitment_status: str = Field(
        default="Unstated",
        description="Recruitment status: 'Actively recruiting', 'Not accepting students', 'Apply through portal', 'Inquire via email', 'Unstated'"
    )
    recruitment_evidence: str = Field(default="None stated in source", description="Verbatim quote/evidence supporting recruitment status")
    position_funding_type: str = Field(
        default="Unstated",
        description="Funding category: 'Explicit position-tied funding stated', 'Departmental / University funding only', 'Unstated'"
    )
    position_funding_evidence: str = Field(default="None stated in source", description="Verbatim quote supporting position-tied funding")
    contact_instructions: str = Field(
        default="Standard academic inquiry",
        description="Explicit contact instructions (e.g., 'Apply through portal - Do not email directly', 'Email with CV', 'Not accepting students')"
    )
    match_score: int = Field(default=50, ge=0, le=100, description="Heuristic Fit Score (0-100), not an admission probability")
    research_overlap_score: int = Field(default=0, ge=0, le=35, description="Rubric score for research overlap (0-35)")
    experience_fit_score: int = Field(default=0, ge=0, le=25, description="Rubric score for documented experience alignment (0-25)")
    degree_fit_score: int = Field(default=0, ge=0, le=20, description="Rubric score for degree & supervisory fit (0-20)")
    recruitment_fit_score: int = Field(default=0, ge=-20, le=20, description="Rubric score for explicit recruitment evidence (0-20)")
    match_reason: str = Field(default="", description="Summary explanation of heuristic fit")
    match_reasons: List[str] = Field(default_factory=list, description="Specific itemized reasons contributing to match")
    missing_information: List[str] = Field(default_factory=list, description="Checklist of unconfirmed details (e.g., email not found, recruitment unstated)")
    score_breakdown: Dict[str, Any] = Field(default_factory=dict, description="Itemized rubric points breakdown")
    evidence_snippet: str = Field(default="Unknown", description="Verbatim quote from source text supporting the faculty profile")
    source_url: str = Field(default="", description="Source page URL where found")
    is_heuristic_score: bool = Field(default=True, description="Always True: identifies numerical score as a heuristic")

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, v: Any) -> str:
        if not v or not str(v).strip():
            return "Unknown Professor"
        return str(v).strip()

    @field_validator("email", mode="before")
    @classmethod
    def clean_email(cls, v: Any) -> str:
        if not v or str(v).strip().lower() in ("unknown", "none", "n/a", "not found", ""):
            return "Not found"
        clean = str(v).strip()
        if "@" in clean:
            return clean
        return "Not found"

    @field_validator("match_score", mode="before")
    @classmethod
    def parse_match_score(cls, v: Any) -> int:
        try:
            val = int(v)
            return max(0, min(100, val))
        except (ValueError, TypeError):
            return 50

class ProfessorListResponse(BaseModel):
    """Root response for professor matching."""
    professors: List[ProfessorItem] = Field(default_factory=list)

class EmailDraftResponse(BaseModel):
    """Outreach email draft structure."""
    subject: str = Field(..., min_length=5, description="Subject line for email")
    body_text: str = Field(..., min_length=20, description="Complete body text of the outreach email")

    @field_validator("subject", mode="before")
    @classmethod
    def clean_subject(cls, v: Any) -> str:
        return str(v or "Academic Inquiry").strip()

    @field_validator("body_text", mode="before")
    @classmethod
    def clean_body(cls, v: Any) -> str:
        return str(v or "").strip()
