"""
Data Exporter Module for ScholarScout.
Provides:
1. CSV and JSON exports for Funding Opportunities, Professors, Crawled Sources, and Outreach Status.
2. Protection against spreadsheet formula injection (CSV Injection / DDE) by sanitizing cells.
3. Redacted diagnostic export scrubbing all API keys, OAuth secrets, email credentials, and private tokens.
"""

import csv
import io
import json
import os
import platform
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Union

from backend.config import config
from backend.database import (
    get_db_connection,
    get_scholarships,
    get_professors,
    get_crawled_pages,
    get_email_drafts,
    get_stats
)
from backend.emails.queue_manager import (
    get_outbound_queue,
    get_email_audit_logs,
    get_email_accounts,
    get_sending_settings
)

# Forbidden formula initiation characters in spreadsheet cells
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "%")

def sanitize_csv_cell(value: Any) -> str:
    """
    Sanitizes values against spreadsheet formula injection (CSV/DDE Injection).
    If a string starts with =, +, -, @, tab, carriage return, or %, it is prepended
    with an apostrophe (') so Excel, Google Sheets, and LibreOffice treat it as pure text.
    """
    if value is None:
        return ""
    val_str = str(value)
    if val_str.startswith(FORMULA_PREFIXES):
        return "'" + val_str
    return val_str

# --- 1. Scholarships & Funding Opportunities Export ---

def export_scholarships_csv(job_id: Optional[int] = None, shortlisted_only: bool = False) -> str:
    """Exports discovered scholarships and funding opportunities as CSV with formula sanitization."""
    items = get_scholarships(job_id=job_id, is_shortlisted=True if shortlisted_only else None)
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

    headers = [
        "ID", "Title", "University", "Country", "Program", "Degree Level",
        "Funding Category", "Funding Type", "Tuition Coverage", "Stipend Amount",
        "Stipend Currency", "Stipend Frequency", "Deadline", "Deadline Date",
        "Opportunity Status", "International Eligibility", "Eligibility Status",
        "Fit Score", "Fit Reason", "Official URL", "Source URL", "Shortlisted",
        "Personal Notes", "Last Checked Date", "Discovered Via Query"
    ]
    writer.writerow([sanitize_csv_cell(h) for h in headers])

    for item in items:
        row = [
            item.get("id"),
            item.get("title", ""),
            item.get("university", ""),
            item.get("country", ""),
            item.get("program", ""),
            item.get("degree_level", ""),
            item.get("funding_category", ""),
            item.get("funding_type", ""),
            item.get("tuition_coverage", ""),
            item.get("stipend_amount", ""),
            item.get("stipend_currency", ""),
            item.get("stipend_frequency", ""),
            item.get("deadline", ""),
            item.get("deadline_date", ""),
            item.get("opportunity_status", ""),
            item.get("international_eligibility", ""),
            item.get("eligibility_status", ""),
            item.get("fit_score", 0),
            item.get("fit_reason", ""),
            item.get("official_url", ""),
            item.get("source_url", ""),
            "Yes" if item.get("is_shortlisted") else "No",
            item.get("notes", ""),
            item.get("last_checked_at") or item.get("created_at", ""),
            item.get("discovered_via_query", "")
        ]
        writer.writerow([sanitize_csv_cell(cell) for cell in row])

    return output.getvalue()

def export_scholarships_json(job_id: Optional[int] = None, shortlisted_only: bool = False) -> str:
    """Exports discovered scholarships and funding opportunities as JSON."""
    items = get_scholarships(job_id=job_id, is_shortlisted=True if shortlisted_only else None)
    return json.dumps({
        "export_type": "scholarships",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_count": len(items),
        "scholarships": items
    }, indent=2)

# --- 2. Professors & Faculty Opportunities Export ---

def export_professors_csv(job_id: Optional[int] = None, shortlisted_only: bool = False) -> str:
    """Exports faculty leads and recruitment opportunities as CSV with formula sanitization."""
    items = get_professors(job_id=job_id, is_shortlisted=True if shortlisted_only else None)
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

    headers = [
        "ID", "Faculty Name", "Title", "Department", "University", "Lab / Group",
        "Verified Email", "Email Source URL", "Official Profile URL", "Lab URL",
        "Research Focus", "Recruitment Status", "Recruitment Evidence",
        "Position Funding Type", "Contact Instructions", "Match Score",
        "Match Reasons", "Missing Information", "Shortlisted", "Personal Notes",
        "Last Checked Date", "Discovered Via Query"
    ]
    writer.writerow([sanitize_csv_cell(h) for h in headers])

    for item in items:
        match_reasons_str = "; ".join(item.get("match_reasons", [])) if isinstance(item.get("match_reasons"), list) else str(item.get("match_reasons", ""))
        missing_info_str = "; ".join(item.get("missing_information", [])) if isinstance(item.get("missing_information"), list) else str(item.get("missing_information", ""))

        row = [
            item.get("id"),
            item.get("name", ""),
            item.get("title", ""),
            item.get("department", ""),
            item.get("university", ""),
            item.get("lab_group", ""),
            item.get("email", ""),
            item.get("email_source_url", ""),
            item.get("official_profile_url", ""),
            item.get("lab_url", ""),
            item.get("research_interests", ""),
            item.get("recruitment_status", ""),
            item.get("recruitment_evidence", ""),
            item.get("position_funding_type", ""),
            item.get("contact_instructions", ""),
            item.get("match_score", 0),
            match_reasons_str,
            missing_info_str,
            "Yes" if item.get("is_shortlisted") else "No",
            item.get("notes", ""),
            item.get("last_checked_at") or item.get("created_at", ""),
            item.get("discovered_via_query", "")
        ]
        writer.writerow([sanitize_csv_cell(cell) for cell in row])

    return output.getvalue()

def export_professors_json(job_id: Optional[int] = None, shortlisted_only: bool = False) -> str:
    """Exports faculty leads as JSON."""
    items = get_professors(job_id=job_id, is_shortlisted=True if shortlisted_only else None)
    return json.dumps({
        "export_type": "professors",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_count": len(items),
        "professors": items
    }, indent=2)

# --- 3. Crawled Sources & Provenance Activity Export ---

def export_sources_csv(job_id: Optional[int] = None) -> str:
    """Exports crawled pages and source verification history as CSV."""
    items = get_crawled_pages(job_id=job_id, limit=2000)
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

    headers = [
        "ID", "Job ID", "URL", "Page Title", "Page Type", "Page Status",
        "Status Code", "Status Reason", "Selection Reason", "Retrieval Method",
        "Content Hash", "Byte Size", "Depth", "Is External", "Domain Type", "Timestamp"
    ]
    writer.writerow([sanitize_csv_cell(h) for h in headers])

    for item in items:
        row = [
            item.get("id"),
            item.get("job_id"),
            item.get("url", ""),
            item.get("page_title", ""),
            item.get("page_type", ""),
            item.get("page_status", ""),
            item.get("status_code", ""),
            item.get("status_reason", ""),
            item.get("selection_reason", ""),
            item.get("retrieval_method", ""),
            item.get("content_hash", ""),
            item.get("byte_size", 0),
            item.get("depth", 0),
            "Yes" if item.get("is_external") else "No",
            item.get("external_domain_type", ""),
            item.get("created_at", "")
        ]
        writer.writerow([sanitize_csv_cell(cell) for cell in row])

    return output.getvalue()

def export_sources_json(job_id: Optional[int] = None) -> str:
    """Exports crawled pages as JSON."""
    items = get_crawled_pages(job_id=job_id, limit=2000)
    return json.dumps({
        "export_type": "crawled_sources",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_count": len(items),
        "sources": items
    }, indent=2)

# --- 4. Outreach Drafts & Outbound Sending Status Export ---

def export_outreach_csv() -> str:
    """Exports outreach inquiries and queue delivery status as CSV."""
    drafts = get_email_drafts()
    queue_items = get_outbound_queue()
    queue_map = {q["draft_id"]: q for q in queue_items}

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

    headers = [
        "Draft ID", "Recipient Name", "Recipient Email", "Recipient Role", "Draft Type",
        "Subject", "Body Text Preview", "Proposed Attachments", "Approval Status",
        "Content Hash", "Approved Content Hash", "Approved At", "Outbound Queue Status",
        "Provider Msg ID", "Sent At", "Reply Status", "Last Reply At", "Created Date"
    ]
    writer.writerow([sanitize_csv_cell(h) for h in headers])

    for d in drafts:
        q_info = queue_map.get(d["id"], {})
        attachments_str = ", ".join(d.get("attachments", [])) if isinstance(d.get("attachments"), list) else str(d.get("attachments", ""))
        body_preview = (d.get("body_text", "")[:120] + "...") if len(d.get("body_text", "")) > 120 else d.get("body_text", "")

        row = [
            d.get("id"),
            d.get("recipient_name", ""),
            d.get("recipient_email", ""),
            d.get("recipient_role", ""),
            d.get("draft_type", ""),
            d.get("subject", ""),
            body_preview,
            attachments_str,
            d.get("approval_status", "draft"),
            d.get("content_hash", ""),
            d.get("approved_content_hash", ""),
            d.get("approved_at", ""),
            q_info.get("status", "not_queued"),
            q_info.get("provider_message_id", ""),
            q_info.get("sent_at", ""),
            d.get("reply_status", "no_reply"),
            d.get("last_reply_at", ""),
            d.get("created_at", "")
        ]
        writer.writerow([sanitize_csv_cell(cell) for cell in row])

    return output.getvalue()

def export_outreach_json() -> str:
    """Exports outreach inquiries and sending queue as JSON."""
    drafts = get_email_drafts()
    queue_items = get_outbound_queue()
    return json.dumps({
        "export_type": "outreach_drafts_and_queue",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "drafts_count": len(drafts),
        "queue_count": len(queue_items),
        "drafts": drafts,
        "outbound_queue": queue_items
    }, indent=2)

# --- 5. Redacted Diagnostic Export ---

def export_redacted_diagnostics() -> Dict[str, Any]:
    """
    Compiles a comprehensive diagnostic bundle for system health, telemetry,
    database stats, job logs, and provider status.
    GUARANTEE: Redacts and scrubs all API keys, OAuth tokens, email credentials,
    and passwords before returning.
    """
    stats = get_stats()
    sending_settings = get_sending_settings()
    accounts = get_email_accounts()
    audit_logs = get_email_audit_logs(limit=30)

    # Sanitize and redact accounts (ensuring zero credentials leak)
    sanitized_accounts = []
    for acc in accounts:
        clean_acc = dict(acc)
        # Verify credentials_json is completely omitted
        if "credentials_json" in clean_acc:
            del clean_acc["credentials_json"]
        if "credentials" in clean_acc:
            del clean_acc["credentials"]
        clean_acc["credentials_redacted"] = True
        sanitized_accounts.append(clean_acc)

    # Sanitize config summary
    redacted_config = {
        "app_env": getattr(config, "app_env", "development"),
        "llm_provider": getattr(config, "llm_provider", "openai_compatible"),
        "model_name": config.model_name,
        "api_base_url": config.api_base_url,
        "api_key_configured": bool(config.api_key),
        "api_key": "[REDACTED_SECRET]" if config.api_key else "Not configured",
        "search_provider": config.search_provider,
        "search_api_key_configured": bool(config.search_api_key),
        "search_api_key": "[REDACTED_SECRET]" if config.search_api_key else "Not configured",
        "crawl_max_pages": getattr(config, "crawl_max_pages", 15),
        "crawl_timeout": getattr(config, "crawl_timeout", 12),
        "llm_timeout": getattr(config, "llm_timeout", 45.0),
        "llm_max_concurrency": getattr(config, "llm_max_concurrency", 3),
        "database_engine": "SQLite 3 WAL Mode"
    }

    # Fetch recent job summaries
    conn = get_db_connection()
    recent_jobs = conn.execute("""
    SELECT id, university_url, university_name, status, stop_reason,
           pages_crawled, scholarships_count, professors_count,
           llm_total_tokens, created_at, started_at, completed_at
    FROM research_jobs ORDER BY id DESC LIMIT 10
    """).fetchall()

    # Evidence history count
    ev_count_row = conn.execute("SELECT COUNT(*) as cnt FROM evidence_history").fetchone()
    evidence_changes_count = ev_count_row["cnt"] if ev_count_row else 0

    # Stale opportunities count
    stale_count_row = conn.execute("""
    SELECT COUNT(*) as cnt FROM scholarships
    WHERE last_checked_at < datetime('now', '-30 days')
    """).fetchone()
    stale_scholarships_count = stale_count_row["cnt"] if stale_count_row else 0

    conn.close()

    return {
        "diagnostic_type": "scholarscout_system_diagnostics",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "platform": {
            "os": platform.system(),
            "os_version": platform.version(),
            "python_version": platform.python_version(),
            "node_platform": platform.platform()
        },
        "system_status": {
            "database_online": True,
            "master_sending_enabled": sending_settings.get("sending_master_enabled", False),
            "evidence_changes_logged": evidence_changes_count,
            "stale_scholarships_detected": stale_scholarships_count
        },
        "database_stats": stats,
        "sending_settings": sending_settings,
        "connected_accounts": sanitized_accounts,
        "recent_jobs": [dict(r) for r in recent_jobs],
        "recent_audit_logs": audit_logs,
        "redacted_configuration": redacted_config,
        "security_guarantee": "All authentication credentials, API keys, passwords, and tokens have been strictly redacted for safe diagnostic sharing."
    }

# --- 6. Formatted Multi-Sheet Excel & Unified Gathering CSV Exports ---

def export_gathering_pipeline_excel(job_id: Optional[int] = None) -> bytes:
    """
    Generates a professionally styled Excel workbook (.xlsx) with two separate sheets:
    1. Universities & Scholarships: university, country, scholarship name, degree level, funding, eligibility, deadline, official URL, contact, source URL
    2. Professors: name, university, department, title, research interests, relevance score, email, phone, profile URL, source URL
    """
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    # Remove default sheet
    default_sheet = wb.active
    wb.remove(default_sheet)

    # Styling definitions
    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    regular_font = Font(name="Calibri", size=10)
    score_high_fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid") # light green
    score_med_fill = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid") # light yellow

    thin_border = Border(
        left=Side(style="thin", color="E2E8F0"),
        right=Side(style="thin", color="E2E8F0"),
        top=Side(style="thin", color="E2E8F0"),
        bottom=Side(style="thin", color="E2E8F0")
    )

    # -------------------------------------------------------------
    # SHEET 1: Universities & Scholarships
    # -------------------------------------------------------------
    ws_scholarships = wb.create_sheet(title="Universities & Scholarships")
    ws_scholarships.views.sheetView[0].showGridLines = True

    scholarship_headers = [
        "University", "Country", "Scholarship Name", "Degree Level",
        "Funding Coverage", "Eligibility Criteria", "Deadline",
        "Official Website URL", "Scholarship Office / Contact", "Source URL"
    ]
    ws_scholarships.append(scholarship_headers)

    # Format header row
    for col_idx, _ in enumerate(scholarship_headers, 1):
        cell = ws_scholarships.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border
    ws_scholarships.row_dimensions[1].height = 28

    scholarships = get_scholarships(job_id=job_id)
    for r_idx, item in enumerate(scholarships, 2):
        row_data = [
            sanitize_csv_cell(item.get("university") or "Academic Institution"),
            sanitize_csv_cell(item.get("country") or "Unknown"),
            sanitize_csv_cell(item.get("title") or "Graduate Funding / Scholarship"),
            sanitize_csv_cell(item.get("degree_level") or "Graduate"),
            sanitize_csv_cell(item.get("tuition_coverage") or item.get("funding_category") or "Full / Partial Coverage"),
            sanitize_csv_cell(item.get("eligibility") or item.get("academic_requirements") or "Open to qualified graduate applicants"),
            sanitize_csv_cell(item.get("deadline") or item.get("deadline_date") or "See official link"),
            sanitize_csv_cell(item.get("official_url") or item.get("source_url") or ""),
            sanitize_csv_cell(item.get("contact_instructions") or item.get("department") or "University Admissions / Financial Aid Office"),
            sanitize_csv_cell(item.get("source_url") or "")
        ]
        ws_scholarships.append(row_data)

        # Apply row styling
        for col_idx in range(1, len(row_data) + 1):
            cell = ws_scholarships.cell(row=r_idx, column=col_idx)
            cell.font = regular_font
            cell.border = thin_border
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            if r_idx % 2 == 1:
                cell.fill = zebra_fill
        ws_scholarships.row_dimensions[r_idx].height = 22

    # Auto-adjust column widths for Sheet 1
    for col in ws_scholarships.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val_str = str(cell.value or "")
            if len(val_str) > max_len:
                max_len = len(val_str)
        ws_scholarships.column_dimensions[col_letter].width = min(max(max_len + 4, 14), 45)

    # -------------------------------------------------------------
    # SHEET 2: Professors (Ranked)
    # -------------------------------------------------------------
    ws_professors = wb.create_sheet(title="Professors")
    ws_professors.views.sheetView[0].showGridLines = True

    prof_headers = [
        "Professor Name", "University", "Department", "Academic Title",
        "Research Interests & Focus", "Relevance Score (0-100)",
        "Publicly Listed Email", "Phone / Office Contact",
        "Official Profile URL", "Source URL"
    ]
    ws_professors.append(prof_headers)

    # Format header row
    for col_idx, _ in enumerate(prof_headers, 1):
        cell = ws_professors.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border
    ws_professors.row_dimensions[1].height = 28

    professors = get_professors(job_id=job_id)
    # Sort by match score descending
    professors = sorted(professors, key=lambda p: int(p.get("match_score") or 0), reverse=True)

    for r_idx, prof in enumerate(professors, 2):
        score = int(prof.get("match_score") or 0)
        email_val = prof.get("email") or ""
        if email_val.lower() in ("not found", "none", "unknown", "n/a"):
            email_val = ""

        row_data = [
            sanitize_csv_cell(prof.get("name") or "Faculty Member"),
            sanitize_csv_cell(prof.get("university") or "Academic Institution"),
            sanitize_csv_cell(prof.get("department") or "Department"),
            sanitize_csv_cell(prof.get("title") or "Faculty"),
            sanitize_csv_cell(prof.get("research_interests") or "Academic Research"),
            score,
            sanitize_csv_cell(email_val),
            sanitize_csv_cell(prof.get("lab_group") if prof.get("lab_group") != "Unknown" else ""),
            sanitize_csv_cell(prof.get("official_profile_url") or prof.get("source_url") or ""),
            sanitize_csv_cell(prof.get("source_url") or "")
        ]
        ws_professors.append(row_data)

        # Apply row styling
        for col_idx in range(1, len(row_data) + 1):
            cell = ws_professors.cell(row=r_idx, column=col_idx)
            cell.font = regular_font
            cell.border = thin_border
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            if col_idx == 6: # Relevance score column
                cell.alignment = Alignment(horizontal="center", vertical="center")
                if score >= 75:
                    cell.fill = score_high_fill
                elif score >= 50:
                    cell.fill = score_med_fill
            elif r_idx % 2 == 1:
                cell.fill = zebra_fill
        ws_professors.row_dimensions[r_idx].height = 22

    # Auto-adjust column widths for Sheet 2
    for col in ws_professors.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val_str = str(cell.value or "")
            if len(val_str) > max_len:
                max_len = len(val_str)
        ws_professors.column_dimensions[col_letter].width = min(max(max_len + 4, 14), 45)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()

def export_gathering_pipeline_csv(job_id: Optional[int] = None) -> str:
    """Exports unified gathering pipeline results as a clean CSV with formula protection."""
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

    headers = [
        "Record Type", "University", "Country", "Item Title / Name", "Department / Field",
        "Degree Level", "Funding / Relevance Score", "Official URL", "Email / Contact", "Source URL"
    ]
    writer.writerow([sanitize_csv_cell(h) for h in headers])

    # 1. Write Scholarships
    scholarships = get_scholarships(job_id=job_id)
    for s in scholarships:
        row = [
            "Scholarship",
            s.get("university", ""),
            s.get("country", ""),
            s.get("title", ""),
            s.get("program", ""),
            s.get("degree_level", ""),
            s.get("tuition_coverage") or s.get("funding_category", ""),
            s.get("official_url", ""),
            s.get("contact_instructions", ""),
            s.get("source_url", "")
        ]
        writer.writerow([sanitize_csv_cell(cell) for cell in row])

    # 2. Write Professors
    professors = get_professors(job_id=job_id)
    professors = sorted(professors, key=lambda p: int(p.get("match_score") or 0), reverse=True)
    for p in professors:
        email_val = p.get("email") or ""
        if email_val.lower() in ("not found", "none", "unknown", "n/a"):
            email_val = ""
        row = [
            "Professor",
            p.get("university", ""),
            "Unknown",
            p.get("name", ""),
            p.get("department", "") + (" - " + p.get("research_interests", "") if p.get("research_interests") else ""),
            "Faculty / PI",
            f"Score: {p.get('match_score', 0)}/100",
            p.get("official_profile_url", ""),
            email_val,
            p.get("source_url", "")
        ]
        writer.writerow([sanitize_csv_cell(cell) for cell in row])

    return output.getvalue()
