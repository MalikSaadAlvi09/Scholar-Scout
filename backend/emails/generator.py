"""
Personalized Outreach Drafts Generator & Quality Auditor for ScholarScout.
Generates tailored, respectful academic inquiry emails for professors and funding coordinators.
Enforces strict grounding against confirmed candidate profile, verified professor facts, and saved outreach instructions.
Enforces safety: sending is permanently disabled (human review, copy, and .eml export only).
"""

import re
import json
from typing import Dict, Any, Optional, List, Tuple
from backend.llm.client import ai_client
from backend.llm.schemas import EmailDraftResponse
from backend.llm.security import frame_untrusted_content
from backend.database import (
    save_email_draft,
    get_email_drafts,
    get_email_draft,
    delete_email_draft,
    get_outreach_settings,
    get_db_connection
)
from backend.profiles.manager import get_task_specific_profile
from backend.logging_utils import logger

EMAIL_SYSTEM_PROMPT = """You are an expert academic advisor helping graduate applicants write concise, professional, and grounded outreach emails to university professors and scholarship committees.

STRICT GROUNDEDNESS & ETHICS GUIDELINES:
1. Tone must be respectful, articulate, scholarly, and concise (strictly under 200 words for the body).
2. ONLY use verified facts from the candidate profile and professor lab evidence provided.
3. NEVER invent qualifications, claim the candidate read a paper that is not explicitly in their background, or assume funding is guaranteed unless explicitly confirmed.
4. Adhere strictly to the user's outreach instructions (purpose, degree, intake, tone, call to action, signature).
5. Do NOT include internal citations or source footnotes in the outgoing email body itself (evidence is stored separately).
6. Provide output matching the JSON schema with "subject" and "body_text".
"""

def detect_contact_instructions_flag(professor: Dict[str, Any]) -> Tuple[str, str]:
    """
    Checks published contact instructions and flags profiles that discourage direct outreach.
    Returns (flag_type, explanation_notes).
    flag_type in ['standard', 'discouraged', 'portal_required']
    """
    contact_inst = (professor.get("contact_instructions") or "").lower()
    recruitment_status = (professor.get("recruitment_status") or "").lower()
    recruitment_evidence = (professor.get("recruitment_evidence") or "").lower()
    notes = (professor.get("notes") or "").lower()

    combined_text = f"{contact_inst} {recruitment_status} {recruitment_evidence} {notes}"

    # Check for direct discouragement or restrictions
    if any(p in combined_text for p in [
        "do not email", "do not contact directly", "no cold email",
        "will not respond to prospective student emails", "not accepting new students",
        "not taking students", "no open positions", "unsolicited emails will be deleted",
        "do not contact faculty directly"
    ]):
        return (
            "discouraged",
            "Faculty published instructions indicate that direct cold emails are discouraged or faculty is not taking new students."
        )

    if any(p in combined_text for p in [
        "apply through the graduate portal", "apply through department", "admissions portal first",
        "central admissions", "apply to eecs first", "department application required",
        "do not send cv before applying", "apply via centralized portal"
    ]):
        return (
            "portal_required",
            "Department guidelines require submitting a formal application through the central graduate admissions portal before contacting faculty."
        )

    return ("standard", "")

def audit_draft_grounding(
    subject: str,
    body_text: str,
    profile: Dict[str, Any],
    professor: Dict[str, Any],
    outreach_settings: Dict[str, Any]
) -> Tuple[bool, str]:
    """
    Audits an outreach draft for unsupported claims, exaggerated research fit, or assumed funding.
    Returns (has_unsupported_claims: bool, warning_notes: str).
    """
    warnings: List[str] = []
    body_lower = body_text.lower()
    prof_funding = (professor.get("position_funding_type") or "").lower()
    recruitment_status = (professor.get("recruitment_status") or "").lower()

    # 1. Check for assumed guaranteed funding when evidence is unconfirmed
    if any(w in body_lower for w in ["guaranteed funding", "fully funded offer", "confirmed stipend", "your funded slot"]):
        if "unstated" in prof_funding or "unverified" in prof_funding or "not stated" in prof_funding:
            warnings.append("Draft references guaranteed funding, but official lab evidence lists funding as unstated or unverified.")

    # 2. Check for claims of having read unverified papers
    if "i read your paper" in body_lower or "after reading your paper" in body_lower or "fascinated by your recent publication" in body_lower:
        prof_papers = professor.get("publications_projects", "")
        if not prof_papers or prof_papers == "None stated in source":
            warnings.append("Draft claims to have read a specific publication, but no verified publications are documented for this faculty member.")

    # 3. Check for exaggerated credentials not in candidate profile
    gpa = profile.get("gpa", "")
    degree = profile.get("target_degree", "Ph.D.")
    if "master's degree" in body_lower and "master" not in str(profile.get("current_major", "")).lower() and "ph.d." in degree.lower() and "bachelor" in str(profile.get("background_summary", "")).lower():
        # warning if claiming master's when candidate only has bachelor's
        warnings.append("Draft mentions possessing a Master's degree; verify this matches your confirmed academic record.")

    # 4. Check for length constraints
    word_count = len(body_text.split())
    if word_count > 260:
        warnings.append(f"Draft body length ({word_count} words) exceeds recommended academic outreach limit of 200-250 words.")

    has_unsupported = len(warnings) > 0
    warning_notes = " | ".join(warnings) if warnings else ""
    return (has_unsupported, warning_notes)

def generate_heuristic_draft(
    recipient_name: str,
    recipient_email: str,
    recipient_role: str,
    context_title: str,
    context_details: str,
    profile: Dict[str, Any],
    outreach_settings: Optional[Dict[str, Any]] = None,
    professor: Optional[Dict[str, Any]] = None
) -> Dict[str, str]:
    """Generates a high-quality academic template draft strictly respecting user outreach settings."""
    settings = outreach_settings or get_outreach_settings()
    student_name = profile.get("name", "Applicant")
    target_degree = profile.get("target_degree", "Ph.D.")
    target_field = profile.get("target_field") or profile.get("current_major", "Computer Science")
    interests = profile.get("research_interests", "Artificial Intelligence")
    background = profile.get("background_summary", "Strong academic coursework and research background.")
    
    degree_intake = settings.get("target_degree_intake") or f"{target_degree} in {target_field} (Fall 2026)"
    purpose = settings.get("purpose") or f"Prospective {target_degree} Research Inquiry"
    specific_request = settings.get("specific_request") or "Could you let me know if you are currently advising new graduate researchers for the upcoming academic year? I would welcome an opportunity to briefly discuss how my background aligns with your lab."
    background_emphasis = settings.get("background_to_emphasize") or background
    raw_sig = settings.get("signature") or f"Sincerely,\n{student_name}\n[Contact Information]"
    if "[Candidate Name]" in raw_sig:
        signature = raw_sig.replace("[Candidate Name]", student_name)
    elif "[Candidate]" in raw_sig:
        signature = raw_sig.replace("[Candidate]", student_name)
    elif "Jane Doe" in raw_sig and student_name != "Jane Doe":
        signature = raw_sig.replace("Jane Doe", student_name)
    elif student_name not in raw_sig:
        signature = f"Sincerely,\n{student_name}\n{raw_sig}"
    else:
        signature = raw_sig

    # Professor salutation
    clean_name = recipient_name.strip()
    if clean_name.startswith("Dr.") or clean_name.startswith("Prof."):
        salutation = f"Dear {clean_name},"
    elif "Dr" in clean_name or "Prof" in clean_name:
        salutation = f"Dear {clean_name},"
    else:
        salutation = f"Dear Professor {clean_name},"

    primary_interest = interests.split(",")[0].strip() if "," in interests else interests.strip()
    
    subject = f"Prospective {target_degree} Inquiry ({degree_intake}) - {student_name} [{primary_interest}]"

    # Context quotation or summary
    prof_focus = context_title or primary_interest
    evidence_snippet = context_details.strip()
    if evidence_snippet and len(evidence_snippet) > 120:
        evidence_snippet = evidence_snippet[:120].rsplit(" ", 1)[0] + "..."

    connection_paragraph = (
        f"My name is {student_name}, and I am writing to express my strong interest in joining your research group for {degree_intake}. "
        f"I have closely followed your group's focus on {prof_focus}"
    )
    if evidence_snippet and evidence_snippet != "None stated in source":
        connection_paragraph += f", specifically your work concerning {evidence_snippet}."
    else:
        connection_paragraph += "."

    body_text = f"""{salutation}

{connection_paragraph}

My background includes {background_emphasis}. With our shared focus on {interests}, I would be eager to contribute to your ongoing investigations and laboratory initiatives.

{specific_request}

I have attached my academic CV and relevant transcripts for your convenience. Thank you very much for your time, consideration, and guidance.

{signature}
"""

    return {
        "subject": subject.strip(),
        "body_text": body_text.strip()
    }

async def create_outreach_draft(
    recipient_name: str,
    recipient_email: str,
    recipient_role: str,
    draft_type: str,
    context_title: str,
    context_details: str,
    profile: Dict[str, Any],
    job_id: Optional[int] = None,
    professor_id: Optional[int] = None,
    scholarship_id: Optional[int] = None,
    custom_instructions: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Generates and saves a personalized email draft to SQLite.
    Always creates drafts with can_send = 0 (sending strictly disabled).
    Extracts verified evidence citations, checks contact flags, and audits claims.
    """
    outreach_settings = custom_instructions or get_outreach_settings()
    minimized_profile = get_task_specific_profile(profile, "email_drafting")
    profile_version = profile.get("version", 1)

    # Fetch professor record if professor_id provided
    professor_data: Dict[str, Any] = {}
    if professor_id:
        conn = get_db_connection()
        p_row = conn.execute("SELECT * FROM professors WHERE id = ?", (professor_id,)).fetchone()
        conn.close()
        if p_row:
            professor_data = dict(p_row)

    # Check published contact instructions
    contact_flag, contact_notes = detect_contact_instructions_flag(professor_data)

    subject = ""
    body_text = ""

    # Build prompt with exact outreach settings and grounded context
    framed_context = frame_untrusted_content(
        context_details,
        source_url="academic_context",
        content_type="faculty_or_award_details"
    )

    user_prompt = f"""Candidate Profile (Confirmed Facts Only):
- Name: {minimized_profile.get('name', 'Applicant')}
- Target Degree & Major: {minimized_profile.get('target_degree', 'Ph.D.')} in {minimized_profile.get('target_field', 'Computer Science')}
- Verified GPA: {minimized_profile.get('gpa', '3.95/4.0')}
- Confirmed Research Interests: {minimized_profile.get('research_interests', '')}
- Background Summary: {minimized_profile.get('background_summary', '')}
- Declared Publications: {minimized_profile.get('publications', 'None listed')}
- Portfolio / Link: {minimized_profile.get('portfolio_url', '')}

Recipient Faculty Information:
- Name: {recipient_name}
- Email: {recipient_email}
- Institution: {professor_data.get('university', 'University')}
- Department: {professor_data.get('department', 'Computer Science')}
- Verified Research Focus: {context_title or professor_data.get('research_interests', '')}
- Verified Recruitment Status: {professor_data.get('recruitment_status', 'Unstated')}
- Verified Funding Context: {professor_data.get('position_funding_type', 'Unstated')}

Verified Lab / Source Evidence:
{framed_context}

User Saved Outreach Instructions:
- Purpose: {outreach_settings.get('purpose', 'PhD Advisorship & Research Assistantship Inquiry')}
- Target Degree & Intake: {outreach_settings.get('target_degree_intake', 'Ph.D. in Computer Science (Fall 2026)')}
- Tone & Max Length: {outreach_settings.get('tone_and_length', 'Professional, concise, scholarly; under 200 words')}
- Specific Call to Action / Request: {outreach_settings.get('specific_request', 'Request a brief 15-minute video call')}
- Background Details to Emphasize: {outreach_settings.get('background_to_emphasize', '')}
- Signature Block: {outreach_settings.get('signature', f'Sincerely,\n{minimized_profile.get("name", "Applicant")}')}
- Proposed Attachments: {outreach_settings.get('proposed_attachments', 'Academic CV (PDF)')}
- Optional Wording Preferences / Constraints: {outreach_settings.get('optional_wording_preferences', '')}

Generate a concise, personalized outreach email adhering to the JSON schema:"""

    if ai_client.is_configured():
        try:
            result = await ai_client.generate_structured(
                schema=EmailDraftResponse,
                system_prompt=EMAIL_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                job_id=job_id
            )
            if result.data:
                subject = result.data.subject
                body_text = result.data.body_text
        except Exception as e:
            logger.warning(f"[Email Generator] AI draft generation failed: {e}. Using template engine.")

    if not subject or not body_text:
        draft = generate_heuristic_draft(
            recipient_name=recipient_name,
            recipient_email=recipient_email,
            recipient_role=recipient_role,
            context_title=context_title,
            context_details=context_details,
            profile=minimized_profile,
            outreach_settings=outreach_settings,
            professor=professor_data
        )
        subject = draft["subject"]
        body_text = draft["body_text"]

    # Audit draft for unsupported or exaggerated claims
    has_unsupported, audit_notes = audit_draft_grounding(
        subject=subject,
        body_text=body_text,
        profile=minimized_profile,
        professor=professor_data,
        outreach_settings=outreach_settings
    )

    # Determine initial status
    if contact_flag == "discouraged":
        initial_status = "flagged_discouraged"
    elif has_unsupported:
        initial_status = "needs_review"
    else:
        initial_status = "draft"

    # Compile structured evidence citations for side-by-side display
    evidence_used = {
        "candidate_facts": [
            f"Target Degree: {minimized_profile.get('target_degree', 'Ph.D.')} in {minimized_profile.get('target_field', 'Computer Science')}",
            f"Verified GPA: {minimized_profile.get('gpa', '3.95/4.0')}",
            f"Declared Interests: {minimized_profile.get('research_interests', '')}",
            f"Profile Version: v{profile_version}"
        ],
        "professor_facts": [
            f"Faculty: {recipient_name} ({professor_data.get('department', 'Computer Science')}, {professor_data.get('university', 'University')})",
            f"Verified Research Focus: {context_title or professor_data.get('research_interests', 'Stated in profile')}",
            f"Recruitment Status: {professor_data.get('recruitment_status', 'Unstated')}",
            f"Contact Policy: {professor_data.get('contact_instructions', 'Standard inquiry')}"
        ],
        "funding_facts": [
            f"Funding Type: {professor_data.get('position_funding_type', 'Unstated on faculty page')}",
            f"Evidence Quote: {professor_data.get('recruitment_evidence', 'None stated in source')[:140]}"
        ],
        "outreach_parameters": {
            "purpose": outreach_settings.get("purpose", ""),
            "target_degree_intake": outreach_settings.get("target_degree_intake", ""),
            "tone_and_length": outreach_settings.get("tone_and_length", ""),
            "specific_request": outreach_settings.get("specific_request", "")
        },
        "source_links": [
            {"label": "Faculty Official Profile", "url": professor_data.get("official_profile_url", "")},
            {"label": "Laboratory / Research Group", "url": professor_data.get("lab_url", "")}
        ]
    }

    # Proposed attachments list
    raw_attachments = outreach_settings.get("proposed_attachments", "Academic CV (PDF), Unofficial Transcript")
    if isinstance(raw_attachments, str):
        attachments_list = [a.strip() for a in raw_attachments.split(",") if a.strip()]
    elif isinstance(raw_attachments, list):
        attachments_list = raw_attachments
    else:
        attachments_list = ["Academic CV (PDF)"]

    draft_record = {
        "job_id": job_id,
        "professor_id": professor_id,
        "scholarship_id": scholarship_id,
        "profile_version": profile_version,
        "recipient_name": recipient_name or "Faculty Member",
        "recipient_email": recipient_email or "Unknown",
        "recipient_role": recipient_role or "Faculty / PI",
        "draft_type": draft_type or "Professor Research Inquiry",
        "subject": subject,
        "body_text": body_text,
        "attachments": attachments_list,
        "evidence_used": evidence_used,
        "outreach_instructions": outreach_settings,
        "contact_instructions_flag": contact_flag,
        "contact_instructions_notes": contact_notes,
        "unsupported_claims_flag": 1 if has_unsupported else 0,
        "unsupported_claims_notes": audit_notes,
        "status": initial_status,
        "is_reviewed": 0
    }

    draft_id = save_email_draft(draft_record)
    draft_record["id"] = draft_id
    draft_record["can_send"] = 0
    draft_record["safety_notice"] = "Sending is disabled by default. Please review, edit, copy, and send from your institutional email client."

    return draft_record
