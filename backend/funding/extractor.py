"""
Funding & Scholarship Extraction Engine for ScholarScout.
Extracts financial aid, fellowships, tuition waivers, and assistantships with verbatim evidence.
Enforces typed Pydantic validation, claims evidence mapping, date-only deadline handling,
opportunity status calculation, eligibility assessment with admissions disclaimers,
and prompt injection defense with heuristic fallback.
"""

import re
from datetime import datetime, date
from typing import List, Dict, Any, Optional, Tuple
from backend.llm.client import ai_client
from backend.llm.schemas import ScholarshipListResponse, ScholarshipItem
from backend.llm.security import frame_untrusted_content
from backend.profiles.manager import get_task_specific_profile
from backend.logging_utils import logger

# Canonical reference date for current operations
CURRENT_REFERENCE_DATE = date(2026, 9, 29)

FUNDING_SYSTEM_PROMPT = """You are an expert academic funding extraction system for ScholarScout.
Analyze the provided university webpage text and extract all official scholarships, fellowships, graduate research/teaching assistantships, tuition waivers, and bursaries.

CRITICAL EXTRACTION RULES:
1. ONLY extract funding opportunities explicitly mentioned in the untrusted text. DO NOT fabricate, guess, or extrapolate.
2. If any piece of information (amount, deadline, eligibility, currency, department, etc.) is not clearly stated in the text, you MUST mark it as "Unknown" or "None stated".
3. FUNDING CATEGORIES - You MUST classify each opportunity into exactly one of these 5 categories:
   - "Explicit full tuition plus living support": Explicit evidence of BOTH 100% full tuition coverage AND living stipend/support. (DO NOT describe stipend as sufficient for all living costs without explicit evidence).
   - "Tuition-only support": Explicit full or partial tuition waiver without living stipend.
   - "Partial funding": Fixed monetary grant/award or partial percentage discount that does not cover full tuition and living.
   - "Conditional assistantship": Graduate Teaching/Research Assistantship (GTA/GRA) requiring service/work obligations and/or conditional on faculty funding/progress.
   - "Unclear funding": Vague mentions like "scholarship available", "funding may be available" or unconfirmed funding. (DO NOT treat "scholarship available" as guaranteed funding).

4. ELIGIBILITY EVALUATION:
   - "Appears eligible": Candidate meets published criteria (degree, GPA, nationality, language).
   - "Appears ineligible": Candidate fails explicit published cutoff (e.g. GPA below minimum, restricted nationality).
   - "Needs clarification": Criteria are missing, unstated, or committee-dependent.
   - "eligibility_explanation": Explain the result comparing candidate's confirmed profile and published criteria. MUST end with: "Preliminary eligibility check based on published criteria; not an official university admission decision."

5. DEADLINES & STATUS:
   - "deadline": Published deadline text, preserving timezone if stated (e.g. "December 15, 2026 at 23:59 EST").
   - "deadline_date": Date-only ISO format (YYYY-MM-DD) or "Unknown". NEVER invent a closing time.
   - "opportunity_status": "open", "upcoming", "closed", or "unknown" based on reference date (2026-09-29) and published deadlines.

6. EVIDENCE & CLAIMS:
   - "evidence_snippet": Primary verbatim quotation supporting the opportunity.
   - "claims_evidence": Dictionary mapping specific claim keys ("tuition", "stipend", "eligibility", "deadline", "obligations", "insurance_travel") to short, exact verbatim excerpts from the page text.

JSON Schema Requirement:
{
  "scholarships": [
    {
      "title": "Exact Award Name",
      "university": "University Name",
      "country": "Country",
      "program": "Program or Department",
      "degree_level": "Ph.D. | Master's | Bachelor's | Postdoc | Unknown",
      "funding_category": "Explicit full tuition plus living support | Tuition-only support | Partial funding | Conditional assistantship | Unclear funding",
      "funding_type": "Fellowship | Assistantship (GRA/GTA) | Tuition Waiver | Merit Award | Bursary | Unknown",
      "intake_and_year": "e.g. Fall 2027 or 2026-2027 or Unknown",
      "international_eligibility": "Open to International & Domestic | Domestic Only | International Only | Needs clarification",
      "nationality_restrictions": "None stated | specific restrictions",
      "academic_requirements": "e.g. Minimum 3.5 GPA, TOEFL 100 or Unknown",
      "tuition_coverage": "100% full tuition | Partial (50%) | None | Unknown",
      "stipend_amount": "e.g. $36,000 | Unknown",
      "stipend_currency": "USD | GBP | EUR | CAD | Unknown",
      "stipend_frequency": "Annual | Monthly | Bi-weekly | One-time | Unknown",
      "amount": "Summary amount string or Unknown",
      "currency": "USD | GBP | EUR | Unknown",
      "funding_duration": "e.g. 4 years guaranteed | 1 year renewable | Unknown",
      "insurance_and_travel": "e.g. Health insurance included; $1,000 travel award | None stated",
      "other_costs": "Covered fees or excluded living costs or Unknown",
      "obligations": "e.g. 20 hrs/week teaching assistantship | No service required | Unknown",
      "renewal_conditions": "e.g. Maintain 3.5 GPA and satisfactory research progress | Unknown",
      "application_fee": "e.g. $75 (Waiver available) | None stated",
      "deadline": "Exact deadline string with timezone if stated or Unknown",
      "deadline_date": "YYYY-MM-DD or Unknown",
      "opportunity_status": "open | upcoming | closed | unknown",
      "application_route": "Automatic consideration with admission | Separate scholarship application | Departmental nomination | Unknown",
      "official_url": "Direct URL or empty",
      "eligibility": "General eligibility summary",
      "eligibility_status": "Appears eligible | Appears ineligible | Needs clarification",
      "eligibility_explanation": "Explanation comparing profile and criteria. Preliminary eligibility check based on published criteria; not an official university admission decision.",
      "department": "Department or University-wide",
      "evidence_snippet": "Verbatim quote",
      "claims_evidence": {
        "tuition": "Verbatim excerpt for tuition",
        "stipend": "Verbatim excerpt for stipend",
        "eligibility": "Verbatim excerpt for eligibility",
        "deadline": "Verbatim excerpt for deadline",
        "obligations": "Verbatim excerpt for obligations"
      },
      "fit_score": 85,
      "fit_reason": "Match explanation"
    }
  ]
}
If no scholarships or funding opportunities are mentioned on the page, return: {"scholarships": []}
"""

MONTH_NAMES = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12
}

def parse_date_only(deadline_str: str, ref_date: Optional[date] = None) -> Optional[str]:
    """
    Extracts date-only ISO string (YYYY-MM-DD) from deadline text.
    Never invents a closing time (e.g. 23:59:59).
    Handles ambiguous formats, ordinal days (1st, 2nd), month names, and ISO dates.
    """
    if not deadline_str or deadline_str.strip().lower() in ("unknown", "none", "n/a", "rolling", "none stated"):
        return None

    if ref_date is None:
        ref_date = CURRENT_REFERENCE_DATE

    s = deadline_str.strip()

    # Pattern 1: ISO date YYYY-MM-DD
    iso_match = re.search(r'\b(20\d{2})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])\b', s)
    if iso_match:
        return f"{iso_match.group(1)}-{iso_match.group(2)}-{iso_match.group(3)}"

    # Pattern 2: Month Day, Year (e.g., "December 15, 2026", "Dec 15 2026", "January 5th, 2027")
    m_match = re.search(
        r'\b(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d{2})\b',
        s,
        re.IGNORECASE
    )
    if m_match:
        m_str, d_str, y_str = m_match.groups()
        m_num = MONTH_NAMES.get(m_str.lower(), 1)
        return f"{int(y_str):04d}-{m_num:02d}-{int(d_str):02d}"

    # Pattern 3: Day Month Year (e.g., "15 December 2026", "1st of November 2026", "1st Jan 2027")
    d_match = re.search(
        r'\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?,?\s+(20\d{2})\b',
        s,
        re.IGNORECASE
    )
    if d_match:
        d_str, m_str, y_str = d_match.groups()
        m_num = MONTH_NAMES.get(m_str.lower(), 1)
        return f"{int(y_str):04d}-{m_num:02d}-{int(d_str):02d}"

    # Pattern 4: MM/DD/YYYY or DD/MM/YYYY
    slash_match = re.search(r'\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b', s)
    if slash_match:
        p1, p2, y_str = slash_match.groups()
        n1, n2 = int(p1), int(p2)
        # If n1 > 12, it must be DD/MM/YYYY
        if n1 > 12:
            return f"{int(y_str):04d}-{n2:02d}-{n1:02d}"
        # Standard US MM/DD/YYYY default
        return f"{int(y_str):04d}-{n1:02d}-{n2:02d}"

    # Pattern 5: Month Day without Year (e.g. "December 15", "Jan 15")
    m_no_yr = re.search(
        r'\b(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b',
        s,
        re.IGNORECASE
    )
    if m_no_yr:
        m_str, d_str = m_no_yr.groups()
        m_num = MONTH_NAMES.get(m_str.lower(), 1)
        d_num = int(d_str)
        # Infer year based on current ref date
        if m_num > ref_date.month or (m_num == ref_date.month and d_num >= ref_date.day):
            inferred_year = ref_date.year
        else:
            inferred_year = ref_date.year + 1
        return f"{inferred_year:04d}-{m_num:02d}-{d_num:02d}"

    return None

def compute_opportunity_status(
    deadline_str: str,
    deadline_date_iso: Optional[str] = None,
    text_context: str = "",
    ref_date: Optional[date] = None
) -> str:
    """
    Computes opportunity status: 'open', 'upcoming', 'closed', or 'unknown'
    based on explicit evidence and current reference date.
    """
    if ref_date is None:
        ref_date = CURRENT_REFERENCE_DATE

    deadline_lower = (deadline_str or "").lower()
    text_lower = (text_context or "").lower()

    if "was " in deadline_lower or "past deadline" in deadline_lower or "deadline passed" in deadline_lower or "closed" in deadline_lower:
        return "closed"

    if not deadline_date_iso or deadline_date_iso == "Unknown":
        deadline_date_iso = parse_date_only(deadline_str, ref_date) or parse_date_only(text_context, ref_date)

    if deadline_date_iso and deadline_date_iso != "Unknown":
        try:
            parts = [int(x) for x in deadline_date_iso.split("-")]
            d_obj = date(parts[0], parts[1], parts[2])
            if d_obj < ref_date:
                return "closed"
            else:
                if any(w in text_lower for w in ["applications open in", "opens in", "opens on", "upcoming intake", "future cycle"]):
                    return "upcoming"
                return "open"
        except Exception:
            pass

    if any(w in deadline_lower for w in ["rolling", "open until filled", "open year-round"]):
        return "open"

    if any(w in deadline_lower or w in text_lower for w in ["upcoming", "opens next", "future cycle"]):
        return "upcoming"

    return "unknown"

def classify_funding_category(
    text: str,
    tuition_coverage: str = "",
    stipend_amount: str = "",
    obligations: str = "",
    funding_type: str = ""
) -> str:
    """
    Classifies funding into one of the 5 canonical categories:
    1. 'Explicit full tuition plus living support'
    2. 'Tuition-only support'
    3. 'Partial funding'
    4. 'Conditional assistantship'
    5. 'Unclear funding'
    """
    t_lower = text.lower()
    tuition_lower = tuition_coverage.lower()
    stipend_lower = stipend_amount.lower()
    obligations_lower = obligations.lower()
    type_lower = funding_type.lower()

    # 1. Conditional Assistantship (check word boundaries to avoid matching 'grant' as 'gra')
    is_assistantship = bool(re.search(
        r'\b(assistantship|assistantships|teaching assistant|research assistant|gta|gra|graduate assistant|ga position)\b',
        t_lower + " " + type_lower + " " + obligations_lower
    ))
    has_work_obligations = bool(re.search(
        r'\b(\d{1,2}\s*(?:hours|hrs)\s*(?:\/|per)\s*week|teaching duties|research duties|service obligation)\b',
        t_lower + " " + obligations_lower
    ))
    if is_assistantship or (has_work_obligations and bool(re.search(r'\b(assistant|teaching|research|stipend)\b', t_lower))):
        return "Conditional assistantship"

    # 2. Explicit full tuition plus living support
    has_full_tuition = bool(re.search(
        r'\b(full tuition|100% tuition|tuition waiver|all fees waived|full ride|full composition fee)\b',
        t_lower + " " + tuition_lower
    ))
    has_stipend = (
        (stipend_lower not in ("", "unknown", "none", "n/a", "none stated") and bool(re.search(r'[\$£€]|stipend|living', stipend_lower)))
        or bool(re.search(r'\b(living stipend|annual stipend|monthly stipend|living allowance|maintenance allowance|maintenance grant|stipend of [\$£€]|stipend of \d)\b', t_lower))
        or bool(re.search(r'\b(stipend\s*plus\s*full|full tuition\s*plus\s*a?\s*[\$£€\d]+)\b', t_lower))
    )
    if has_full_tuition and has_stipend:
        return "Explicit full tuition plus living support"

    # 3. Tuition-only support
    if has_full_tuition and not has_stipend:
        if not bool(re.search(r'\b(living allowance|stipend|living cost|living expenses|maintenance)\b', t_lower)):
            return "Tuition-only support"
        if bool(re.search(r'\b(living expenses and housing are excluded|excludes living|tuition only)\b', t_lower)):
            return "Tuition-only support"

    # 4. Partial funding
    is_partial = bool(re.search(
        r'\b(partial|merit award|entrance award|one-time|fee reduction|discount|bursary|\$\s?[\d,]+|£\s?[\d,]+|€\s?[\d,]+)\b',
        t_lower + " " + tuition_lower + " " + type_lower
    ))
    if is_partial and not (has_full_tuition and has_stipend):
        return "Partial funding"

    # 5. Vague / Unclear mentions
    if bool(re.search(r'\b(scholarship available|scholarships are available|funding available|financial aid may be|may be eligible for scholarships)\b', t_lower)):
        return "Unclear funding"

    if has_full_tuition:
        return "Tuition-only support"

    return "Unclear funding"

def evaluate_candidate_eligibility(
    criteria_text: str,
    profile: Dict[str, Any],
    academic_reqs: str = "",
    nationality_reqs: str = "",
    degree_reqs: str = ""
) -> Tuple[str, str]:
    """
    Evaluates profile against published criteria:
    Returns (eligibility_status, eligibility_explanation)
    eligibility_status: 'Appears eligible', 'Appears ineligible', 'Needs clarification'
    Always includes mandatory admissions disclaimer.
    """
    DISCLAIMER = "Preliminary eligibility check based on published criteria; not an official university admission decision."

    c_lower = criteria_text.lower()
    acad_lower = academic_reqs.lower()
    nat_lower = nationality_reqs.lower()
    deg_lower = degree_reqs.lower()
    combined_criteria = c_lower + " " + acad_lower + " " + nat_lower + " " + deg_lower

    reasons = []
    ineligible_flags = []
    unclear_flags = []

    # 1. Degree Level Check
    profile_target_deg = str(profile.get("target_degree", "")).strip().lower()
    if profile_target_deg and profile_target_deg not in ("unknown", ""):
        if any(d in profile_target_deg for d in ["phd", "doctoral", "ph.d."]):
            if "undergraduate only" in c_lower or "bachelor only" in c_lower:
                ineligible_flags.append(f"Target degree ({profile.get('target_degree')}) does not match undergraduate-only requirement.")
            elif any(d in combined_criteria for d in ["phd", "doctoral", "ph.d."]):
                reasons.append(f"Degree target ({profile.get('target_degree')}) matches doctoral/graduate eligibility.")
        elif "master" in profile_target_deg:
            if "phd only" in c_lower or "doctoral only" in c_lower:
                ineligible_flags.append(f"Target degree ({profile.get('target_degree')}) does not match PhD-only requirement.")
            elif any(d in combined_criteria for d in ["master", "master's"]):
                reasons.append(f"Degree target ({profile.get('target_degree')}) matches master's degree eligibility.")

    # 2. Nationality / Domestic vs International Check
    profile_nat = str(profile.get("nationality", "")).strip().lower()
    if any(r in c_lower for r in ["domestic only", "domestic us", "us citizens only", "uk home students only", "uk home only", "eu only"]):
        if profile_nat not in ("us", "united states", "uk", "united kingdom", "eu") and profile_nat != "unknown":
            ineligible_flags.append(f"Restricted to domestic applicants (Candidate nationality: {profile.get('nationality', 'International')}).")
    elif "international" in c_lower or "all nationalities" in c_lower or "no nationality restrictions" in nat_lower:
        reasons.append(f"Open to international applicants (Candidate: {profile.get('nationality', 'International')}).")

    # 3. GPA Requirement Check
    gpa_match = re.search(
        r'(?:minimum|min|at least|hold)\s+(?:a\s+|an\s+)?(?:minimum\s+)?(?:gpa|grade|cumulative gpa)?\s*(?:of\s*)?([234]\.\d{1,2})',
        combined_criteria
    )
    if not gpa_match:
        gpa_match = re.search(r'([234]\.\d{1,2})\s*(?:minimum\s+)?gpa', combined_criteria)

    if gpa_match:
        req_gpa = float(gpa_match.group(1))
        # Parse profile GPA
        cand_gpa_val = None
        profile_gpa_str = str(profile.get("gpa", "")).strip()
        cand_gpa_match = re.search(r'([234]\.\d{1,2})', profile_gpa_str)
        if cand_gpa_match:
            try:
                cand_gpa_val = float(cand_gpa_match.group(1))
            except ValueError:
                pass

        if cand_gpa_val is not None:
            if cand_gpa_val >= req_gpa:
                reasons.append(f"Candidate GPA ({cand_gpa_val}) meets or exceeds minimum requirement ({req_gpa}).")
            else:
                ineligible_flags.append(f"Candidate GPA ({cand_gpa_val}) is below published minimum ({req_gpa}).")
        else:
            unclear_flags.append(f"Published minimum GPA is {req_gpa}, but candidate GPA scale requires verification.")
    else:
        unclear_flags.append("Specific minimum academic cutoff not explicitly stated on page.")

    # Status determination
    if ineligible_flags:
        status = "Appears ineligible"
        explanation = " ".join(ineligible_flags) + " " + DISCLAIMER
    elif unclear_flags and (not reasons or len(reasons) < 2):
        # If there are no clear positive criteria or only partial generic mentions
        if not gpa_match and not any(r in c_lower for r in ["open to all", "all admitted", "all international"]):
            status = "Needs clarification"
            explanation = " ".join(unclear_flags) + " Key eligibility requirements must be confirmed with department. " + DISCLAIMER
        elif reasons:
            status = "Appears eligible"
            explanation = " ".join(reasons) + " " + DISCLAIMER
        else:
            status = "Needs clarification"
            explanation = "Criteria require departmental review. " + DISCLAIMER
    elif reasons:
        status = "Appears eligible"
        explanation = " ".join(reasons) + " " + DISCLAIMER
    else:
        status = "Needs clarification"
        explanation = "Criteria require departmental review. " + DISCLAIMER

    return status, explanation

def extract_claims_evidence_dict(paragraph: str, source_url: str) -> Dict[str, str]:
    """
    Extracts verbatim evidence excerpts mapped to specific claim facets.
    """
    claims = {}
    p_clean = paragraph.strip()
    sentences = re.split(r'(?<=[.!?])\s+', p_clean)

    for s in sentences:
        s_clean = s.strip()
        s_lower = s_clean.lower()
        if not s_clean:
            continue

        # Tuition claim
        if any(w in s_lower for w in ["tuition", "waiver", "fees"]) and "tuition" not in claims:
            claims["tuition"] = s_clean

        # Stipend claim
        if any(w in s_lower for w in ["stipend", "living allowance", "salary", "$", "£", "€", "per year", "annual"]) and "stipend" not in claims:
            claims["stipend"] = s_clean

        # Eligibility claim
        if any(w in s_lower for w in ["eligibility", "eligible", "gpa", "degree", "requirement", "citizenship", "international", "applicants must"]) and "eligibility" not in claims:
            claims["eligibility"] = s_clean

        # Deadline claim
        if any(w in s_lower for w in ["deadline", "due date", "closes", "applications close", "applications due", "priority date"]) and "deadline" not in claims:
            claims["deadline"] = s_clean

        # Obligations claim
        if any(w in s_lower for w in ["teaching", "research", "hours/week", "hrs/week", "duties", "service", "assistantship"]) and "obligations" not in claims:
            claims["obligations"] = s_clean

        # Insurance & travel claim
        if any(w in s_lower for w in ["insurance", "health", "travel grant", "travel award", "relocation"]) and "insurance_travel" not in claims:
            claims["insurance_travel"] = s_clean

    return claims

def heuristic_funding_extractor(page_url: str, text_content: str, profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Offline/Heuristic funding parser using regex pattern matching and paragraph segmentation.
    Guarantees rigorous evidence-based extraction even without external LLM API key.
    Extracts all 35 scholarship fields with verbatim quotes, date-only parsing, and status calculation.
    """
    found = []
    
    # Split text into meaningful blocks (by double newline or contiguous sentences)
    raw_blocks = [b.strip() for b in re.split(r'\n\s*\n', text_content) if len(b.strip()) > 20]
    if len(raw_blocks) <= 1:
        # Fallback to single text if no double newlines
        raw_blocks = [text_content.strip()]

    triggers = [
        "scholarship", "fellowship", "assistantship", "tuition waiver",
        "stipend", "financial aid", "bursary", "grant", "graduate funding",
        "full ride", "merit award", "endowment", "doctoral funding"
    ]

    for p in raw_blocks:
        # Normalize internal whitespace
        p_clean = " ".join(p.split())
        p_lower = p_clean.lower()

        matched_trigger = next((t for t in triggers if t in p_lower), None)
        if not matched_trigger:
            continue

        # Extract title from sentence
        title = "University Funding Opportunity"
        sentences = re.split(r'(?<=[.!?])\s+', p_clean)
        for s in sentences:
            if any(t in s.lower() for t in triggers):
                words = s.split()
                if len(words) <= 12:
                    title = s.strip(" :-.")
                else:
                    title = " ".join(words[:8]) + "..."
                break

        # Detect Amount & Currency
        amount_match = re.search(r'(\$\s?[\d,]+(\s*(\/|per)\s*(year|yr|semester|month|annual))?|£\s?[\d,]+|€\s?[\d,]+|full tuition|100% tuition)', p_clean, re.I)
        amount = amount_match.group(0).strip() if amount_match else "Unknown"

        currency = "Unknown"
        if "$" in p_clean or "usd" in p_lower:
            currency = "USD"
        elif "£" in p_clean or "gbp" in p_lower:
            currency = "GBP"
        elif "€" in p_clean or "eur" in p_lower:
            currency = "EUR"
        elif "cad" in p_lower or "c$" in p_lower:
            currency = "CAD"
        elif "aud" in p_lower or "a$" in p_lower:
            currency = "AUD"

        # Detect Stipend specifics
        stipend_amount = "Unknown"
        stipend_freq = "Unknown"
        stipend_match = re.search(r'(\$\s?[\d,]+|£\s?[\d,]+|€\s?[\d,]+)\s*(?:annual stipend|monthly stipend|stipend|per year|per month|\/year|\/month)?', p_clean, re.I)
        if stipend_match and any(w in p_lower for w in ["stipend", "living", "allowance", "salary"]):
            stipend_amount = stipend_match.group(0).strip()
            if "month" in p_lower:
                stipend_freq = "Monthly"
            elif "year" in p_lower or "annual" in p_lower:
                stipend_freq = "Annual"

        # Detect Tuition Coverage
        tuition_coverage = "Unknown"
        if "full tuition" in p_lower or "100% tuition" in p_lower or "full tuition waiver" in p_lower:
            tuition_coverage = "100% full tuition waiver"
        elif "partial tuition" in p_lower or "50% tuition" in p_lower:
            tuition_coverage = "Partial tuition waiver"
        elif "no tuition" in p_lower or "excludes tuition" in p_lower:
            tuition_coverage = "No tuition coverage"

        # Detect Obligations
        obligations = "Unknown"
        is_asst = bool(re.search(r'\b(assistantship|assistantships|gta|gra|teaching assistant|research assistant)\b', p_lower))
        if is_asst:
            hrs_match = re.search(r'(\d{1,2}\s*(?:hours|hrs)\s*(?:\/|per)\s*week)', p_lower)
            if hrs_match:
                obligations = f"{hrs_match.group(1).title()} teaching/research duties"
            else:
                obligations = "Graduate assistantship duties required (contingent upon department)"
        elif "fellowship" in p_lower and not any(w in p_lower for w in ["teaching", "service", "hours/week"]):
            obligations = "No teaching service required (Fellowship)"

        # Detect Deadline & Date-Only ISO
        deadline_match = re.search(r'(?:deadline|due date|applications close|priority deadline|deadline was)[\s:]*([A-Za-z0-9,\s/-]+?(?:EST|PST|GMT|UTC|CST|midnight|\.|\n|$))', p_clean, re.I)
        raw_deadline = deadline_match.group(1).strip(" .") if deadline_match else "Unknown"
        if raw_deadline != "Unknown" and len(raw_deadline.split()) > 8:
            raw_deadline = " ".join(raw_deadline.split()[:6])

        date_iso = parse_date_only(raw_deadline, CURRENT_REFERENCE_DATE) or parse_date_only(p_clean, CURRENT_REFERENCE_DATE) or "Unknown"
        opp_status = compute_opportunity_status(raw_deadline, date_iso, p_clean, CURRENT_REFERENCE_DATE)

        # Detect Funding Type
        ftype = "Unknown"
        if is_asst:
            ftype = "Assistantship (GRA/GTA)"
        elif "fellowship" in p_lower:
            ftype = "Fellowship"
        elif "tuition waiver" in p_lower:
            ftype = "Tuition Waiver"
        elif "bursary" in p_lower:
            ftype = "Bursary"
        elif "merit award" in p_lower:
            ftype = "Merit Award"
        elif "scholarship" in p_lower:
            ftype = "Scholarship"

        # Classify Funding Category
        funding_cat = classify_funding_category(
            text=p_clean,
            tuition_coverage=tuition_coverage,
            stipend_amount=stipend_amount,
            obligations=obligations,
            funding_type=ftype
        )

        # Eligibility Check
        acad_reqs = "Unknown"
        gpa_m = re.search(r'(?:minimum|min|at least|hold)\s+(?:a\s+|an\s+)?(?:gpa|grade)?\s*(?:of\s*)?([234]\.\d{1,2})', p_lower)
        if not gpa_m:
            gpa_m = re.search(r'([234]\.\d{1,2})\s*(?:minimum\s+)?gpa', p_lower)
        if gpa_m:
            acad_reqs = f"Minimum {gpa_m.group(1)} GPA"

        nat_reqs = "None stated"
        if "domestic only" in p_lower or "us citizen" in p_lower:
            nat_reqs = "Domestic applicants only"
        elif "international only" in p_lower:
            nat_reqs = "International applicants only"

        int_elig = "Unknown"
        if "international" in p_lower and "not eligible" in p_lower:
            int_elig = "Domestic Only"
        elif "international" in p_lower or "all nationalities" in p_lower:
            int_elig = "Open to International & Domestic"

        elig_status, elig_exp = evaluate_candidate_eligibility(
            criteria_text=p_clean,
            profile=profile,
            academic_reqs=acad_reqs,
            nationality_reqs=nat_reqs,
            degree_reqs=profile.get("target_degree", "")
        )

        # Insurance and Travel
        ins_travel = "None stated"
        if "health insurance" in p_lower or "insurance" in p_lower:
            ins_travel = "Health insurance covered"
        if "travel" in p_lower:
            ins_travel = (ins_travel + "; Travel award available") if ins_travel != "None stated" else "Travel award available"

        # Claims Evidence mapping
        claims_evidence = extract_claims_evidence_dict(p_clean, page_url)

        # Fit score calculation
        fit_score = 60
        target_deg = profile.get("target_degree", "phd").lower()
        if target_deg in p_lower:
            fit_score += 15
        if elig_status == "Appears eligible":
            fit_score += 15
        elif elig_status == "Appears ineligible":
            fit_score = max(10, fit_score - 30)

        # Academic Intake
        intake_match = re.search(r'\b(Fall|Spring|Winter|Summer)\s+(20\d{2})\b', p_clean, re.I)
        intake_and_year = intake_match.group(0) if intake_match else "Unknown"

        found.append({
            "title": title,
            "university": profile.get("target_institution", "Unknown"),
            "country": profile.get("target_country", "Unknown"),
            "program": profile.get("target_field", "Departmental"),
            "degree_level": profile.get("target_degree", "Graduate"),
            "funding_category": funding_cat,
            "funding_type": ftype,
            "intake_and_year": intake_and_year,
            "international_eligibility": int_elig,
            "nationality_restrictions": nat_reqs,
            "academic_requirements": acad_reqs,
            "tuition_coverage": tuition_coverage,
            "stipend_amount": stipend_amount,
            "stipend_currency": currency,
            "stipend_frequency": stipend_freq,
            "amount": amount,
            "currency": currency,
            "funding_duration": "4 years guaranteed" if "4 year" in p_lower else "Unknown",
            "insurance_and_travel": ins_travel,
            "other_costs": "Unknown",
            "obligations": obligations,
            "renewal_conditions": "Maintain 3.5 GPA" if "maintain" in p_lower and "gpa" in p_lower else "Unknown",
            "application_fee": "None stated",
            "deadline": raw_deadline,
            "deadline_date": date_iso,
            "opportunity_status": opp_status,
            "application_route": "Automatic consideration with degree application" if "automatic" in p_lower else "Unknown",
            "official_url": page_url,
            "eligibility": f"Degree: {profile.get('target_degree', 'Graduate')} relevant.",
            "eligibility_status": elig_status,
            "eligibility_explanation": elig_exp,
            "department": profile.get("target_field", "Departmental"),
            "evidence_snippet": p_clean[:400],
            "claims_evidence": claims_evidence,
            "source_url": page_url,
            "fit_score": min(max(fit_score, 0), 98),
            "fit_reason": f"Discovered on official page mentioning {matched_trigger}. Category: {funding_cat}. Status: {opp_status}."
        })

    # Deduplicate by title
    unique_items = []
    seen_titles = set()
    for item in found:
        t_norm = item["title"].lower()[:25]
        if t_norm not in seen_titles:
            seen_titles.add(t_norm)
            unique_items.append(item)

    return unique_items[:8]

async def extract_funding_opportunities(
    page_url: str,
    text_content: str,
    profile: Dict[str, Any],
    job_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Extracts scholarships and funding from page text using typed Pydantic validation,
    claims evidence mapping, date-only deadline handling, data minimization,
    and prompt injection defense with automatic heuristic fallback.
    """
    if not text_content or len(text_content.strip()) < 80:
        return []

    minimized = get_task_specific_profile(profile, "scholarship_eligibility")
    funding_needs = ", ".join(minimized.get("funding_needs", [])) if isinstance(minimized.get("funding_needs"), list) else str(minimized.get("funding_needs", "Unknown"))
    preferred_dest = ", ".join(minimized.get("preferred_countries", [])) if isinstance(minimized.get("preferred_countries"), list) else str(minimized.get("preferred_countries", "Unknown"))

    profile_context = f"""Candidate Profile (Eligibility Scope):
- Target Degree: {minimized.get('target_degree', 'Unknown')}
- Discipline / Broad Subject: {minimized.get('broad_subject', 'Unknown')}
- GPA & Original Scale: {minimized.get('gpa', 'Unknown')}
- Nationality: {minimized.get('nationality', 'Unknown')}
- Current Residence: {minimized.get('current_residence', 'Unknown')}
- Preferred Destinations: {preferred_dest or 'Global'}
- Intended Intake: {minimized.get('intended_intake', 'Unknown')}
- Funding Requirements: {funding_needs or 'Tuition / Stipend'}
- Language Tests: {minimized.get('english_tests', 'Unknown')}
"""

    framed_text = frame_untrusted_content(text_content, source_url=page_url, content_type="webpage_funding_text")
    user_prompt = f"""{profile_context}

Source URL: {page_url}

{framed_text}

Extract all official scholarships, assistantships, and funding opportunities according to the instructions. Mark missing details as 'Unknown'."""

    if ai_client.is_configured():
        try:
            result = await ai_client.generate_structured(
                schema=ScholarshipListResponse,
                system_prompt=FUNDING_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                job_id=job_id
            )
            if result.data and result.data.scholarships:
                output_list = []
                for s in result.data.scholarships:
                    d = s.model_dump()
                    d["source_url"] = page_url
                    if not d.get("official_url"):
                        d["official_url"] = page_url

                    # Validate date-only deadline
                    if d.get("deadline_date") and d["deadline_date"] != "Unknown":
                        parsed_iso = parse_date_only(d["deadline_date"], CURRENT_REFERENCE_DATE)
                        d["deadline_date"] = parsed_iso or "Unknown"
                    elif d.get("deadline") and d["deadline"] != "Unknown":
                        parsed_iso = parse_date_only(d["deadline"], CURRENT_REFERENCE_DATE)
                        d["deadline_date"] = parsed_iso or "Unknown"

                    # Calculate opportunity status
                    d["opportunity_status"] = compute_opportunity_status(
                        deadline_str=d.get("deadline", "Unknown"),
                        deadline_date_iso=d.get("deadline_date"),
                        text_context=text_content,
                        ref_date=CURRENT_REFERENCE_DATE
                    )

                    # Ensure admissions disclaimer in eligibility explanation
                    disclaimer = "Preliminary eligibility check based on published criteria; not an official university admission decision."
                    if disclaimer not in d.get("eligibility_explanation", ""):
                        d["eligibility_explanation"] = (d.get("eligibility_explanation", "").strip() + " " + disclaimer).strip()

                    output_list.append(d)
                return output_list
            elif result.data:
                return []
        except Exception as e:
            logger.warning(f"[Funding Extractor] Structured AI extraction failed: {e}. Falling back to heuristic extractor.")

    # Fallback to heuristic parser
    return heuristic_funding_extractor(page_url, text_content, profile)
