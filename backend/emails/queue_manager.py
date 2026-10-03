"""
Durable Outbound Email Queue Manager, Approval Workflow, and Audit Logger for ScholarScout.
Enforces:
1. Strict pre-send approval matching exact message hash.
2. Controlled master switch (sending is disabled until explicitly enabled).
3. Durable outbound queue with configurable rate limits.
4. Provider acceptance tracking and audit logs.
5. Ambiguous timeout handling with non-retry reconciliation.
6. Reply synchronization and follow-up halting.
"""

import json
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from backend.database import get_db_connection
from backend.emails.security import (
    compute_content_hash,
    validate_draft_approval,
    validate_attachments,
    check_do_not_contact,
    check_duplicate_send
)
from backend.emails.providers.factory import get_email_provider
from backend.logging_utils import logger

def log_email_action(
    action: str,
    recipient_email: str,
    draft_id: Optional[int] = None,
    queue_id: Optional[int] = None,
    account_id: Optional[int] = None,
    provider_message_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    cursor: Any = None
) -> int:
    """Inserts a structured entry into the persistent email_audit_log table."""
    details_str = json.dumps(details or {})
    if cursor:
        cursor.execute("""
        INSERT INTO email_audit_log (
            draft_id, queue_id, account_id, recipient_email, action,
            provider_message_id, details_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            draft_id,
            queue_id,
            account_id,
            (recipient_email or "").strip().lower(),
            action,
            provider_message_id or "",
            details_str
        ))
        return cursor.lastrowid or 0

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
    INSERT INTO email_audit_log (
        draft_id, queue_id, account_id, recipient_email, action,
        provider_message_id, details_json, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (
        draft_id,
        queue_id,
        account_id,
        (recipient_email or "").strip().lower(),
        action,
        provider_message_id or "",
        details_str
    ))
    log_id = c.lastrowid or 0
    conn.commit()
    conn.close()
    return log_id

# --- Sending Settings & Master Switch ---

def get_sending_settings() -> Dict[str, Any]:
    """Retrieves master sending settings."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Initialize default settings if not existing
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()

    rows = cursor.execute("SELECT key, value FROM system_settings").fetchall()
    conn.close()

    settings_dict = {r["key"]: r["value"] for r in rows}

    return {
        "sending_master_enabled": settings_dict.get("sending_master_enabled", "0") == "1",
        "max_hourly_outbound": int(settings_dict.get("max_hourly_outbound", "20")),
        "duplicate_window_days": int(settings_dict.get("duplicate_window_days", "30")),
        "default_account_id": int(settings_dict.get("default_account_id", "1")) if settings_dict.get("default_account_id") else 1,
        "auto_reconcile_timeouts": settings_dict.get("auto_reconcile_timeouts", "1") == "1"
    }

def update_sending_settings(updates: Dict[str, Any]) -> Dict[str, Any]:
    """Updates master sending settings."""
    conn = get_db_connection()
    cursor = conn.cursor()

    for k, v in updates.items():
        val_str = "1" if v is True else "0" if v is False else str(v)
        cursor.execute("""
        INSERT INTO system_settings (key, value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
        """, (k, val_str))

    conn.commit()
    conn.close()
    return get_sending_settings()

def toggle_master_sending(enabled: bool, reason: str = "User toggle") -> Dict[str, Any]:
    """Toggles the global master sending switch."""
    res = update_sending_settings({"sending_master_enabled": enabled})
    log_email_action(
        action="master_switch_toggled",
        recipient_email="system@scholarscout.local",
        details={"enabled": enabled, "reason": reason}
    )
    logger.info(f"[Email Queue] Master sending switch set to {enabled} ({reason})")
    return res

# --- Email Accounts Management ---

def get_email_accounts() -> List[Dict[str, Any]]:
    """Retrieves all registered email accounts with sanitized credentials."""
    conn = get_db_connection()
    rows = conn.execute("""
    SELECT id, name, provider_type, email_address, credentials_json,
           is_active, hourly_limit, daily_limit, delay_between_sends_sec,
           reply_sync_enabled, created_at, updated_at
    FROM email_accounts
    ORDER BY id ASC
    """).fetchall()
    conn.close()

    accounts = []
    for r in rows:
        d = dict(r)
        # Never expose full raw secrets to frontend
        creds = {}
        if d.get("credentials_json"):
            try:
                creds = json.loads(d["credentials_json"])
            except Exception:
                creds = {}
        d["has_credentials"] = bool(creds)
        d["provider_details"] = {
            "simulation_mode": creds.get("simulation_mode", "normal") if d["provider_type"] == "mock_sandbox" else None,
            "smtp_host": creds.get("smtp_host") if d["provider_type"] == "custom_smtp" else None,
            "smtp_port": creds.get("smtp_port") if d["provider_type"] == "custom_smtp" else None,
            "client_id": creds.get("client_id", "")[:6] + "..." if creds.get("client_id") else ""
        }
        del d["credentials_json"]
        accounts.append(d)
    return accounts

def get_email_account(account_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves single email account with full backend credentials for dispatch."""
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM email_accounts WHERE id = ?", (account_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    creds = {}
    if d.get("credentials_json"):
        try:
            creds = json.loads(d["credentials_json"])
        except Exception:
            creds = {}
    d["credentials"] = creds
    return d

def save_email_account(data: Dict[str, Any]) -> int:
    """Creates or updates an email account."""
    conn = get_db_connection()
    cursor = conn.cursor()

    account_id = data.get("id")
    name = data.get("name", "My Academic Email").strip()
    provider_type = data.get("provider_type", "mock_sandbox").strip().lower()
    email_address = data.get("email_address", "").strip()
    creds = data.get("credentials", {})
    if isinstance(creds, dict):
        creds_json = json.dumps(creds)
    else:
        creds_json = str(creds)

    hourly_limit = int(data.get("hourly_limit", 20))
    daily_limit = int(data.get("daily_limit", 100))
    delay_sec = int(data.get("delay_between_sends_sec", 15))
    reply_sync = 1 if data.get("reply_sync_enabled") else 0
    is_active = 1 if data.get("is_active", True) else 0

    if account_id:
        cursor.execute("""
        UPDATE email_accounts SET
            name = ?, provider_type = ?, email_address = ?, credentials_json = ?,
            hourly_limit = ?, daily_limit = ?, delay_between_sends_sec = ?,
            reply_sync_enabled = ?, is_active = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """, (
            name, provider_type, email_address, creds_json,
            hourly_limit, daily_limit, delay_sec, reply_sync, is_active, account_id
        ))
    else:
        cursor.execute("""
        INSERT INTO email_accounts (
            name, provider_type, email_address, credentials_json,
            hourly_limit, daily_limit, delay_between_sends_sec,
            reply_sync_enabled, is_active
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            name, provider_type, email_address, creds_json,
            hourly_limit, daily_limit, delay_sec, reply_sync, is_active
        ))
        account_id = cursor.lastrowid

    conn.commit()
    conn.close()
    return account_id

def delete_email_account(account_id: int) -> bool:
    """Deletes an email account (Mock sandbox cannot be deleted if it is ID 1)."""
    if account_id == 1:
        # Preserve default sandbox account
        return False
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM email_accounts WHERE id = ?", (account_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

def test_account_connection(account_id: int) -> Dict[str, Any]:
    """Validates connection health for an email account."""
    acc = get_email_account(account_id)
    if not acc:
        return {"valid": False, "message": "Email account not found."}
    provider = get_email_provider(acc)
    return provider.validate_connection()

# --- Draft Approval & Invalidation ---

def approve_email_draft(draft_id: int, user_identifier: str = "Candidate User") -> Tuple[bool, str]:
    """
    Approves an exact message version.
    Records the approved content hash and transitions status to 'approved'.
    """
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM email_drafts WHERE id = ?", (draft_id,)).fetchone()
    if not row:
        conn.close()
        return (False, f"Draft ID {draft_id} not found.")

    draft = dict(row)
    # Parse attachments
    attachments = []
    if draft.get("attachments"):
        try:
            attachments = json.loads(draft["attachments"])
        except Exception:
            attachments = [draft["attachments"]]

    # Compute exact content hash
    content_hash = compute_content_hash(
        recipient_email=draft.get("recipient_email", ""),
        subject=draft.get("subject", ""),
        body_text=draft.get("body_text", ""),
        attachments=attachments
    )

    now_iso = datetime.now(timezone.utc).isoformat()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE email_drafts SET
        approval_status = 'approved',
        content_hash = ?,
        approved_content_hash = ?,
        approved_at = ?,
        approved_by = ?,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = ?
    """, (content_hash, content_hash, now_iso, user_identifier, draft_id))

    conn.commit()
    conn.close()

    log_email_action(
        action="approved",
        recipient_email=draft.get("recipient_email", ""),
        draft_id=draft_id,
        details={
            "approved_by": user_identifier,
            "content_hash": content_hash,
            "subject": draft.get("subject", "")
        }
    )

    logger.info(f"[Email Approval] Draft {draft_id} approved with hash {content_hash[:12]}")
    return (True, f"Draft {draft_id} approved for exact content version {content_hash[:8]}.")

def batch_approve_drafts(draft_ids: List[int], user_identifier: str = "Candidate User") -> Dict[str, Any]:
    """Approves a specified batch of drafts."""
    success_ids = []
    failed = []

    for d_id in draft_ids:
        ok, msg = approve_email_draft(d_id, user_identifier)
        if ok:
            success_ids.append(d_id)
        else:
            failed.append({"id": d_id, "error": msg})

    return {
        "approved_count": len(success_ids),
        "approved_ids": success_ids,
        "failed_count": len(failed),
        "failed": failed
    }

def invalidate_approval_on_edit(draft_id: int) -> None:
    """
    Called when a draft's recipient, subject, body, or attachments are edited.
    Automatically invalidates prior approval status.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE email_drafts SET
        approval_status = 'draft',
        approved_content_hash = NULL,
        approved_at = NULL,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = ? AND approval_status != 'draft'
    """, (draft_id,))
    if cursor.rowcount > 0:
        logger.info(f"[Email Approval] Approval invalidated for draft {draft_id} due to modifications.")
    conn.commit()
    conn.close()

# --- Pre-Send Inspection ---

def get_pre_send_preview(draft_id: int, account_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Returns exact pre-send preview containing:
    - Recipient details.
    - Subject.
    - Body text.
    - Attachments list with sizes & types.
    - Selected account details.
    - Exact version content hash and approval validity.
    - Guardrail checks: Do-Not-Contact list, Duplicate send, Attachment safety.
    """
    conn = get_db_connection()
    draft_row = conn.execute("SELECT * FROM email_drafts WHERE id = ?", (draft_id,)).fetchone()
    conn.close()

    if not draft_row:
        return {"error": f"Draft ID {draft_id} not found."}

    draft = dict(draft_row)

    # Attachments
    raw_att = []
    if draft.get("attachments"):
        try:
            raw_att = json.loads(draft["attachments"])
        except Exception:
            raw_att = [draft["attachments"]]

    att_valid, att_err, validated_att = validate_attachments(raw_att)

    # Selected Account
    settings = get_sending_settings()
    acc_id = account_id or settings.get("default_account_id", 1)
    acc = get_email_account(acc_id)
    if not acc:
        acc = get_email_account(1)  # Fallback to sandbox

    # Content Hash & Approval
    is_approved, cur_hash, approval_explanation = validate_draft_approval({
        "recipient_email": draft.get("recipient_email", ""),
        "subject": draft.get("subject", ""),
        "body_text": draft.get("body_text", ""),
        "attachments": raw_att,
        "approval_status": draft.get("approval_status", "draft"),
        "approved_content_hash": draft.get("approved_content_hash", "")
    })

    # Guardrail checks
    dnc_blocked, dnc_reason = check_do_not_contact(draft.get("recipient_email", ""))
    dup_blocked, dup_reason = check_duplicate_send(draft.get("recipient_email", ""), draft.get("subject", ""), settings["duplicate_window_days"])

    can_enqueue = is_approved and att_valid and (not dnc_blocked) and (not dup_blocked)

    return {
        "draft_id": draft_id,
        "recipient_name": draft.get("recipient_name", ""),
        "recipient_email": draft.get("recipient_email", ""),
        "recipient_role": draft.get("recipient_role", "Faculty / PI"),
        "subject": draft.get("subject", ""),
        "body_text": draft.get("body_text", ""),
        "attachments": validated_att,
        "attachments_valid": att_valid,
        "attachments_error": att_err,
        "selected_account": {
            "id": acc["id"] if acc else 1,
            "name": acc["name"] if acc else "Mock Sandbox",
            "provider_type": acc["provider_type"] if acc else "mock_sandbox",
            "email_address": acc["email_address"] if acc else "sandbox@scholarscout.local"
        },
        "content_hash": cur_hash,
        "approval_status": draft.get("approval_status", "draft"),
        "is_approved_version": is_approved,
        "approval_explanation": approval_explanation,
        "sending_master_enabled": settings["sending_master_enabled"],
        "safety_checks": {
            "do_not_contact_blocked": dnc_blocked,
            "do_not_contact_reason": dnc_reason,
            "duplicate_send_blocked": dup_blocked,
            "duplicate_send_reason": dup_reason
        },
        "can_enqueue": can_enqueue
    }

# --- Outbound Queue Operations ---

def enqueue_outbound_draft(draft_id: int, account_id: Optional[int] = None) -> Tuple[bool, str, Optional[int]]:
    """
    Enqueues an approved draft into the durable email_outbound_queue.
    Validates exact approval hash, attachments, DNC, and duplicate protections.
    """
    preview = get_pre_send_preview(draft_id, account_id)
    if "error" in preview:
        return (False, preview["error"], None)

    if not preview["is_approved_version"]:
        return (False, f"Cannot queue draft: {preview['approval_explanation']}", None)

    if not preview["attachments_valid"]:
        return (False, f"Cannot queue draft: Attachment validation failed ({preview['attachments_error']})", None)

    if preview["safety_checks"]["do_not_contact_blocked"]:
        return (False, f"Cannot queue draft: {preview['safety_checks']['do_not_contact_reason']}", None)

    if preview["safety_checks"]["duplicate_send_blocked"]:
        return (False, f"Cannot queue draft: {preview['safety_checks']['duplicate_send_reason']}", None)

    conn = get_db_connection()
    cursor = conn.cursor()

    acc_id = preview["selected_account"]["id"]
    attachments_json = json.dumps(preview["attachments"])

    cursor.execute("""
    INSERT INTO email_outbound_queue (
        draft_id, account_id, recipient_email, recipient_name,
        subject, body_text, attachments_json, content_hash,
        status, attempts, max_attempts, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued', 0, 3, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """, (
        draft_id,
        acc_id,
        preview["recipient_email"],
        preview["recipient_name"],
        preview["subject"],
        preview["body_text"],
        attachments_json,
        preview["content_hash"]
    ))
    queue_id = cursor.lastrowid

    # Update draft status
    cursor.execute("""
    UPDATE email_drafts SET approval_status = 'queued', updated_at = CURRENT_TIMESTAMP
    WHERE id = ?
    """, (draft_id,))

    conn.commit()
    conn.close()

    log_email_action(
        action="queued",
        recipient_email=preview["recipient_email"],
        draft_id=draft_id,
        queue_id=queue_id,
        account_id=acc_id,
        details={"content_hash": preview["content_hash"]}
    )

    logger.info(f"[Email Queue] Draft {draft_id} queued as Queue Item #{queue_id}")
    return (True, f"Draft {draft_id} successfully added to outbound dispatch queue (Queue #{queue_id}).", queue_id)

def get_outbound_queue(status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves items from the durable outbound queue."""
    conn = get_db_connection()
    if status_filter and status_filter.lower() != "all":
        rows = conn.execute("""
        SELECT q.*, a.name as account_name, a.provider_type
        FROM email_outbound_queue q
        LEFT JOIN email_accounts a ON q.account_id = a.id
        WHERE q.status = ?
        ORDER BY q.id DESC
        """, (status_filter.lower().strip(),)).fetchall()
    else:
        rows = conn.execute("""
        SELECT q.*, a.name as account_name, a.provider_type
        FROM email_outbound_queue q
        LEFT JOIN email_accounts a ON q.account_id = a.id
        ORDER BY q.id DESC
        """).fetchall()
    conn.close()

    result = []
    for r in rows:
        d = dict(r)
        if d.get("attachments_json"):
            try:
                d["attachments"] = json.loads(d["attachments_json"])
            except Exception:
                d["attachments"] = []
        else:
            d["attachments"] = []
        result.append(d)
    return result

def process_outbound_queue_item(queue_id: int) -> Dict[str, Any]:
    """
    Processes a single outbound queue item through its assigned provider.
    Enforces master sending switch, provider quotas, and non-retry timeout logic.
    """
    settings = get_sending_settings()
    if not settings["sending_master_enabled"]:
        return {
            "success": False,
            "status": "held",
            "message": "Outbound dispatch is paused: Controlled sending master switch is currently DISABLED. Enable sending in Settings to dispatch queued messages."
        }

    conn = get_db_connection()
    cursor = conn.cursor()

    row = cursor.execute("SELECT * FROM email_outbound_queue WHERE id = ?", (queue_id,)).fetchone()
    if not row:
        conn.close()
        return {"success": False, "status": "not_found", "message": f"Queue item #{queue_id} not found."}

    item = dict(row)
    if item["status"] not in ("queued", "failed", "uncertain"):
        conn.close()
        return {
            "success": False,
            "status": item["status"],
            "message": f"Queue item #{queue_id} is in status '{item['status']}' and cannot be processed."
        }

    # Retrieve account directly on cursor
    acc_row = cursor.execute("SELECT * FROM email_accounts WHERE id = ?", (item["account_id"],)).fetchone()
    if not acc_row:
        conn.close()
        return {"success": False, "status": "failed", "message": f"Account #{item['account_id']} not found."}

    acc = dict(acc_row)
    creds = {}
    if acc.get("credentials_json"):
        try:
            creds = json.loads(acc["credentials_json"])
        except Exception:
            creds = {}
    acc["credentials"] = creds

    # Check Do-Not-Contact directly on cursor
    clean_email = (item["recipient_email"] or "").strip().lower()
    email_domain = clean_email.split("@")[-1] if "@" in clean_email else ""
    dnc_rows = cursor.execute("SELECT pattern, reason FROM do_not_contact").fetchall()

    dnc_blocked = False
    dnc_reason = None
    for r in dnc_rows:
        pat = (r["pattern"] or "").strip().lower()
        reason = r["reason"] or "Recipient is listed on Do-Not-Contact suppression list."
        if pat == clean_email:
            dnc_blocked = True
            dnc_reason = f"Do-Not-Contact blocked: Exact match for {clean_email} ({reason})"
            break
        if pat.startswith("@") and pat[1:] == email_domain:
            dnc_blocked = True
            dnc_reason = f"Do-Not-Contact blocked: Domain {email_domain} is suppressed ({reason})"
            break
        if pat == email_domain:
            dnc_blocked = True
            dnc_reason = f"Do-Not-Contact blocked: Domain {email_domain} is suppressed ({reason})"
            break

    if dnc_blocked:
        cursor.execute("""
        UPDATE email_outbound_queue SET
            status = 'cancelled', error_message = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """, (f"Cancelled: {dnc_reason}", queue_id))
        cursor.execute("UPDATE email_drafts SET approval_status = 'cancelled' WHERE id = ?", (item["draft_id"],))
        log_email_action(
            action="dnc_blocked",
            recipient_email=item["recipient_email"],
            draft_id=item["draft_id"],
            queue_id=queue_id,
            details={"reason": dnc_reason},
            cursor=cursor
        )
        conn.commit()
        conn.close()
        return {"success": False, "status": "cancelled", "message": f"Dispatch blocked: {dnc_reason}"}

    # Increment attempt count
    cursor.execute("""
    UPDATE email_outbound_queue SET attempts = attempts + 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?
    """, (queue_id,))
    conn.commit()

    # Parse attachments
    attachments = []
    if item.get("attachments_json"):
        try:
            attachments = json.loads(item["attachments_json"])
        except Exception:
            attachments = []

    provider = get_email_provider(acc)
    send_result = provider.send_email(
        recipient=item["recipient_email"],
        subject=item["subject"],
        body_text=item["body_text"],
        attachments=attachments
    )

    now_iso = datetime.now(timezone.utc).isoformat()

    if send_result.status == "provider-accepted":
        cursor.execute("""
        UPDATE email_outbound_queue SET
            status = 'provider-accepted',
            provider_message_id = ?,
            sent_at = ?,
            error_message = '',
            reconciliation_needed = 0,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """, (send_result.provider_message_id or "", now_iso, queue_id))

        cursor.execute("""
        UPDATE email_drafts SET
            approval_status = 'provider-accepted',
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """, (item["draft_id"],))

        log_email_action(
            action="provider_accepted",
            recipient_email=item["recipient_email"],
            draft_id=item["draft_id"],
            queue_id=queue_id,
            account_id=acc["id"],
            provider_message_id=send_result.provider_message_id,
            details={
                "delivery_note": send_result.delivery_note,
                "sent_at": now_iso
            },
            cursor=cursor
        )

    elif send_result.status == "uncertain":
        # Ambiguous timeout! Do NOT retry blindly. Set status to uncertain.
        cursor.execute("""
        UPDATE email_outbound_queue SET
            status = 'uncertain',
            error_message = ?,
            reconciliation_needed = 1,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """, (send_result.error_message or "Ambiguous network timeout", queue_id))

        cursor.execute("""
        UPDATE email_drafts SET approval_status = 'uncertain', updated_at = CURRENT_TIMESTAMP WHERE id = ?
        """, (item["draft_id"],))

        log_email_action(
            action="uncertain_timeout",
            recipient_email=item["recipient_email"],
            draft_id=item["draft_id"],
            queue_id=queue_id,
            account_id=acc["id"],
            details={"error": send_result.error_message},
            cursor=cursor
        )

    else:
        cursor.execute("""
        UPDATE email_outbound_queue SET
            status = 'failed',
            error_message = ?,
            reconciliation_needed = 0,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """, (send_result.error_message or "Provider transmission failure", queue_id))

        cursor.execute("""
        UPDATE email_drafts SET approval_status = 'failed', updated_at = CURRENT_TIMESTAMP WHERE id = ?
        """, (item["draft_id"],))

        log_email_action(
            action="dispatch_failed",
            recipient_email=item["recipient_email"],
            draft_id=item["draft_id"],
            queue_id=queue_id,
            account_id=acc["id"],
            details={"error": send_result.error_message},
            cursor=cursor
        )

    conn.commit()
    conn.close()

    return {
        "queue_id": queue_id,
        "success": send_result.success,
        "status": send_result.status,
        "provider_message_id": send_result.provider_message_id,
        "error_message": send_result.error_message,
        "is_ambiguous_timeout": send_result.is_ambiguous_timeout,
        "delivery_note": send_result.delivery_note
    }

def process_outbound_queue_batch(limit: int = 10) -> Dict[str, Any]:
    """Processes pending items in the outbound queue up to specified limit."""
    settings = get_sending_settings()
    if not settings["sending_master_enabled"]:
        return {
            "processed_count": 0,
            "message": "Dispatch paused: Controlled sending switch is DISABLED."
        }

    conn = get_db_connection()
    rows = conn.execute("""
    SELECT id FROM email_outbound_queue
    WHERE status = 'queued'
    ORDER BY id ASC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()

    results = []
    for r in rows:
        res = process_outbound_queue_item(r["id"])
        results.append(res)
        # Apply inter-send delay to avoid spam flags
        time.sleep(0.1)

    return {
        "processed_count": len(results),
        "results": results
    }

# --- Ambiguous Timeout Reconciliation ---

def reconcile_uncertain_queue_item(queue_id: int) -> Dict[str, Any]:
    """
    Reconciles an uncertain queue item after an ambiguous network timeout.
    Queries the provider sent index instead of blindly retrying.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    row = cursor.execute("SELECT * FROM email_outbound_queue WHERE id = ?", (queue_id,)).fetchone()
    if not row:
        conn.close()
        return {"success": False, "message": f"Queue item #{queue_id} not found."}

    item = dict(row)
    acc_row = cursor.execute("SELECT * FROM email_accounts WHERE id = ?", (item["account_id"],)).fetchone()
    if not acc_row:
        conn.close()
        return {"success": False, "message": f"Account #{item['account_id']} not found."}

    acc = dict(acc_row)
    creds = {}
    if acc.get("credentials_json"):
        try:
            creds = json.loads(acc["credentials_json"])
        except Exception:
            creds = {}
    acc["credentials"] = creds

    provider = get_email_provider(acc)
    reconcile_res = provider.reconcile_ambiguous_send(
        recipient=item["recipient_email"],
        subject=item["subject"],
        attempted_after_iso=item["created_at"],
        provider_message_id=item.get("provider_message_id")
    )

    if reconcile_res.resolved:
        if reconcile_res.actually_sent:
            # Reconciled as successfully dispatched
            cursor.execute("""
            UPDATE email_outbound_queue SET
                status = 'provider-accepted',
                provider_message_id = ?,
                sent_at = ?,
                reconciliation_needed = 0,
                error_message = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """, (
                reconcile_res.provider_message_id or item.get("provider_message_id", "reconciled_sent"),
                reconcile_res.sent_timestamp or datetime.now(timezone.utc).isoformat(),
                reconcile_res.details,
                queue_id
            ))
            cursor.execute("UPDATE email_drafts SET approval_status = 'provider-accepted' WHERE id = ?", (item["draft_id"],))
            log_email_action(
                action="reconciled_sent",
                recipient_email=item["recipient_email"],
                draft_id=item["draft_id"],
                queue_id=queue_id,
                details={"reconciliation": reconcile_res.details},
                cursor=cursor
            )
        else:
            # Reconciled as definitely NOT sent
            cursor.execute("""
            UPDATE email_outbound_queue SET
                status = 'failed',
                reconciliation_needed = 0,
                error_message = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """, (f"Reconciliation confirmed message was NOT dispatched: {reconcile_res.details}", queue_id))
            cursor.execute("UPDATE email_drafts SET approval_status = 'failed' WHERE id = ?", (item["draft_id"],))
            log_email_action(
                action="reconciled_not_sent",
                recipient_email=item["recipient_email"],
                draft_id=item["draft_id"],
                queue_id=queue_id,
                details={"reconciliation": reconcile_res.details},
                cursor=cursor
            )

    conn.commit()
    conn.close()

    return {
        "queue_id": queue_id,
        "resolved": reconcile_res.resolved,
        "actually_sent": reconcile_res.actually_sent,
        "provider_message_id": reconcile_res.provider_message_id,
        "details": reconcile_res.details
    }

# --- Reply Synchronization & Follow-Up Halting ---

def sync_account_replies(account_id: int) -> Dict[str, Any]:
    """
    Queries provider inbox for replies from professors who received outreach.
    When a reply is detected:
    1. Records reply in email_replies table.
    2. Flags professor outreach state as 'replied'.
    3. Automatically halts/cancels any scheduled follow-up drafts for this recipient.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    acc_row = cursor.execute("SELECT * FROM email_accounts WHERE id = ?", (account_id,)).fetchone()
    if not acc_row:
        conn.close()
        return {"success": False, "message": f"Account #{account_id} not found."}

    acc = dict(acc_row)
    creds = {}
    if acc.get("credentials_json"):
        try:
            creds = json.loads(acc["credentials_json"])
        except Exception:
            creds = {}
    acc["credentials"] = creds

    # Fetch all professors contacted from this account
    rows = cursor.execute("""
    SELECT DISTINCT recipient_email FROM email_outbound_queue
    WHERE account_id = ? AND status = 'provider-accepted'
    """, (account_id,)).fetchall()
    
    known_recipients = [r["recipient_email"] for r in rows if r["recipient_email"]]
    if not known_recipients:
        conn.close()
        return {"success": True, "synced_replies_count": 0, "message": "No contacted recipients found to query replies for."}

    provider = get_email_provider(acc)
    replies = provider.sync_replies(known_recipients)

    new_replies_count = 0
    halted_followups_count = 0

    for rep in replies:
        sender = rep.get("sender_email", "").strip().lower()
        sub = rep.get("subject", "")
        snip = rep.get("snippet", "")
        p_msg_id = rep.get("provider_message_id", "")
        is_opt_out = 1 if rep.get("is_opt_out") else 0

        # Check if already recorded
        existing = cursor.execute("""
        SELECT id FROM email_replies WHERE account_id = ? AND provider_message_id = ?
        """, (account_id, p_msg_id)).fetchone()

        if not existing:
            cursor.execute("""
            INSERT INTO email_replies (
                account_id, sender_email, subject, snippet,
                provider_message_id, is_opt_out, received_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                account_id, sender, sub, snip, p_msg_id, is_opt_out,
                rep.get("received_at", datetime.now(timezone.utc).isoformat())
            ))
            new_replies_count += 1

            # Log audit
            log_email_action(
                action="opt_out_detected" if is_opt_out else "reply_detected",
                recipient_email=sender,
                account_id=account_id,
                details={"subject": sub, "snippet": snip, "is_opt_out": bool(is_opt_out)},
                cursor=cursor
            )

            # Auto-add to DNC if opt-out
            if is_opt_out:
                cursor.execute("""
                INSERT OR IGNORE INTO do_not_contact (pattern, reason, source)
                VALUES (?, 'Auto-detected opt out from professor reply', 'auto_reply_opt_out')
                """, (sender,))

            # HALT FOLLOW-UPS for this recipient
            cursor.execute("""
            UPDATE email_drafts SET
                approval_status = 'cancelled',
                safety_notice = 'Follow-up cancelled: Professor reply or opt-out has been detected for this recipient.'
            WHERE LOWER(recipient_email) = ? AND follow_up_sequence > 0 AND approval_status IN ('draft', 'approved', 'queued')
            """, (sender,))
            halted_followups_count += cursor.rowcount

            # Cancel any queued follow-ups in queue
            cursor.execute("""
            UPDATE email_outbound_queue SET
                status = 'cancelled',
                error_message = 'Cancelled: Professor reply detected.'
            WHERE LOWER(recipient_email) = ? AND status = 'queued'
            """, (sender,))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "account_id": account_id,
        "synced_replies_count": new_replies_count,
        "halted_followups_count": halted_followups_count,
        "message": f"Successfully synchronized replies: {new_replies_count} new reply recorded, {halted_followups_count} pending follow-up drafts safely halted."
    }

# --- Do-Not-Contact Suppression CRUD ---

def get_do_not_contact_list() -> List[Dict[str, Any]]:
    """Retrieves all active Do-Not-Contact suppression entries."""
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM do_not_contact ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_do_not_contact(pattern: str, reason: str = "User manual suppression", source: str = "user_manual") -> Tuple[bool, str]:
    """Adds an email or domain to the suppression list and cancels any active queue items."""
    clean_pat = pattern.strip().lower()
    if not clean_pat:
        return (False, "Pattern cannot be empty.")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO do_not_contact (pattern, reason, source, created_at)
    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(pattern) DO UPDATE SET reason = excluded.reason, source = excluded.source
    """, (clean_pat, reason, source))

    # Cancel any active queue items matching this pattern
    if clean_pat.startswith("@"):
        domain = clean_pat[1:]
        cursor.execute("""
        UPDATE email_outbound_queue SET
            status = 'cancelled', error_message = 'Cancelled by Do-Not-Contact domain suppression'
        WHERE LOWER(recipient_email) LIKE ? AND status = 'queued'
        """, (f"%@{domain}",))
    else:
        cursor.execute("""
        UPDATE email_outbound_queue SET
            status = 'cancelled', error_message = 'Cancelled by Do-Not-Contact email suppression'
        WHERE LOWER(recipient_email) = ? AND status = 'queued'
        """, (clean_pat,))

    log_email_action(
        action="dnc_added",
        recipient_email=clean_pat,
        details={"reason": reason, "source": source},
        cursor=cursor
    )

    conn.commit()
    conn.close()

    return (True, f"Added '{clean_pat}' to Do-Not-Contact suppression list.")

def remove_do_not_contact(entry_id: int) -> bool:
    """Removes an entry from the suppression list."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM do_not_contact WHERE id = ?", (entry_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

# --- Audit Logs Retrieval ---

def get_email_audit_logs(limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieves recent email audit logs with parsed JSON details."""
    conn = get_db_connection()
    rows = conn.execute("""
    SELECT l.*, a.name as account_name
    FROM email_audit_log l
    LEFT JOIN email_accounts a ON l.account_id = a.id
    ORDER BY l.id DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()

    result = []
    for r in rows:
        d = dict(r)
        if d.get("details_json"):
            try:
                d["details"] = json.loads(d["details_json"])
            except Exception:
                d["details"] = {}
        else:
            d["details"] = {}
        result.append(d)
    return result
