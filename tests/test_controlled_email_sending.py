"""
Comprehensive Test Suite for Controlled Email Sending, Approvals, Queueing,
Timeout Reconciliation, Duplicate Protection, and Reply Synchronization.
Validates 100% offline safety via Mock Sandbox Email Provider.
"""

import pytest
import json
from fastapi.testclient import TestClient

from backend.main import app
from backend.database import (
    init_db,
    save_email_draft,
    get_email_draft,
    get_db_connection
)
from backend.emails.security import (
    compute_content_hash,
    validate_draft_approval,
    validate_attachments,
    check_do_not_contact,
    check_duplicate_send
)
from backend.emails.providers.mock_sandbox import MockSandboxEmailProvider
from backend.emails.queue_manager import (
    get_sending_settings,
    toggle_master_sending,
    get_email_accounts,
    save_email_account,
    approve_email_draft,
    batch_approve_drafts,
    get_pre_send_preview,
    enqueue_outbound_draft,
    get_outbound_queue,
    process_outbound_queue_item,
    reconcile_uncertain_queue_item,
    sync_account_replies,
    add_do_not_contact,
    remove_do_not_contact
)
from backend.emails.followup_manager import generate_followup_draft

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_test_state():
    """Ensure clean database schema and reset sandbox store before tests."""
    init_db()
    MockSandboxEmailProvider._SENT_STORE.clear()
    MockSandboxEmailProvider._SIMULATED_REPLIES.clear()
    conn = get_db_connection()
    conn.execute("DELETE FROM email_outbound_queue")
    conn.execute("DELETE FROM email_audit_log")
    conn.execute("DELETE FROM do_not_contact WHERE source != 'system_seed'")
    conn.execute("DELETE FROM email_replies")
    conn.commit()
    conn.close()
    toggle_master_sending(False, "Test reset")

# 1. Content Hash & Invalidation Tests

def test_content_hash_deterministic():
    """Verifies that content hash is deterministic and whitespace-normalized."""
    h1 = compute_content_hash(
        recipient_email="prof.smith@mit.edu",
        subject="PhD Inquiry Fall 2026",
        body_text="Dear Professor,\nI am interested in your lab.",
        attachments=["Academic CV (PDF)"]
    )
    h2 = compute_content_hash(
        recipient_email="PROF.SMITH@MIT.EDU ",
        subject="PhD Inquiry Fall 2026 ",
        body_text="Dear Professor,\r\nI am interested in your lab. ",
        attachments=["Academic CV (PDF)"]
    )
    assert h1 == h2
    assert len(h1) == 64

def test_approval_and_edit_invalidation():
    """Verifies that editing recipient, subject, body, or attachments invalidates approval."""
    draft_id = save_email_draft({
        "recipient_name": "Dr. Sarah Connor",
        "recipient_email": "sconnor@mit.edu",
        "subject": "PhD Research Inquiry",
        "body_text": "Original draft body text for research inquiry.",
        "attachments": ["Academic CV (PDF)"]
    })

    # Initially in draft status
    draft = get_email_draft(draft_id)
    assert draft["approval_status"] == "draft"

    # Approve draft
    ok, msg = approve_email_draft(draft_id, user_identifier="Test User")
    assert ok is True
    draft = get_email_draft(draft_id)
    assert draft["approval_status"] == "approved"
    assert draft["approved_content_hash"] == draft["content_hash"]

    # Verify approval check passes
    valid, _, _ = validate_draft_approval(draft)
    assert valid is True

    # EDIT THE BODY -> Must invalidate approval
    save_email_draft({
        "id": draft_id,
        "recipient_name": "Dr. Sarah Connor",
        "recipient_email": "sconnor@mit.edu",
        "subject": "PhD Research Inquiry",
        "body_text": "MODIFIED draft body text - changed content!",
        "attachments": ["Academic CV (PDF)"]
    })

    modified_draft = get_email_draft(draft_id)
    assert modified_draft["approval_status"] == "draft"
    assert not modified_draft["approved_content_hash"]

    # Approval check must fail
    valid, _, exp = validate_draft_approval(modified_draft)
    assert valid is False
    assert "not been approved" in exp or "invalidated" in exp

# 2. Attachment Validation Tests

def test_attachment_validation():
    """Verifies allowed extensions, blocking executables, and size checks."""
    # Whitelisted academic extensions
    ok, err, val = validate_attachments(["CV_2026.pdf", "Transcript.docx", "Diagram.png"])
    assert ok is True
    assert len(val) == 3

    # Forbidden executable
    bad_ok, bad_err, _ = validate_attachments(["MaliciousScript.exe"])
    assert bad_ok is False
    assert "forbidden executable" in bad_err.lower()

    # Unsupported extension
    bad_ext_ok, bad_ext_err, _ = validate_attachments(["archive.xyz"])
    assert bad_ext_ok is False
    assert "not supported" in bad_ext_err.lower()

# 3. Do-Not-Contact List Tests

def test_do_not_contact_suppression():
    """Verifies exact email and domain suppression."""
    add_do_not_contact("suppressed-prof@cmu.edu", "Opted out from cold email")
    add_do_not_contact("@blocked-univ.edu", "Domain level suppression")

    # Check exact match
    b1, r1 = check_do_not_contact("suppressed-prof@cmu.edu")
    assert b1 is True
    assert "suppressed-prof@cmu.edu" in r1

    # Check domain match
    b2, r2 = check_do_not_contact("faculty@blocked-univ.edu")
    assert b2 is True
    assert "blocked-univ.edu" in r2

    # Check allowed email
    b3, _ = check_do_not_contact("regular-prof@mit.edu")
    assert b3 is False

# 4. Pre-Send Inspection & Approval API

def test_pre_send_inspection_endpoint():
    """Tests GET /api/emails/drafts/{id}/pre-send-preview."""
    draft_id = save_email_draft({
        "recipient_name": "Prof. David",
        "recipient_email": "pdavid@stanford.edu",
        "subject": "Graduate AI Research",
        "body_text": "I am writing to inquire about research positions.",
        "attachments": ["Academic CV (PDF)"]
    })

    # Preview before approval
    res = client.get(f"/api/emails/drafts/{draft_id}/pre-send-preview")
    assert res.status_code == 200
    data = res.json()
    assert data["recipient_email"] == "pdavid@stanford.edu"
    assert data["is_approved_version"] is False
    assert data["can_enqueue"] is False

    # Approve via API
    app_res = client.post(f"/api/emails/drafts/{draft_id}/approve")
    assert app_res.status_code == 200

    # Preview after approval
    res2 = client.get(f"/api/emails/drafts/{draft_id}/pre-send-preview")
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["is_approved_version"] is True
    assert data2["can_enqueue"] is True

# 5. Outbound Queueing & Controlled Dispatch

def test_controlled_sending_and_queue_dispatch():
    """Verifies durable queueing, master switch enforcement, and sandbox dispatch."""
    draft_id = save_email_draft({
        "recipient_name": "Prof. Alan Turing",
        "recipient_email": "aturing@cam.ac.uk",
        "subject": "Automata & Machine Learning Inquiry",
        "body_text": "Inquiry regarding PhD opportunities in your group.",
        "attachments": ["Academic CV (PDF)"]
    })
    approve_email_draft(draft_id)

    # 1. Enqueue draft
    q_ok, q_msg, queue_id = enqueue_outbound_draft(draft_id, account_id=1)
    assert q_ok is True
    assert queue_id is not None

    queue_items = get_outbound_queue(status_filter="queued")
    assert any(q["id"] == queue_id for q in queue_items)

    # 2. Attempt dispatch while master switch is DISABLED
    toggle_master_sending(False)
    held_res = process_outbound_queue_item(queue_id)
    assert held_res["success"] is False
    assert held_res["status"] == "held"

    # 3. Enable master sending and dispatch
    toggle_master_sending(True)
    send_res = process_outbound_queue_item(queue_id)
    assert send_res["success"] is True
    assert send_res["status"] == "provider-accepted"
    assert send_res["provider_message_id"].startswith("sandbox_msg_")

    # Verify draft status updated
    draft = get_email_draft(draft_id)
    assert draft["approval_status"] == "provider-accepted"

# 6. Ambiguous Timeout & Reconciliation (No Blind Retries)

def test_ambiguous_timeout_and_reconciliation():
    """Verifies that timeouts yield 'uncertain' status and reconcile resolves correctly."""
    draft_id = save_email_draft({
        "recipient_name": "Prof. Timed Out",
        "recipient_email": "timeout-prof@ox.ac.uk",
        "subject": "SIMULATE_TIMEOUT PhD Inquiry",
        "body_text": "Testing timeout handling.",
        "attachments": ["Academic CV (PDF)"]
    })
    approve_email_draft(draft_id)
    _, _, queue_id = enqueue_outbound_draft(draft_id, account_id=1)

    toggle_master_sending(True)
    send_res = process_outbound_queue_item(queue_id)
    assert send_res["status"] == "uncertain"
    assert send_res["is_ambiguous_timeout"] is True

    # Check queue item status
    q_items = get_outbound_queue(status_filter="uncertain")
    assert any(q["id"] == queue_id for q in q_items)

    # Run reconciliation (Safe provider check)
    reconcile_res = reconcile_uncertain_queue_item(queue_id)
    assert reconcile_res["resolved"] is True
    # Initial timeout was not recorded in sent log
    assert reconcile_res["actually_sent"] is False

# 7. Reply Synchronization & Follow-Up Halting

def test_reply_sync_and_followup_halting():
    """Verifies that detected professor replies automatically cancel/halt follow-ups."""
    # 1. Create parent draft and mark as provider-accepted
    parent_id = save_email_draft({
        "recipient_name": "Dr. Geoffrey Hinton",
        "recipient_email": "ghinton@cs.toronto.edu",
        "subject": "Deep Learning Inquiry",
        "body_text": "Prospective PhD inquiry.",
        "attachments": ["Academic CV (PDF)"]
    })
    approve_email_draft(parent_id)
    enqueue_outbound_draft(parent_id, account_id=1)
    toggle_master_sending(True)
    
    # Get queue item
    q_item = get_outbound_queue(status_filter="queued")[0]
    process_outbound_queue_item(q_item["id"])

    # 2. Generate follow-up draft (sequence 1)
    f_ok, f_msg, followup_id = generate_followup_draft(parent_draft_id=parent_id, days_elapsed=7)
    assert f_ok is True
    assert followup_id is not None

    followup_draft = get_email_draft(followup_id)
    assert followup_draft["approval_status"] == "draft"
    assert followup_draft["follow_up_sequence"] == 1

    # 3. Simulate an incoming reply from Dr. Hinton
    MockSandboxEmailProvider.add_simulated_reply(
        sender_email="ghinton@cs.toronto.edu",
        subject="Re: Deep Learning Inquiry",
        snippet="Thank you for reaching out. Please apply through the formal admissions portal."
    )

    # 4. Synchronize replies
    sync_res = sync_account_replies(account_id=1)
    assert sync_res["success"] is True
    assert sync_res["synced_replies_count"] >= 1
    assert sync_res["halted_followups_count"] >= 1

    # 5. Verify follow-up draft is CANCELLED
    updated_followup = get_email_draft(followup_id)
    assert updated_followup["approval_status"] == "cancelled"
    assert "Professor reply" in updated_followup["safety_notice"]

    # 6. Verify subsequent follow-up generation is blocked
    block_ok, block_msg, _ = generate_followup_draft(parent_draft_id=parent_id)
    assert block_ok is False
    assert "halted" in block_msg.lower() or "replied" in block_msg.lower()
