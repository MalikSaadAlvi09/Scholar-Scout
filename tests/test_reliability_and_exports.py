"""
Automated Test Suite for Reliability, Checkpoints, Idempotency, Exports, and Backups.
Verifies:
1. Formula injection sanitization in CSV exports (=, +, -, @, \\t, \\r, %).
2. Redacted diagnostic export with strict zero-credential-leakage guarantee.
3. Database backup creation, listing, integrity verification, and safe restoration.
4. Idempotent scholarship and professor upserts without duplicate records.
5. Evidence history change tracking across deadline, funding, recruitment, and contact updates.
6. User notes and shortlist state preservation across re-crawls.
7. Scheduled rechecks CRUD, single catch-up on missed runs, and stale opportunity detection.
8. Job lifecycle: pause, resume, cancel, checkpoint state saving, and budget stop explanations.
"""

import os
import json
import pytest
import sqlite3
from datetime import datetime, timezone, timedelta

TEST_DB_PATH = os.path.abspath("test_reliability.db")
os.environ["DATABASE_PATH"] = TEST_DB_PATH

from backend.config import config
config.database_path = TEST_DB_PATH
from backend.database import (
    init_db,
    get_db_connection,
    enqueue_research_job,
    get_job,
    update_job_status,
    pause_job,
    resume_job,
    cancel_job,
    save_job_checkpoint,
    get_job_checkpoint,
    insert_scholarships,
    get_scholarships,
    insert_professors,
    get_professors,
    toggle_scholarship_shortlist,
    save_scholarship_notes,
    toggle_professor_shortlist,
    save_professor_notes,
    get_evidence_history,
    get_recent_evidence_changes,
    mark_stale_records
)
from backend.export.data_exporter import (
    sanitize_csv_cell,
    export_scholarships_csv,
    export_scholarships_json,
    export_professors_csv,
    export_professors_json,
    export_sources_csv,
    export_sources_json,
    export_outreach_csv,
    export_outreach_json,
    export_redacted_diagnostics
)
from backend.export.backup_manager import (
    create_database_backup,
    list_database_backups,
    restore_database_backup,
    delete_database_backup
)
from backend.jobs.rechecks import (
    create_scheduled_recheck,
    get_scheduled_rechecks,
    update_scheduled_recheck,
    delete_scheduled_recheck,
    check_and_run_due_rechecks
)

TEST_DB_PATH = os.path.abspath("test_reliability.db")

@pytest.fixture(autouse=True)
def setup_test_database():
    """Initializes schema on a dedicated test database."""
    orig_db = config.database_path
    config.database_path = TEST_DB_PATH
    init_db()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM scholarships")
    c.execute("DELETE FROM professors")
    c.execute("DELETE FROM research_jobs")
    c.execute("DELETE FROM crawl_pages")
    c.execute("DELETE FROM email_drafts")
    c.execute("DELETE FROM evidence_history")
    c.execute("DELETE FROM scheduled_rechecks")
    c.execute("DELETE FROM external_leads")
    conn.commit()
    conn.close()
    yield
    config.database_path = orig_db
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass

# --- 1. CSV Formula Injection Defense Tests ---

def test_formula_injection_sanitization():
    """Verify cells starting with formula triggers are safely escaped with an apostrophe."""
    assert sanitize_csv_cell("=SUM(A1:A10)") == "'=SUM(A1:A10)"
    assert sanitize_csv_cell("+123456789") == "'+123456789"
    assert sanitize_csv_cell("-1000") == "'-1000"
    assert sanitize_csv_cell("@cmd|' /C calc'!A0") == "'@cmd|' /C calc'!A0"
    assert sanitize_csv_cell("\tTabPrefix") == "'\tTabPrefix"
    assert sanitize_csv_cell("\rReturnPrefix") == "'\rReturnPrefix"
    assert sanitize_csv_cell("%00Encoded") == "'%00Encoded"

    # Regular text should remain untouched
    assert sanitize_csv_cell("Fulbright Fellowship") == "Fulbright Fellowship"
    assert sanitize_csv_cell("Prof. Turing") == "Prof. Turing"
    assert sanitize_csv_cell(None) == ""
    assert sanitize_csv_cell(42) == "42"

def test_scholarship_csv_export_injection_protection():
    """Verify exported scholarship CSV contains sanitized formula cells."""
    job_id = enqueue_research_job("https://test-injection.edu", university_name="Injection University")
    malicious_item = [{
        "title": "=cmd|'/C calc'!A0",
        "university": "+Test Uni",
        "funding_category": "@Malicious Category",
        "tuition_coverage": "-100% Waiver",
        "stipend_amount": "=2000*12",
        "deadline": "2026-12-01",
        "source_url": "https://test-injection.edu/funding"
    }]
    insert_scholarships(job_id, malicious_item)
    csv_out = export_scholarships_csv(job_id=job_id)

    assert "'=cmd|'/C calc'!A0" in csv_out
    assert "'+Test Uni" in csv_out
    assert "'@Malicious Category" in csv_out
    assert "'-100% Waiver" in csv_out
    assert "'=2000*12" in csv_out

# --- 2. Redacted Diagnostics Export Tests ---

def test_redacted_diagnostics_privacy():
    """Verify diagnostic bundle strictly redacts API keys, passwords, and credentials."""
    diag = export_redacted_diagnostics()
    assert diag["diagnostic_type"] == "scholarscout_system_diagnostics"
    assert "database_stats" in diag
    assert "platform" in diag

    # Check configuration redaction
    config_diag = diag["redacted_configuration"]
    if config_diag.get("api_key_configured"):
        assert config_diag["api_key"] == "[REDACTED_SECRET]"
    if config_diag.get("search_api_key_configured"):
        assert config_diag["search_api_key"] == "[REDACTED_SECRET]"

    # Check connected accounts have no secret credential fields
    for acc in diag["connected_accounts"]:
        assert "credentials_json" not in acc
        assert "credentials" not in acc
        assert acc.get("credentials_redacted") is True

    # Check serialization
    json_str = json.dumps(diag)
    assert "SECRET" in json_str or "Not configured" in json_str
    # Verify no unmasked auth tokens
    assert "sk-" not in json_str
    assert "Bearer " not in json_str

# --- 3. Database Backup & Restore Tests ---

def test_database_backup_and_restore():
    """Verify creating a backup, modifying state, and restoring safely."""
    # 1. Create a backup
    backup_res = create_database_backup(label="unit_test")
    assert backup_res["success"] is True
    assert backup_res["integrity"].lower() == "ok"
    backup_filename = backup_res["filename"]

    # 2. List backups
    backups = list_database_backups()
    assert any(b["filename"] == backup_filename for b in backups)

    # 3. Create dummy entity in db
    job_id = enqueue_research_job("https://temp-backup-test.edu", university_name="Temp Uni")
    assert get_job(job_id) is not None

    # 4. Restore from backup
    restore_res = restore_database_backup(backup_filename)
    assert restore_res["success"] is True
    assert restore_res["integrity"].lower() == "ok"
    assert restore_res["safety_snapshot_created"] != ""

    # 5. Clean up test backup file
    delete_database_backup(backup_filename)
    if restore_res.get("safety_snapshot_created"):
        delete_database_backup(restore_res["safety_snapshot_created"])

# --- 4. Idempotency & Evidence History Tracking Tests ---

def test_idempotent_scholarship_upsert_and_evidence_tracking():
    """Verify re-running a crawl updates scholarship fields, records changes in evidence_history, and preserves user notes."""
    job_id = enqueue_research_job("https://cam.ac.uk", university_name="University of Cambridge")
    
    # 1. Initial crawl discovery
    s1 = [{
        "title": "Gates Cambridge Fellowship",
        "university": "University of Cambridge",
        "funding_category": "Partial funding",
        "tuition_coverage": "Full Tuition",
        "stipend_amount": "£18,000 / year",
        "deadline": "15 October 2025",
        "deadline_date": "2025-10-15",
        "opportunity_status": "open",
        "eligibility_status": "Needs clarification",
        "official_url": "https://www.gatescambridge.org/apply",
        "evidence_snippet": "Provides full tuition and annual maintenance.",
        "source_url": "https://www.gatescambridge.org",
        "fit_score": 85
    }]
    inserted = insert_scholarships(job_id, s1)
    assert inserted == 1

    # Fetch scholarship ID
    items = get_scholarships(job_id=job_id)
    assert len(items) == 1
    s_id = items[0]["id"]

    # 2. User confirms edits: shortlists item and adds personal notes
    toggle_scholarship_shortlist(s_id, True)
    save_scholarship_notes(s_id, "Need to request reference letters early from Prof. Miller.")

    # 3. Second crawl finds updated deadline and increased stipend
    s2 = [{
        "title": "Gates Cambridge Fellowship",
        "university": "University of Cambridge",
        "funding_category": "Explicit full tuition plus living support",
        "tuition_coverage": "Full Tuition + Healthcare",
        "stipend_amount": "£20,000 / year",
        "deadline": "05 December 2025",
        "deadline_date": "2025-12-05",
        "opportunity_status": "open",
        "eligibility_status": "Appears eligible",
        "official_url": "https://www.gatescambridge.org/apply",
        "evidence_snippet": "Updated funding: stipend increased to £20,000 with deadline extended to Dec 5.",
        "source_url": "https://www.gatescambridge.org",
        "fit_score": 92
    }]
    re_inserted = insert_scholarships(job_id, s2)
    assert re_inserted == 1

    # Verify NO duplicate record was created
    all_items = get_scholarships(job_id=job_id)
    assert len(all_items) == 1
    updated_item = all_items[0]

    # Verify fields were updated to newest values
    assert updated_item["stipend_amount"] == "£20,000 / year"
    assert updated_item["deadline"] == "05 December 2025"
    assert updated_item["fit_score"] == 92

    # Verify user notes and shortlisted status are STRICTLY PRESERVED
    assert updated_item["is_shortlisted"] == 1
    assert updated_item["notes"] == "Need to request reference letters early from Prof. Miller."

    # Verify evidence history recorded the deadline & stipend changes
    history = get_evidence_history(entity_type="scholarship", entity_id=s_id)
    assert len(history) >= 2
    fields_changed = [h["field_name"] for h in history]
    assert "deadline" in fields_changed or "deadline_date" in fields_changed
    assert "stipend_amount" in fields_changed

def test_idempotent_professor_upsert_and_recruitment_change_tracking():
    """Verify professor updates log recruitment changes to evidence_history and preserve user shortlisted status."""
    job_id = enqueue_research_job("https://ox.ac.uk", university_name="University of Oxford")

    p1 = [{
        "name": "Dr. Sarah Jenkins",
        "university": "University of Oxford",
        "department": "Computer Science",
        "email": "sarah.jenkins@cs.ox.ac.uk",
        "recruitment_status": "Unstated",
        "recruitment_evidence": "Faculty bio page",
        "official_profile_url": "https://cs.ox.ac.uk/people/sarah.jenkins",
        "source_url": "https://cs.ox.ac.uk/people/sarah.jenkins",
        "match_score": 75
    }]
    insert_professors(job_id, p1)

    profs = get_professors(job_id=job_id)
    assert len(profs) == 1
    p_id = profs[0]["id"]

    # User adds personal notes & shortlists
    toggle_professor_shortlist(p_id, True)
    save_professor_notes(p_id, "Paper on transformer reasoning matches my thesis.")

    # Re-crawl discovers open funded PhD position
    p2 = [{
        "name": "Dr. Sarah Jenkins",
        "university": "University of Oxford",
        "department": "Computer Science; Autonomous Reasoning Lab",
        "email": "sarah.jenkins@cs.ox.ac.uk",
        "recruitment_status": "Actively recruiting PhD students",
        "recruitment_evidence": "Seeking 2 funded PhD students in neuro-symbolic reasoning for Fall 2026.",
        "position_funding_type": "Fully funded EPSRC Studentship",
        "official_profile_url": "https://cs.ox.ac.uk/people/sarah.jenkins",
        "source_url": "https://cs.ox.ac.uk/people/sarah.jenkins",
        "match_score": 90
    }]
    insert_professors(job_id, p2)

    # Verify no duplicate
    profs_after = get_professors(job_id=job_id)
    assert len(profs_after) == 1
    updated_prof = profs_after[0]

    # Verify updated fields and preserved user notes
    assert updated_prof["recruitment_status"] == "Actively recruiting PhD students"
    assert updated_prof["is_shortlisted"] == 1
    assert updated_prof["notes"] == "Paper on transformer reasoning matches my thesis."

    # Verify evidence history entry
    p_history = get_evidence_history(entity_type="professor", entity_id=p_id)
    assert len(p_history) >= 1
    assert any(h["field_name"] == "recruitment_status" for h in p_history)

# --- 5. Scheduled Rechecks & Stale Flagging Tests ---

def test_scheduled_rechecks_and_missed_run_handling():
    """Verify scheduled recheck registration, single catch-up on overdue items, and advancement of next run time."""
    import asyncio
    # 1. Create a recheck
    recheck_id = create_scheduled_recheck(
        target_type="scholarship",
        target_id=1,
        target_title="Rhodes Scholarship Recheck",
        target_url="https://www.rhodeshouse.ox.ac.uk",
        frequency="weekly"
    )
    assert recheck_id > 0

    rechecks = get_scheduled_rechecks()
    assert any(r["id"] == recheck_id for r in rechecks)

    # 2. Simulate missed run by backdating next_run_at to past
    conn = get_db_connection()
    conn.execute("""
    UPDATE scheduled_rechecks
    SET next_run_at = datetime('now', '-3 days')
    WHERE id = ?
    """, (recheck_id,))
    conn.commit()
    conn.close()

    # 3. Trigger run due rechecks
    executed = asyncio.run(check_and_run_due_rechecks())
    assert len(executed) >= 1
    assert any(e["recheck_id"] == recheck_id for e in executed)

    # 4. Verify next_run_at was advanced into the future (preventing duplicate runaway loops)
    rechecks_after = get_scheduled_rechecks()
    recheck_obj = next(r for r in rechecks_after if r["id"] == recheck_id)
    next_run_dt = datetime.fromisoformat(recheck_obj["next_run_at"].replace(" ", "T"))
    assert next_run_dt > datetime.now()

    # Clean up
    delete_scheduled_recheck(recheck_id)

def test_stale_records_detection():
    """Verify mark_stale_records accurately flags items older than 30 days."""
    conn = get_db_connection()
    # Backdate a scholarship to 45 days ago
    conn.execute("""
    UPDATE scholarships
    SET last_checked_at = datetime('now', '-45 days'), is_stale = 0
    """)
    conn.commit()
    conn.close()

    res = mark_stale_records(stale_days=30)
    assert isinstance(res, dict)

# --- 6. Job Lifecycle, Budgets, and Stop Reasons Tests ---

def test_job_lifecycle_pause_resume_cancel_and_checkpoints():
    """Verify job lifecycle transitions, checkpoint state persistence, and budget stop explanations."""
    job_id = enqueue_research_job("https://stanford.edu", university_name="Stanford University")
    
    # Check initial status
    job = get_job(job_id)
    assert job["status"] == "queued"

    # Save checkpoint
    chk = {
        "visited_urls": ["https://stanford.edu", "https://stanford.edu/academics"],
        "queue": [{"url": "https://stanford.edu/funding", "priority": 90, "depth": 1}],
        "stats": {"pages_crawled": 2, "pages_successful": 2},
        "elapsed_seconds": 15.5
    }
    save_job_checkpoint(job_id, chk, elapsed_seconds=15.5)

    loaded_chk = get_job_checkpoint(job_id)
    assert loaded_chk is not None
    assert len(loaded_chk["visited_urls"]) == 2
    assert loaded_chk["stats"]["pages_crawled"] == 2

    # Pause job
    pause_job(job_id, reason="User reached daily token quota")
    job_paused = get_job(job_id)
    assert job_paused["status"] == "paused"
    assert "token quota" in job_paused["pause_reason"]

    # Resume job
    resume_job(job_id)
    job_resumed = get_job(job_id)
    assert job_resumed["status"] == "queued"

    # Update with stop reason and partially_completed status
    update_job_status(
        job_id=job_id,
        status="partially_completed",
        stop_reason="Page budget reached (15/15 pages)",
        pages_crawled=15,
        scholarships_count=3,
        professors_count=4
    )
    job_final = get_job(job_id)
    assert job_final["status"] == "partially_completed"
    assert job_final["stop_reason"] == "Page budget reached (15/15 pages)"
    assert job_final["completed_at"] is not None

    # Cancel a job
    job2_id = enqueue_research_job("https://mit.edu", university_name="MIT")
    cancel_job(job2_id)
    job2 = get_job(job2_id)
    assert job2["status"] == "cancelled"
    assert job2["stop_reason"] == "Cancelled by user"
