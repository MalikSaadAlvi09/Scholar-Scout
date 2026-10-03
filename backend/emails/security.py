"""
Security, Approval Hashing, Attachment Validation, and Guardrails for Outreach Sending.
Enforces:
1. Exact content hash verification (editing recipient, subject, body, or attachments invalidates approval).
2. Attachment safety checks (file extension whitelist, size limits, binary execution block).
3. Do-Not-Contact (DNC) suppression list checks (exact email and domain-level).
4. Duplicate-send protection (prevents redundant emails to faculty within 30 days).
"""

import hashlib
import os
import json
from typing import Dict, Any, List, Optional, Tuple
from backend.database import get_db_connection
from backend.logging_utils import logger

# Permitted attachment file extensions
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".rtf", ".png", ".jpg", ".jpeg"}

# Forbidden dangerous file extensions
BLOCKED_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".sh", ".vbs", ".js", ".scr", ".bin",
    ".msi", ".jar", ".ps1", ".py", ".com", ".pif", ".hta", ".reg"
}

# Maximum file sizes
MAX_SINGLE_ATTACHMENT_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_TOTAL_ATTACHMENT_BYTES = 25 * 1024 * 1024   # 25 MB

def normalize_text(text: Optional[str]) -> str:
    """Normalizes whitespace and linebreaks for deterministic hashing."""
    if not text:
        return ""
    # Strip leading/trailing, normalize CRLF to LF
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(lines).strip()

def compute_content_hash(
    recipient_email: str,
    subject: str,
    body_text: str,
    attachments: Optional[List[Any]] = None
) -> str:
    """
    Computes a cryptographic SHA256 hex digest of the exact message version.
    Any edit to recipient, subject, body text, or attachments alters this hash,
    invalidating prior approvals.
    """
    norm_recipient = (recipient_email or "").strip().lower()
    norm_subject = normalize_text(subject)
    norm_body = normalize_text(body_text)

    # Normalize attachments representation
    att_repr_list = []
    if attachments:
        for att in attachments:
            if isinstance(att, str):
                att_repr_list.append(att.strip().lower())
            elif isinstance(att, dict):
                att_name = att.get("name", "").strip().lower()
                att_size = str(att.get("size_bytes", 0))
                att_sha = att.get("sha256", "")
                att_repr_list.append(f"{att_name}:{att_size}:{att_sha}")
    att_repr_list.sort()
    norm_attachments = "|".join(att_repr_list)

    raw_payload = f"TO:{norm_recipient}###SUBJ:{norm_subject}###BODY:{norm_body}###ATT:{norm_attachments}"
    return hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()

def validate_draft_approval(draft: Dict[str, Any]) -> Tuple[bool, str, str]:
    """
    Validates if a draft's current content matches its approved content hash.
    Returns (is_valid: bool, current_hash: str, explanation: str).
    """
    current_hash = compute_content_hash(
        recipient_email=draft.get("recipient_email", ""),
        subject=draft.get("subject", ""),
        body_text=draft.get("body_text", ""),
        attachments=draft.get("attachments", [])
    )

    approval_status = draft.get("approval_status", "draft")
    approved_hash = draft.get("approved_content_hash", "")

    if approval_status != "approved":
        return (False, current_hash, f"Draft has not been approved (current status: '{approval_status}').")

    if not approved_hash:
        return (False, current_hash, "Draft has no recorded approved content hash.")

    if current_hash != approved_hash:
        return (
            False,
            current_hash,
            "Approval invalidated: The draft content (recipient, subject, body, or attachments) has been modified since approval."
        )

    return (True, current_hash, "Draft content exactly matches the approved version hash.")

def validate_attachments(attachments: Optional[List[Any]]) -> Tuple[bool, Optional[str], List[Dict[str, Any]]]:
    """
    Validates attachment files for safety, allowed types, and size constraints.
    Returns (is_valid, error_message, validated_attachment_objects).
    """
    if not attachments:
        return (True, None, [])

    validated: List[Dict[str, Any]] = []
    total_bytes = 0

    for item in attachments:
        if isinstance(item, str):
            name = item.strip()
            path = ""
            size = 0
            # If item is a file path or description
            if os.path.exists(name):
                path = os.path.abspath(name)
                name = os.path.basename(path)
                size = os.path.getsize(path)
        elif isinstance(item, dict):
            name = item.get("name", "").strip()
            path = item.get("path", "")
            size = item.get("size_bytes", 0)
            if path and os.path.exists(path) and size == 0:
                size = os.path.getsize(path)
        else:
            continue

        if not name:
            continue

        ext = os.path.splitext(name)[1].lower()

        # Check dangerous file extensions
        if ext in BLOCKED_EXTENSIONS:
            return (
                False,
                f"Attachment '{name}' has a forbidden executable extension ({ext}). Only academic documents and images are permitted.",
                []
            )

        # Check permitted extensions
        if ext and ext not in ALLOWED_EXTENSIONS:
            return (
                False,
                f"Attachment '{name}' extension ({ext}) is not supported. Allowed extensions: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
                []
            )

        # Check single file size limit
        if size > MAX_SINGLE_ATTACHMENT_BYTES:
            mb_size = size / (1024 * 1024)
            return (
                False,
                f"Attachment '{name}' ({mb_size:.1f} MB) exceeds the maximum single file size limit of 10 MB.",
                []
            )

        total_bytes += size

        # Compute file SHA256 if file exists on disk
        file_sha = ""
        if path and os.path.isfile(path):
            try:
                with open(path, "rb") as f:
                    file_sha = hashlib.sha256(f.read()).hexdigest()
            except Exception:
                file_sha = ""

        validated.append({
            "name": name,
            "path": path,
            "size_bytes": size,
            "extension": ext or ".pdf",
            "sha256": file_sha
        })

    # Check total size limit
    if total_bytes > MAX_TOTAL_ATTACHMENT_BYTES:
        total_mb = total_bytes / (1024 * 1024)
        return (
            False,
            f"Total attachments size ({total_mb:.1f} MB) exceeds the maximum allowed total size of 25 MB.",
            []
        )

    return (True, None, validated)

def check_do_not_contact(recipient_email: str) -> Tuple[bool, Optional[str]]:
    """
    Checks if the recipient email or domain is present on the Do-Not-Contact suppression list.
    Returns (is_blocked: bool, block_reason: Optional[str]).
    """
    if not recipient_email or not recipient_email.strip():
        return (True, "Invalid or empty recipient email address.")

    clean_email = recipient_email.strip().lower()
    email_domain = clean_email.split("@")[-1] if "@" in clean_email else ""

    conn = get_db_connection()
    cursor = conn.cursor()

    # Query matching exact email or domain patterns (@domain.edu or domain.edu)
    rows = cursor.execute("""
    SELECT pattern, reason FROM do_not_contact
    """).fetchall()
    conn.close()

    for r in rows:
        pat = (r["pattern"] or "").strip().lower()
        reason = r["reason"] or "Recipient is listed on Do-Not-Contact suppression list."

        if pat == clean_email:
            return (True, f"Do-Not-Contact blocked: Exact match for {clean_email} ({reason})")

        if pat.startswith("@") and pat[1:] == email_domain:
            return (True, f"Do-Not-Contact blocked: Domain {email_domain} is suppressed ({reason})")

        if pat == email_domain:
            return (True, f"Do-Not-Contact blocked: Domain {email_domain} is suppressed ({reason})")

    return (False, None)

def check_duplicate_send(
    recipient_email: str,
    subject: str,
    window_days: int = 30
) -> Tuple[bool, Optional[str]]:
    """
    Checks audit log and active outbound queue for recent sends to the same recipient.
    Prevents duplicate emails to faculty within the specified window.
    Returns (is_duplicate: bool, duplicate_details: Optional[str]).
    """
    clean_email = (recipient_email or "").strip().lower()
    if not clean_email:
        return (False, None)

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Check active outbound queue (queued or provider-accepted)
    queue_row = cursor.execute("""
    SELECT id, status, subject, created_at FROM email_outbound_queue
    WHERE LOWER(recipient_email) = ? AND status IN ('queued', 'provider-accepted', 'uncertain')
    ORDER BY id DESC LIMIT 1
    """, (clean_email,)).fetchone()

    if queue_row:
        conn.close()
        return (
            True,
            f"Duplicate protection: An email with subject '{queue_row['subject']}' is already in outbound queue (Status: {queue_row['status']}, Queued at: {queue_row['created_at']})."
        )

    # 2. Check audit log within window_days
    log_row = cursor.execute(f"""
    SELECT action, details_json, created_at FROM email_audit_log
    WHERE LOWER(recipient_email) = ? AND action IN ('provider_accepted', 'dispatched', 'reconciled_sent')
      AND created_at >= datetime('now', '-{int(window_days)} days')
    ORDER BY id DESC LIMIT 1
    """, (clean_email,)).fetchone()

    conn.close()

    if log_row:
        return (
            True,
            f"Duplicate protection: Message was previously dispatched to {clean_email} within the past {window_days} days (Action: {log_row['action']}, Date: {log_row['created_at']})."
        )

    return (False, None)
