"""
Academic Profiles Manager for ScholarScout.
Handles complete academic profile persistence, versioning, data minimization,
incomplete profile tolerance, and a structured profile-completeness checklist.
"""

import json
from typing import Dict, Any, List, Optional, Union
from pydantic import BaseModel, Field, field_validator
from backend.database import (
    get_active_profile,
    get_all_profiles,
    get_profile_by_id,
    save_profile,
    get_profile_versions,
    get_profile_version
)

class AcademicProfileSchema(BaseModel):
    """
    Comprehensive academic profile for scholarship finding and professor matching.
    Allows incomplete profiles while strictly preserving original values.
    """
    id: Optional[int] = None
    full_name: str = Field(..., description="Student full name")
    name: Optional[str] = None  # Alias for backward compatibility
    nationality: str = Field("Unknown", description="Citizenship or nationality status")
    country_of_origin: Optional[str] = None  # Alias
    current_residence: str = Field("Unknown", description="Current country of residence")

    # Current Education
    current_degree: str = Field("Unknown", description="Current or most recent degree (e.g. B.S. in Computer Science)")
    current_institution: str = Field("Unknown", description="Current or completed university")
    current_major: Optional[str] = Field("Computer Science", description="Current major")
    gpa: str = Field("Unknown", description="Original GPA with scale preserved (e.g. 3.92 / 4.0, 8.8 / 10.0, First Class)")
    graduation_date: str = Field("Unknown", description="Graduation or expected graduation date (e.g. May 2025)")

    # Target Studies
    target_degree: str = Field("Ph.D.", description="Target degree (e.g. Ph.D., Master's, Postdoc)")
    broad_subject: str = Field("Computer Science", description="Broad discipline / major")
    target_field: Optional[str] = None  # Alias
    specific_interests: str = Field("", description="Specific research focus, topics, and keywords")
    research_interests: Optional[str] = None  # Alias
    intended_intake: str = Field("Unknown", description="Target start semester and year (e.g. Fall 2025)")

    # Country Preferences
    preferred_countries: Union[List[str], str] = Field(default_factory=list, description="Target study destinations")
    excluded_countries: Union[List[str], str] = Field(default_factory=list, description="Excluded countries")

    # Language Proficiency
    english_tests: str = Field("Unknown", description="English test scores (e.g. TOEFL 110, IELTS 8.0, English Medium)")

    # Experience & Skills
    projects: str = Field("", description="Key academic or industry projects")
    publications: str = Field("", description="Papers, preprints, conference proceedings")
    research_experience: str = Field("", description="Research assistantships or lab background")
    technical_skills: str = Field("", description="Technical stack, languages, tools")
    background_summary: Optional[str] = Field("", description="Holistic academic summary")

    # Funding Needs
    funding_needs: Union[List[str], str] = Field(
        default_factory=lambda: ["full_tuition", "living_stipend"],
        description="Required funding components (e.g. tuition, stipend, health insurance, travel)"
    )
    funding_notes: str = Field("", description="Specific financial constraints or requirements")

    # Links
    portfolio_url: str = Field("", description="Portfolio / project showcase URL")
    github_url: str = Field("", description="GitHub profile URL")
    website_url: str = Field("", description="Personal website or LinkedIn URL")

    # Metadata
    version: int = Field(1, description="Profile version number")
    is_active: bool = Field(True, description="Whether this profile is currently active")

    @field_validator("full_name", mode="before")
    @classmethod
    def resolve_name(cls, v: Any, values: Any) -> str:
        if v and str(v).strip():
            return str(v).strip()
        return "Prospective Student"

    @field_validator("preferred_countries", "excluded_countries", "funding_needs", mode="before")
    @classmethod
    def parse_list_fields(cls, v: Any) -> List[str]:
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, list):
                        return [str(x).strip() for x in parsed if str(x).strip()]
                except Exception:
                    pass
            return [x.strip() for x in v.split(",") if x.strip()]
        return []

def calculate_completeness(profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculates the profile completeness score (0-100%) and returns an actionable checklist.
    Evaluates across key pillars: Identity, Education, Research, Language, Skills & Funding.
    """
    checklist = []
    total_weight = 0
    earned_weight = 0

    def check_field(field_name: str, label: str, weight: int, category: str, custom_check=None):
        nonlocal total_weight, earned_weight
        total_weight += weight
        val = profile.get(field_name)
        if custom_check:
            is_complete = custom_check(val)
        else:
            is_complete = bool(val and str(val).strip() and str(val).lower() != "unknown" and val != "[]" and val != [])
        
        if is_complete:
            earned_weight += weight
        checklist.append({
            "field": field_name,
            "label": label,
            "category": category,
            "weight": weight,
            "is_complete": is_complete
        })

    # Pillar 1: Identity & Residence (15%)
    check_field("name", "Full Name", 5, "Identity", lambda v: bool(v and str(v).strip() and str(v) != "Prospective Student"))
    check_field("nationality", "Nationality / Citizenship", 5, "Identity")
    check_field("current_residence", "Current Country of Residence", 5, "Identity")

    # Pillar 2: Current Education & GPA (20%)
    check_field("current_degree", "Current Degree", 5, "Education")
    check_field("current_institution", "Current / Past Institution", 5, "Education")
    check_field("gpa", "GPA & Original Grading Scale", 5, "Education")
    check_field("graduation_date", "Graduation / Expected Date", 5, "Education")

    # Pillar 3: Target Studies & Research Focus (25%)
    check_field("target_degree", "Target Degree (e.g. Ph.D., Master's)", 10, "Target Studies")
    check_field("target_field", "Broad Subject / Department", 5, "Target Studies")
    check_field("research_interests", "Specific Research Interests", 10, "Target Studies")

    # Pillar 4: Experience, Skills & Publications (15%)
    check_field("technical_skills", "Technical Skills & Tools", 5, "Experience")
    check_field("research_experience", "Research Experience or Lab Work", 5, "Experience")
    check_field("background_summary", "Academic Background Summary", 5, "Experience")

    # Pillar 5: Funding & Location Preferences (15%)
    check_field("funding_needs", "Funding Requirements (Tuition, Stipend, etc.)", 5, "Preferences", lambda v: bool(v and (isinstance(v, list) and len(v) > 0 or isinstance(v, str) and v != "[]" and v.strip())))
    check_field("preferred_countries", "Preferred Study Destinations", 5, "Preferences", lambda v: bool(v and (isinstance(v, list) and len(v) > 0 or isinstance(v, str) and v != "[]" and v.strip())))
    check_field("intended_intake", "Intended Intake (e.g. Fall 2025)", 5, "Preferences")

    # Pillar 6: Links & Language (10%)
    check_field("english_tests", "English Language Tests (TOEFL, IELTS, or Waiver)", 5, "Language & Links")
    check_field("github_url", "GitHub / Portfolio / Website Link", 5, "Language & Links", lambda v: bool(profile.get("github_url") or profile.get("portfolio_url") or profile.get("website_url")))

    score = int((earned_weight / max(total_weight, 1)) * 100)

    if score >= 85:
        tier = "Comprehensive (Ready for High-Accuracy Matching)"
        tier_class = "high"
    elif score >= 60:
        tier = "Good (Adequate for Basic Discovery)"
        tier_class = "med"
    else:
        tier = "Incomplete (Add more details for accurate matching)"
        tier_class = "low"

    completed_count = sum(1 for item in checklist if item["is_complete"])
    missing_items = [item["label"] for item in checklist if not item["is_complete"]]

    return {
        "score": score,
        "tier": tier,
        "tier_class": tier_class,
        "completed_count": completed_count,
        "total_items": len(checklist),
        "checklist": checklist,
        "missing_items": missing_items
    }

def get_task_specific_profile(profile: Dict[str, Any], task_type: str) -> Dict[str, Any]:
    """
    Data minimization utility: Returns only the profile fields strictly needed
    for a specific AI reasoning task to protect privacy and optimize token usage.
    """
    if task_type == "scholarship_eligibility":
        # Sent for funding extraction and eligibility analysis
        return {
            "target_degree": profile.get("target_degree", "Unknown"),
            "broad_subject": profile.get("broad_subject") or profile.get("target_field", "Unknown"),
            "gpa": profile.get("gpa", "Unknown"),
            "nationality": profile.get("nationality") or profile.get("country_of_origin", "Unknown"),
            "current_residence": profile.get("current_residence", "Unknown"),
            "preferred_countries": profile.get("preferred_countries", []),
            "intended_intake": profile.get("intended_intake", "Unknown"),
            "funding_needs": profile.get("funding_needs", []),
            "english_tests": profile.get("english_tests", "Unknown"),
            "background_summary": profile.get("background_summary", "")
        }
    elif task_type == "professor_matching":
        # Sent for faculty research alignment
        return {
            "name": profile.get("name", "Applicant"),
            "target_degree": profile.get("target_degree", "Ph.D."),
            "target_field": profile.get("broad_subject") or profile.get("target_field", "Computer Science"),
            "research_interests": profile.get("specific_interests") or profile.get("research_interests", ""),
            "technical_skills": profile.get("technical_skills", ""),
            "publications": profile.get("publications", ""),
            "projects": profile.get("projects", ""),
            "research_experience": profile.get("research_experience", ""),
            "github_url": profile.get("github_url", ""),
            "portfolio_url": profile.get("portfolio_url", "")
        }
    elif task_type == "email_drafting":
        # Sent for personalized outreach email synthesis
        return {
            "name": profile.get("name", "Applicant"),
            "target_degree": profile.get("target_degree", "Ph.D."),
            "current_major": profile.get("current_major") or profile.get("broad_subject", "Computer Science"),
            "target_field": profile.get("target_field") or profile.get("broad_subject", "Computer Science"),
            "research_interests": profile.get("specific_interests") or profile.get("research_interests", ""),
            "background_summary": profile.get("background_summary", ""),
            "publications": profile.get("publications", ""),
            "portfolio_url": profile.get("portfolio_url") or profile.get("github_url", "")
        }
    return profile

def get_current_profile() -> Dict[str, Any]:
    """Retrieves current active profile with calculated completeness and field aliases."""
    profile = get_active_profile()
    if not profile:
        profiles = get_all_profiles()
        if profiles:
            profile = profiles[0]

    if not profile:
        # Default starter template
        profile = {
            "id": 1,
            "name": "Alex Rivera",
            "full_name": "Alex Rivera",
            "nationality": "International",
            "country_of_origin": "International",
            "current_residence": "Germany",
            "current_degree": "B.S. in Computer Science",
            "current_institution": "Technical University of Munich",
            "current_major": "Computer Science",
            "gpa": "3.92 / 4.0",
            "graduation_date": "June 2025",
            "target_degree": "Ph.D.",
            "broad_subject": "Computer Science",
            "target_field": "Artificial Intelligence",
            "specific_interests": "Large Language Models, Multi-Agent Systems, Neural Reasoning",
            "research_interests": "Large Language Models, Multi-Agent Systems, Neural Reasoning",
            "preferred_countries": ["United States", "United Kingdom", "Canada", "Germany"],
            "excluded_countries": [],
            "intended_intake": "Fall 2025",
            "english_tests": "TOEFL iBT 112 (R:30, L:29, S:26, W:27)",
            "projects": "ScholarScout Autonomous Research Agent, LLM Benchmark Suite",
            "publications": "1 workshop paper at NeurIPS LLM Agent Evaluation Workshop",
            "research_experience": "Undergraduate Research Assistant in NLP Laboratory (2 years)",
            "technical_skills": "Python, PyTorch, C++, CUDA, Transformers, FastMCP",
            "background_summary": "B.S. in Computer Science. Strong background in deep learning architectures and NLP research.",
            "funding_needs": ["full_tuition", "living_stipend", "health_insurance"],
            "funding_notes": "Seeking fully-funded graduate research assistantship (GRA/GTA) or fellowship.",
            "portfolio_url": "https://alexrivera.dev",
            "github_url": "https://github.com/alexrivera-research",
            "website_url": "https://alexrivera.dev",
            "version": 1,
            "is_active": 1
        }
        # Save initial profile
        save_profile(profile)

    # Normalize JSON list fields
    for list_field in ["preferred_countries", "excluded_countries", "funding_needs"]:
        if isinstance(profile.get(list_field), str):
            try:
                profile[list_field] = json.loads(profile[list_field])
            except Exception:
                profile[list_field] = [x.strip() for x in profile[list_field].split(",") if x.strip()]

    profile["completeness"] = calculate_completeness(profile)
    return profile

def update_or_create_profile(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validates, versions, and persists student academic profile to SQLite."""
    # Synchronize alias fields
    name = data.get("full_name") or data.get("name") or "Prospective Student"
    data["name"] = name.strip()
    data["full_name"] = name.strip()

    if data.get("nationality"):
        data["country_of_origin"] = data["nationality"]
    elif data.get("country_of_origin"):
        data["nationality"] = data["country_of_origin"]

    if data.get("broad_subject"):
        data["target_field"] = data["broad_subject"]
        data["current_major"] = data["broad_subject"]
    elif data.get("target_field"):
        data["broad_subject"] = data["target_field"]

    if data.get("specific_interests"):
        data["research_interests"] = data["specific_interests"]
    elif data.get("research_interests"):
        data["specific_interests"] = data["research_interests"]

    # Convert list fields to JSON strings for SQLite storage
    for list_field in ["preferred_countries", "excluded_countries", "funding_needs"]:
        val = data.get(list_field)
        if isinstance(val, list):
            data[list_field] = json.dumps(val)
        elif isinstance(val, str) and not (val.startswith("[") and val.endswith("]")):
            items = [x.strip() for x in val.split(",") if x.strip()]
            data[list_field] = json.dumps(items)

    profile_id = save_profile(data)
    saved = get_profile_by_id(profile_id)
    if saved:
        for list_field in ["preferred_countries", "excluded_countries", "funding_needs"]:
            if isinstance(saved.get(list_field), str):
                try:
                    saved[list_field] = json.loads(saved[list_field])
                except Exception:
                    saved[list_field] = []
        saved["completeness"] = calculate_completeness(saved)
        return saved

    return {"id": profile_id, "name": name}

def get_profile_history(profile_id: int) -> List[Dict[str, Any]]:
    """Returns chronological audit snapshots of the profile versions."""
    versions = get_profile_versions(profile_id)
    results = []
    for v in versions:
        snap = json.loads(v["snapshot_json"]) if isinstance(v.get("snapshot_json"), str) else v.get("snapshot_json", {})
        results.append({
            "version": v["version"],
            "created_at": v["created_at"],
            "snapshot": snap
        })
    return results
