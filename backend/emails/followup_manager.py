"""
Follow-Up Draft Automation and Reply-Stopping Safety for ScholarScout.
Enforces:
1. Generation of concise, respectful follow-up drafts for contacted professors.
2. STRICT STOPPING: Automatically halts and cancels follow-up drafts the moment
   a reply or opt-out is detected from the professor.
"""

from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone
from backend.database import get_db_connection, save_email_draft
from backend.emails.security import check_do_not_contact
from backend.emails.queue_manager import log_email_action
from backend.logging_utils import logger

def check_can_generate_followup(recipient_email: str) -> Tuple[bool, str]:
    """
    Checks if a follow-up draft is safe to generate.
    Blocks generation if professor replied, opted out, or is on Do-Not-Contact list.
    """
    clean_email = (recipient_email or "").strip().lower()
    if not clean_email:
        return (False, "Recipient email is empty.")

    # 1. Check Do-Not-Contact
    dnc_blocked, dnc_reason = check_do_not_contact(clean_email)
    if dnc_blocked:
        return (False, f"Follow-up blocked: {dnc_reason}")

    # 2. Check if a reply has been recorded from this professor
    conn = get_db_connection()
    reply_row = conn.execute("""
    SELECT id, subject, snippet, received_at FROM email_replies
    WHERE LOWER(sender_email) = ?
    ORDER BY id DESC LIMIT 1
    """, (clean_email,)).fetchone()
    conn.close()

    if reply_row:
        return (
            False,
            f"Follow-up halted: Professor has already replied to outreach (Subject: '{reply_row['subject']}', Received: {reply_row['received_at']})."
        )

    return (True, "Ready for follow-up generation.")

def generate_followup_draft(
    parent_draft_id: int,
    days_elapsed: int = 7
) -> Tuple[bool, str, Optional[int]]:
    """
    Creates a respectful follow-up draft linked to an initial outreach email.
    Stops immediately if a reply or opt-out exists.
    """
    conn = get_db_connection()
    parent_row = conn.execute("SELECT * FROM email_drafts WHERE id = ?", (parent_draft_id,)).fetchone()
    conn.close()

    if not parent_row:
        return (False, f"Parent draft #{parent_draft_id} not found.", None)

    parent = dict(parent_row)
    recipient_email = parent.get("recipient_email", "")

    # Safety check against replies and DNC
    can_gen, reason = check_can_generate_followup(recipient_email)
    if not can_gen:
        logger.info(f"[FollowUp] Blocked follow-up for {recipient_email}: {reason}")
        return (False, reason, None)

    # Generate polite, concise follow-up text
    recipient_name = parent.get("recipient_name", "Professor")
    parent_subject = parent.get("subject", "Prospective PhD Inquiry")
    followup_subject = f"Following up: {parent_subject}" if not parent_subject.startswith("Following up:") else parent_subject

    body_text = (
        f"Dear {recipient_name},\n\n"
        f"I hope you are having a productive week.\n\n"
        f"I am writing to briefly follow up on my inquiry regarding prospective doctoral research opportunities in your laboratory. "
        f"I remain enthusiastic about your team's published work and would welcome the opportunity to discuss prospective research synergy if you are reviewing applicants for upcoming intakes.\n\n"
        f"Thank you very much for your time and consideration.\n\n"
        f"Sincerely,\n"
        f"Applicant"
    )

    followup_data = {
        "job_id": parent.get("job_id"),
        "professor_id": parent.get("professor_id"),
        "scholarship_id": parent.get("scholarship_id"),
        "profile_version": parent.get("profile_version", 1),
        "recipient_name": parent.get("recipient_name", ""),
        "recipient_email": recipient_email,
        "recipient_role": parent.get("recipient_role", "Faculty / PI"),
        "draft_type": "Follow-Up Inquiry",
        "subject": followup_subject,
        "body_text": body_text,
        "attachments": parent.get("attachments", ["Academic CV (PDF)"]),
        "status": "draft",
        "parent_draft_id": parent_draft_id,
        "follow_up_sequence": (parent.get("follow_up_sequence") or 0) + 1,
        "safety_notice": f"Follow-up draft generated (elapsed: {days_elapsed} days). Will automatically halt if a reply is detected."
    }

    followup_id = save_email_draft(followup_data)

    log_email_action(
        action="followup_created",
        recipient_email=recipient_email,
        draft_id=followup_id,
        details={"parent_draft_id": parent_draft_id, "sequence": followup_data["follow_up_sequence"]}
    )

    return (True, f"Follow-up draft #{followup_id} created successfully.", followup_id)
