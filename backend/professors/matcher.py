"""
Professor Research Matcher, Lab Discovery & Faculty Extractor for ScholarScout.
Identifies faculty members, research domains, verified public professional emails,
lab affiliations, recruitment status, position-tied funding, and computes an explainable
4-part heuristic fit rubric with explicit reasons and missing information.
"""

import re
import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse

from backend.llm.client import ai_client
from backend.llm.schemas import ProfessorListResponse, ProfessorItem
from backend.llm.security import frame_untrusted_content
from backend.logging_utils import logger
from backend.profiles.manager import get_task_specific_profile

PROFESSOR_SYSTEM_PROMPT = """You are an academic faculty analysis expert for ScholarScout.
Analyze the provided university/department/lab page text and identify faculty members, principal investigators, and researchers.

CRITICAL DISCOVERY & COMPLIANCE RULES:
1. ONLY extract professors explicitly mentioned in the source text.
2. PUBLIC PROFESSIONAL CONTACTS ONLY:
   - ONLY extract an email if it is explicitly listed on the page.
   - NEVER guess or construct an email address from name conventions (e.g., first.last@uni.edu).
   - If no email is explicitly stated, you MUST set email to "Not found".
3. LAB AFFILIATIONS & EXTERNAL SITES:
   - If a professor is affiliated with a lab, group, or center, extract the lab name and any linked lab URL.
   - Provide an "affiliation_evidence" quote establishing the relationship.
4. RECRUITMENT STATUS & CONTACT INSTRUCTIONS:
   - Classify recruitment_status into one of: 'Actively recruiting', 'Not accepting students', 'Apply through portal', 'Inquire via email', 'Unstated'.
   - Extract explicit contact_instructions (e.g., 'Apply through portal - Do not email directly', 'Email with CV and transcripts', 'Not accepting students').
   - Provide "recruitment_evidence" with a verbatim quote.
5. SEPARATE FUNDING SCOPES:
   - Strictly distinguish position-tied funding (lab grant/GRA) from university-wide funding.
   - position_funding_type: 'Explicit position-tied funding stated', 'Departmental / University funding only', 'Unstated'.
   - Provide "position_funding_evidence" quote.
6. PROJECTS & PUBLICATIONS:
   - Extract specific mentioned papers/projects supported by the text, or set to 'None stated in source'.
7. VERBATIM EVIDENCE:
   - Provide exact evidence_snippet quote from the page.

Return structured JSON adhering strictly to the schema."""

# Common academic recruitment phrases
RECRUITMENT_KEYWORDS = {
    "actively_recruiting": [
        "actively looking for", "seeking phd students", "looking for motivated",
        "openings for graduate", "phd positions available", "we are recruiting",
        "accepting new graduate students", "positions in my lab", "open positions for",
        "join our lab", "looking for research assistants"
    ],
    "apply_portal": [
        "apply through the portal", "apply online via", "do not email directly regarding admissions",
        "submit application through", "admissions are handled centrally", "please do not send email inquiry",
        "apply directly to the department"
    ],
    "not_accepting": [
        "not accepting students", "not taking new students", "no open positions",
        "group is currently full", "on sabbatical - not accepting", "not taking graduate students this cycle"
    ],
    "inquire_email": [
        "prospective students should email", "send your cv and", "inquire with cv",
        "email me if you are interested", "contact me with subject"
    ]
}

# Position-tied funding phrases vs departmental funding
POSITION_FUNDING_KEYWORDS = [
    "funded gra position", "funded ra position", "nsf funded", "nih funded",
    "grant funded", "research assistantship available", "stipend and tuition covered by grant",
    "funded project", "fully funded phd position"
]

DEPARTMENT_FUNDING_KEYWORDS = [
    "departmental fellowship", "university fellowship", "graduate school funding",
    "teaching assistantship through department", "central scholarship", "ta/ra support available"
]


def extract_contact_instructions_and_recruitment(text: str) -> Tuple[str, str, str]:
    """
    Extracts recruitment status, contact instructions, and verbatim evidence quote.
    Returns: (recruitment_status, contact_instructions, recruitment_evidence)
    """
    text_lower = text.lower()
    
    # 1. Check for "Not accepting" first (safety priority)
    for kw in RECRUITMENT_KEYWORDS["not_accepting"]:
        if kw in text_lower:
            start_pos = text_lower.find(kw)
            excerpt = text[max(0, start_pos - 20):min(len(text), start_pos + 150)].strip()
            return "Not accepting students", "Not accepting students this cycle", f'"{excerpt}"'

    # 2. Check for "Apply through portal / Do not email"
    for kw in RECRUITMENT_KEYWORDS["apply_portal"]:
        if kw in text_lower:
            start_pos = text_lower.find(kw)
            excerpt = text[max(0, start_pos - 20):min(len(text), start_pos + 150)].strip()
            return "Apply through portal", "Apply through portal - Do not email directly", f'"{excerpt}"'

    # 3. Check for "Actively recruiting"
    for kw in RECRUITMENT_KEYWORDS["actively_recruiting"]:
        if kw in text_lower:
            start_pos = text_lower.find(kw)
            excerpt = text[max(0, start_pos - 20):min(len(text), start_pos + 150)].strip()
            return "Actively recruiting", "Actively recruiting - Email with CV & research interests", f'"{excerpt}"'

    # 4. Check for "Inquire via email"
    for kw in RECRUITMENT_KEYWORDS["inquire_email"]:
        if kw in text_lower:
            start_pos = text_lower.find(kw)
            excerpt = text[max(0, start_pos - 20):min(len(text), start_pos + 150)].strip()
            return "Inquire via email", "Inquire via email with CV and statement", f'"{excerpt}"'

    return "Unstated", "Standard academic inquiry", "None stated in source"


def extract_funding_separation(text: str) -> Tuple[str, str]:
    """
    Strictly separates position-tied funding from general university funding.
    Returns: (position_funding_type, position_funding_evidence)
    """
    text_lower = text.lower()

    for kw in POSITION_FUNDING_KEYWORDS:
        if kw in text_lower:
            start_pos = text_lower.find(kw)
            excerpt = text[max(0, start_pos - 20):min(len(text), start_pos + 160)].strip()
            return "Explicit position-tied funding stated", f'"{excerpt}"'

    for kw in DEPARTMENT_FUNDING_KEYWORDS:
        if kw in text_lower:
            start_pos = text_lower.find(kw)
            excerpt = text[max(0, start_pos - 20):min(len(text), start_pos + 160)].strip()
            return "Departmental / University funding only", f'"{excerpt}"'

    return "Unstated", "None stated in source"


def compute_explainable_rubric(
    prof: Dict[str, Any],
    profile: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Computes an explainable 4-part rubric:
    1. Research Overlap (0-35)
    2. Documented Experience Alignment (0-25)
    3. Degree & Supervisory Fit (0-20)
    4. Explicit Recruitment Evidence (0-20, with penalties for closed recruitment)

    Total Heuristic Fit Score: 0-100 (explicitly marked as a heuristic, not admission probability).
    Returns rich dictionary with score_breakdown, match_reasons, and missing_information.
    """
    candidate_interests = [
        k.strip().lower() for k in (
            profile.get("specific_interests") or profile.get("research_interests") or ""
        ).split(",") if k.strip()
    ]
    target_field = (profile.get("target_field") or profile.get("broad_subject") or "Computer Science").lower()
    technical_skills = [s.strip().lower() for s in profile.get("technical_skills", "").split(",") if s.strip()]
    projects_exp = f"{profile.get('projects', '')} {profile.get('research_experience', '')}".strip().lower()
    publications = (profile.get("publications") or "").strip().lower()
    target_degree = (profile.get("target_degree") or "Ph.D.").strip().lower()

    prof_text = (
        f"{prof.get('name', '')} {prof.get('title', '')} {prof.get('department', '')} "
        f"{prof.get('lab_group', '')} {prof.get('research_interests', '')} "
        f"{prof.get('publications_projects', '')} {prof.get('evidence_snippet', '')}"
    ).lower()

    match_reasons: List[str] = []
    missing_info: List[str] = []

    # --- 1. Research Overlap (0 to 35 pts) ---
    research_overlap_score = 10  # Baseline for discipline
    matched_interests = []
    for interest in candidate_interests:
        if interest in prof_text or any(w in prof_text for w in interest.split() if len(w) > 3):
            matched_interests.append(interest)
            research_overlap_score += 10

    if target_field in prof_text:
        research_overlap_score += 5
        matched_interests.append(target_field)

    research_overlap_score = min(35, max(0, research_overlap_score))
    if matched_interests:
        unique_matched = list(dict.fromkeys(matched_interests))
        match_reasons.append(f"Strong research topic overlap in: {', '.join(unique_matched[:3])}")
    else:
        missing_info.append("Limited direct overlap with specific research interest keywords")

    # --- 2. Documented Experience Alignment (0 to 25 pts) ---
    if not technical_skills and not projects_exp and not publications:
        # Minimal profile without specified skills/projects -> infer from research overlap
        experience_fit_score = 15 if matched_interests else 10
    else:
        experience_fit_score = 5
        matched_skills = []
        for skill in technical_skills:
            if skill and skill in prof_text:
                matched_skills.append(skill)
                experience_fit_score += 5

        # Check publication / project methods overlap
        if "agent" in prof_text and ("agent" in projects_exp or "agent" in publications):
            experience_fit_score += 5
            matched_skills.append("Agentic Systems")
        if "llm" in prof_text and ("llm" in projects_exp or "llm" in publications):
            experience_fit_score += 5
            matched_skills.append("LLM architectures")

        experience_fit_score = min(25, max(0, experience_fit_score))
        if matched_skills:
            match_reasons.append(f"Documented technical skills & project alignment: {', '.join(list(dict.fromkeys(matched_skills))[:3])}")
        else:
            missing_info.append("Candidate projects/publications not explicitly referenced on faculty page")

    # --- 3. Degree & Supervisory Fit (0 to 20 pts) ---
    degree_fit_score = 10
    title_lower = (prof.get("title") or "").lower()
    if any(t in title_lower for t in ["professor", "chair", "director", "pi"]):
        degree_fit_score = 20
        match_reasons.append(f"Academic title ({prof.get('title', 'Professor')}) indicates graduate supervisory capacity for {target_degree.upper()}")
    elif "assistant" in title_lower or "associate" in title_lower:
        degree_fit_score = 18
        match_reasons.append(f"Faculty member ({prof.get('title')}) capable of advising {target_degree.upper()} candidates")
    else:
        degree_fit_score = 12

    # --- 4. Explicit Recruitment Evidence (0 to 20 pts) ---
    recruitment_status = prof.get("recruitment_status", "Unstated")
    recruitment_fit_score = 5

    if recruitment_status == "Actively recruiting":
        recruitment_fit_score = 20
        match_reasons.append("Explicit evidence of active graduate student recruitment on profile")
    elif recruitment_status == "Inquire via email":
        recruitment_fit_score = 16
        match_reasons.append("Explicit invitation for prospective student email inquiries")
    elif recruitment_status == "Apply through portal":
        recruitment_fit_score = 12
        match_reasons.append("Official application portal route specified by faculty member")
    elif recruitment_status == "Not accepting students":
        recruitment_fit_score = -20
        missing_info.append("Faculty explicitly stated: Not accepting new students this cycle")
    else:
        recruitment_fit_score = 5
        missing_info.append("Explicit student recruitment status not stated on profile")

    # --- Missing Information Checklist ---
    email_val = prof.get("email", "")
    if not email_val or email_val.lower() in ("unknown", "none", "not found", ""):
        missing_info.append("Public professional email not found on source page")

    if prof.get("position_funding_type") == "Unstated":
        missing_info.append("Lab-specific position funding not verified in source text")

    if prof.get("publications_projects") in ("None stated in source", "Unknown", ""):
        missing_info.append("Specific recent publications or projects not listed on this page")

    if not prof.get("lab_url"):
        missing_info.append("Official lab website URL not linked on profile")

    # Calculate Total Heuristic Score
    raw_total = research_overlap_score + experience_fit_score + degree_fit_score + recruitment_fit_score
    total_score = max(0, min(100, raw_total))

    score_breakdown = {
        "research_overlap": {"score": research_overlap_score, "max": 35, "label": "Research Overlap"},
        "experience_fit": {"score": experience_fit_score, "max": 25, "label": "Documented Experience"},
        "degree_fit": {"score": degree_fit_score, "max": 20, "label": "Degree & Supervisory Fit"},
        "recruitment_evidence": {"score": max(0, recruitment_fit_score), "max": 20, "label": "Recruitment Evidence"}
    }

    match_reason = ". ".join(match_reasons[:3]) + "." if match_reasons else "Faculty member in target discipline."

    return {
        "match_score": total_score,
        "research_overlap_score": research_overlap_score,
        "experience_fit_score": experience_fit_score,
        "degree_fit_score": degree_fit_score,
        "recruitment_fit_score": recruitment_fit_score,
        "match_reason": match_reason,
        "match_reasons": match_reasons,
        "missing_information": missing_info,
        "score_breakdown": score_breakdown,
        "is_heuristic_score": True
    }


def heuristic_professor_extractor(
    page_url: str,
    text_content: str,
    emails_found: List[str],
    profile: Dict[str, Any],
    university_name: str = "Unknown"
) -> List[Dict[str, Any]]:
    """
    Offline heuristic faculty and lab parser.
    Extracts faculty names, academic titles, departments, lab groups, verified emails,
    recruitment status, position funding, and runs the explainable rubric engine.
    Strictly follows: NEVER guess email addresses from naming conventions.
    """
    found: List[Dict[str, Any]] = []
    observed_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Split text into multi-line blocks / sections
    blocks = [b.strip() for b in re.split(r'\n\s*\n', text_content) if b.strip()]
    if len(blocks) <= 1:
        blocks = [p.strip() for p in text_content.split("\n") if len(p.strip()) > 20]

    title_patterns = [
        r'(Prof\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)',
        r'(Dr\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)',
        r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+),\s*(?:Assistant|Associate|Full|Distinguished|Clinical|Adjunct)?\s*Professor',
        r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s*-\s*(?:Assistant|Associate|Full|Distinguished)?\s*Professor',
        r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+),\s*(?:Department Chair|Director|Principal Investigator|Faculty Member)'
    ]

    # Detect page-level lab / group name
    page_lab_group = "Unknown"
    lab_match = re.search(r'([A-Z][A-Za-z0-9\s\(\)\-]{2,45}?\s+(?:Lab|Laboratory|Research Group|Center|Institute))', text_content)
    if lab_match:
        page_lab_group = lab_match.group(1).strip()
    elif "bair" in text_content.lower():
        page_lab_group = "Berkeley Artificial Intelligence Research (BAIR) Lab"

    # Detect global recruitment & funding on page
    global_recruitment_status, global_contact_instructions, global_recruitment_ev = extract_contact_instructions_and_recruitment(text_content)
    global_funding_type, global_funding_ev = extract_funding_separation(text_content)

    for block in blocks:
        block_lower = block.lower()
        for pat in title_patterns:
            matches = re.finditer(pat, block)
            for m in matches:
                raw_name = m.group(1).strip()
                clean_name = re.sub(r'^(Prof\.?|Dr\.?)\s+', '', raw_name).strip()
                if len(clean_name.split()) < 2 or len(clean_name) > 35:
                    continue
                # Filter obvious non-names
                if any(w in clean_name.lower() for w in ["university", "department", "curriculum", "admissions", "scholarship", "faculty directory"]):
                    continue

                # STRICT EMAIL VERIFICATION: Only match emails physically present on page
                associated_email = "Not found"
                email_src_url = ""
                name_parts = clean_name.lower().split()
                last_name = name_parts[-1]
                first_initial = name_parts[0][0] if name_parts[0] else ""

                for em in emails_found:
                    em_lower = em.lower()
                    if last_name in em_lower or (first_initial and f"{first_initial}{last_name}" in em_lower):
                        associated_email = em
                        email_src_url = page_url
                        break

                if associated_email == "Not found" and len(emails_found) == 1 and len(blocks) < 5:
                    associated_email = emails_found[0]
                    email_src_url = page_url

                # Extract block-level recruitment and contact instructions if present
                rec_status, contact_inst, rec_ev = extract_contact_instructions_and_recruitment(block)
                if rec_status == "Unstated":
                    rec_status = global_recruitment_status
                    contact_inst = global_contact_instructions
                    rec_ev = global_recruitment_ev

                # Extract position funding
                pos_funding_type, pos_funding_ev = extract_funding_separation(block)
                if pos_funding_type == "Unstated":
                    pos_funding_type = global_funding_type
                    pos_funding_ev = global_funding_ev

                # Lab Group & Affiliation
                lab_group = page_lab_group
                lab_evidence = f"Affiliated faculty listed on {page_url}"
                if "lab" in block_lower or "group" in block_lower or "center" in block_lower or "bair" in block_lower:
                    local_lab_m = re.search(r'([A-Z][A-Za-z0-9\s\(\)\-]{2,45}?\s+(?:Lab|Laboratory|Group|Center|Institute))', block)
                    if local_lab_m:
                        lab_group = local_lab_m.group(1).strip()
                        lab_evidence = f"Extracted from profile section: '{block[:100]}...'"
                    elif "bair" in block_lower:
                        lab_group = "Berkeley Artificial Intelligence Research (BAIR) Lab"
                        lab_evidence = f"Extracted from profile section: '{block[:100]}...'"

                # Publications / Projects
                pub_proj = "None stated in source"
                if "publication" in block_lower or "paper" in block_lower or "project" in block_lower or "research:" in block_lower:
                    pub_proj = block[:200].replace("\n", " ")

                # Department & Title
                dept = profile.get("target_field") or "Computer Science"
                if "department of" in block_lower:
                    dept_m = re.search(r'Department of ([A-Za-z\s]+)', block, re.I)
                    if dept_m:
                        dept = f"Department of {dept_m.group(1).strip()}"

                title = "Professor"
                if "associate professor" in block_lower:
                    title = "Associate Professor"
                elif "assistant professor" in block_lower:
                    title = "Assistant Professor"
                elif "chair" in block_lower:
                    title = "Department Chair & Professor"
                elif "dr." in raw_name.lower():
                    title = "Faculty Researcher / Dr."

                evidence_snip = block[:300] if len(block) > 20 else text_content[:300]

                prof_record: Dict[str, Any] = {
                    "name": clean_name,
                    "title": title,
                    "department": dept,
                    "university": university_name if university_name != "Unknown" else profile.get("target_field", "University"),
                    "lab_group": lab_group,
                    "lab_url": "",
                    "affiliation_evidence": lab_evidence,
                    "official_profile_url": page_url,
                    "email": associated_email,
                    "email_source_url": email_src_url if associated_email != "Not found" else "",
                    "email_date_observed": observed_date if associated_email != "Not found" else "",
                    "research_interests": block[:150] if len(block) > 30 else profile.get("research_interests", "Unknown"),
                    "publications_projects": pub_proj,
                    "recruitment_status": rec_status,
                    "recruitment_evidence": rec_ev,
                    "position_funding_type": pos_funding_type,
                    "position_funding_evidence": pos_funding_ev,
                    "contact_instructions": contact_inst,
                    "source_url": page_url,
                    "evidence_snippet": evidence_snip
                }

                # Compute explainable rubric
                rubric_res = compute_explainable_rubric(prof_record, profile)
                prof_record.update(rubric_res)

                found.append(prof_record)

    return deduplicate_and_merge_professors([], found)[:12]


def deduplicate_and_merge_professors(
    existing_profs: List[Dict[str, Any]],
    new_profs: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Deduplicates faculty records by normalized name while preserving multiple affiliations,
    merging lab groups, retaining verified emails, and combining evidence.
    """
    merged_map: Dict[str, Dict[str, Any]] = {}

    def get_norm_key(name: str) -> str:
        clean = re.sub(r'^(Prof\.?|Dr\.?)\s+', '', name, flags=re.I).strip().lower()
        parts = clean.split()
        if len(parts) >= 2:
            return f"{parts[0]}_{parts[-1]}"
        return clean

    for p in (existing_profs + new_profs):
        name = p.get("name", "").strip()
        if not name or name.lower() in ("unknown", "none", "n/a"):
            continue

        key = get_norm_key(name)
        if key not in merged_map:
            merged_map[key] = dict(p)
        else:
            curr = merged_map[key]
            # Merge departments
            curr_dept = curr.get("department", "Unknown")
            new_dept = p.get("department", "Unknown")
            if new_dept != "Unknown" and new_dept not in curr_dept:
                curr["department"] = f"{curr_dept}; {new_dept}" if curr_dept != "Unknown" else new_dept

            # Merge lab groups
            curr_lab = curr.get("lab_group", "Unknown")
            new_lab = p.get("lab_group", "Unknown")
            if new_lab != "Unknown" and new_lab not in curr_lab:
                curr["lab_group"] = f"{curr_lab}; {new_lab}" if curr_lab != "Unknown" else new_lab

            # Update lab_url if present in new
            if p.get("lab_url") and not curr.get("lab_url"):
                curr["lab_url"] = p["lab_url"]

            # Update email if current is 'Not found' and new has valid email
            curr_email = curr.get("email", "Not found")
            new_email = p.get("email", "Not found")
            if (not curr_email or curr_email in ("Not found", "Unknown")) and new_email not in ("Not found", "Unknown"):
                curr["email"] = new_email
                curr["email_source_url"] = p.get("email_source_url", curr.get("source_url", ""))
                curr["email_date_observed"] = p.get("email_date_observed", datetime.now(timezone.utc).strftime("%Y-%m-%d"))

            # Update recruitment status if new is more specific
            if p.get("recruitment_status") not in ("Unstated", "Unknown", None) and curr.get("recruitment_status") == "Unstated":
                curr["recruitment_status"] = p["recruitment_status"]
                curr["recruitment_evidence"] = p.get("recruitment_evidence", curr.get("recruitment_evidence", ""))
                curr["contact_instructions"] = p.get("contact_instructions", curr.get("contact_instructions", ""))

            # Update position funding if new is more specific
            if p.get("position_funding_type") not in ("Unstated", "Unknown", None) and curr.get("position_funding_type") == "Unstated":
                curr["position_funding_type"] = p["position_funding_type"]
                curr["position_funding_evidence"] = p.get("position_funding_evidence", curr.get("position_funding_evidence", ""))

            # Merge publications / projects
            curr_pub = curr.get("publications_projects", "None stated in source")
            new_pub = p.get("publications_projects", "None stated in source")
            if new_pub not in ("None stated in source", "Unknown", "") and new_pub not in curr_pub:
                curr["publications_projects"] = f"{curr_pub} | {new_pub}" if curr_pub != "None stated in source" else new_pub

            # Keep highest match score & rubric
            if int(p.get("match_score", 0)) > int(curr.get("match_score", 0)):
                curr["match_score"] = p.get("match_score", 0)
                curr["research_overlap_score"] = p.get("research_overlap_score", 0)
                curr["experience_fit_score"] = p.get("experience_fit_score", 0)
                curr["degree_fit_score"] = p.get("degree_fit_score", 0)
                curr["recruitment_fit_score"] = p.get("recruitment_fit_score", 0)
                curr["match_reason"] = p.get("match_reason", "")
                curr["match_reasons"] = p.get("match_reasons", [])
                curr["missing_information"] = p.get("missing_information", [])
                curr["score_breakdown"] = p.get("score_breakdown", {})

    return list(merged_map.values())


async def match_professors(
    page_url: str,
    text_content: str,
    emails_found: List[str],
    profile: Dict[str, Any],
    job_id: Optional[int] = None,
    university_name: str = "Unknown"
) -> List[Dict[str, Any]]:
    """
    Extracts faculty members, lab affiliations, verified public contacts, and computes
    explainable rubric match scores with AI structured output and heuristic fallback.
    """
    if not text_content or len(text_content.strip()) < 80:
        return []

    minimized = get_task_specific_profile(profile, "professor_matching")
    observed_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    profile_context = f"""Candidate Profile (Research Synergy & Rubric Scope):
- Name: {minimized.get('name', 'Applicant')}
- Target Degree: {minimized.get('target_degree', 'Ph.D.')}
- Academic Discipline: {minimized.get('target_field', 'Computer Science')}
- Stated Research Interests: {minimized.get('research_interests', '')}
- Documented Technical Skills: {minimized.get('technical_skills', '')}
- Publications & Preprints: {minimized.get('publications', '')}
- Experience & Projects: {minimized.get('projects', '') or minimized.get('research_experience', '')}
- Portfolio / GitHub: {minimized.get('portfolio_url', '') or minimized.get('github_url', '')}
"""

    emails_hint = f"Verified public emails detected on this page: {', '.join(emails_found)}" if emails_found else "No email addresses found in page text/mailto."

    framed_text = frame_untrusted_content(text_content, source_url=page_url, content_type="faculty_directory_or_lab_page")
    user_prompt = f"""{profile_context}

Target University: {university_name}
Source URL: {page_url}
{emails_hint}

{framed_text}

Identify faculty members, lab affiliations, verified public emails (or 'Not found'), recruitment status, position funding, and contact instructions. Mark missing details as 'Not found' or 'Unstated'."""

    if ai_client.is_configured():
        try:
            result = await ai_client.generate_structured(
                schema=ProfessorListResponse,
                system_prompt=PROFESSOR_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                job_id=job_id
            )
            if result.data and result.data.professors:
                output_list = []
                for p in result.data.professors:
                    d = p.model_dump()
                    d["source_url"] = page_url
                    d["official_profile_url"] = d.get("official_profile_url") or page_url
                    if d.get("university") in ("Unknown", "", None):
                        d["university"] = university_name

                    # Strict Email Compliance Check
                    raw_email = d.get("email", "").strip()
                    if raw_email and raw_email.lower() not in ("not found", "unknown", "none"):
                        # Verify it was actually in emails_found or page text
                        if raw_email.lower() in [e.lower() for e in emails_found] or raw_email.lower() in text_content.lower():
                            d["email"] = raw_email
                            d["email_source_url"] = page_url
                            d["email_date_observed"] = observed_date
                        else:
                            # Model attempted to hallucinate / guess an email
                            logger.warning(f"[Professor Matcher] Discarding unverified guessed email '{raw_email}' for {d.get('name')}")
                            d["email"] = "Not found"
                            d["email_source_url"] = ""
                            d["email_date_observed"] = ""
                    else:
                        d["email"] = "Not found"

                    # Compute explainable rubric
                    rubric = compute_explainable_rubric(d, profile)
                    d.update(rubric)
                    output_list.append(d)

                return deduplicate_and_merge_professors([], output_list)
            elif result.data:
                return []
        except Exception as e:
            logger.warning(f"[Professor Matcher] Structured AI matching failed: {e}. Falling back to heuristic engine.")

    return heuristic_professor_extractor(page_url, text_content, emails_found, profile, university_name=university_name)
