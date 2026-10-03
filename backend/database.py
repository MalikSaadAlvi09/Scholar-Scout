"""
Database Module for ScholarScout SQLite Storage.
Handles schema initialization, migrations, academic profiles with version history,
persistent research jobs, discovered scholarships, matching professors, and outreach drafts.
"""

import sqlite3
import json
import os
from urllib.parse import urlparse
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Union
from backend.config import config
from backend.logging_utils import logger

def get_db_connection() -> sqlite3.Connection:
    """Returns a thread-safe SQLite connection with dict-like row factory."""
    db_path = config.database_path
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    
    conn = sqlite3.connect(db_path, timeout=60.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 60000")
    return conn

def init_db():
    """Initializes the SQLite schema with all required tables and runs migrations."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. User Academic Profiles
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        nationality TEXT DEFAULT 'Unknown',
        current_residence TEXT DEFAULT 'Unknown',
        current_degree TEXT DEFAULT 'Unknown',
        current_institution TEXT DEFAULT 'Unknown',
        current_major TEXT NOT NULL,
        gpa TEXT NOT NULL,
        graduation_date TEXT DEFAULT 'Unknown',
        target_degree TEXT NOT NULL,
        broad_subject TEXT DEFAULT 'Unknown',
        target_field TEXT NOT NULL,
        research_interests TEXT NOT NULL,
        specific_interests TEXT DEFAULT '',
        preferred_countries TEXT DEFAULT '[]',
        excluded_countries TEXT DEFAULT '[]',
        intended_intake TEXT DEFAULT 'Unknown',
        english_tests TEXT DEFAULT 'Unknown',
        projects TEXT DEFAULT '',
        publications TEXT DEFAULT '',
        research_experience TEXT DEFAULT '',
        technical_skills TEXT DEFAULT '',
        background_summary TEXT,
        funding_needs TEXT DEFAULT '[]',
        funding_notes TEXT DEFAULT '',
        portfolio_url TEXT DEFAULT '',
        github_url TEXT DEFAULT '',
        website_url TEXT DEFAULT '',
        version INTEGER DEFAULT 1,
        country_of_origin TEXT DEFAULT 'Unknown',
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 2. Profile Version History Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS profile_versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        profile_id INTEGER NOT NULL,
        version INTEGER NOT NULL,
        snapshot_json TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
    )
    """)

    # 3. Persistent Research Jobs Queue
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS research_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        profile_id INTEGER,
        profile_version INTEGER DEFAULT 1,
        university_url TEXT NOT NULL,
        university_name TEXT,
        status TEXT DEFAULT 'queued', -- queued, running, completed, failed, cancelled
        current_step TEXT DEFAULT 'Job queued',
        progress_pct INTEGER DEFAULT 0,
        pages_crawled INTEGER DEFAULT 0,
        scholarships_count INTEGER DEFAULT 0,
        professors_count INTEGER DEFAULT 0,
        llm_requests_count INTEGER DEFAULT 0,
        llm_prompt_tokens INTEGER DEFAULT 0,
        llm_completion_tokens INTEGER DEFAULT 0,
        llm_total_tokens INTEGER DEFAULT 0,
        logs TEXT DEFAULT '[]',
        error_message TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        started_at TIMESTAMP,
        completed_at TIMESTAMP,
        FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE SET NULL
    )
    """)

    # 4. Discovered Scholarships and Funding Opportunities
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS scholarships (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER NOT NULL,
        profile_version INTEGER DEFAULT 1,
        title TEXT NOT NULL,
        university TEXT DEFAULT 'Unknown',
        country TEXT DEFAULT 'Unknown',
        program TEXT DEFAULT 'Unknown',
        degree_level TEXT DEFAULT 'Unknown',
        funding_category TEXT DEFAULT 'Unclear funding', -- Explicit full tuition plus living support, Tuition-only support, Partial funding, Conditional assistantship, Unclear funding
        funding_type TEXT DEFAULT 'Unknown',
        intake_and_year TEXT DEFAULT 'Unknown',
        international_eligibility TEXT DEFAULT 'Unknown',
        nationality_restrictions TEXT DEFAULT 'None stated',
        academic_requirements TEXT DEFAULT 'Unknown',
        tuition_coverage TEXT DEFAULT 'Unknown',
        stipend_amount TEXT DEFAULT 'Unknown',
        stipend_currency TEXT DEFAULT 'Unknown',
        stipend_frequency TEXT DEFAULT 'Unknown',
        amount TEXT DEFAULT 'Unknown',
        currency TEXT DEFAULT 'Unknown',
        funding_duration TEXT DEFAULT 'Unknown',
        insurance_and_travel TEXT DEFAULT 'None stated',
        other_costs TEXT DEFAULT 'Unknown',
        obligations TEXT DEFAULT 'Unknown',
        renewal_conditions TEXT DEFAULT 'Unknown',
        application_fee TEXT DEFAULT 'None stated',
        deadline TEXT DEFAULT 'Unknown',
        deadline_date TEXT DEFAULT 'Unknown',
        opportunity_status TEXT DEFAULT 'unknown', -- open, upcoming, closed, unknown
        application_route TEXT DEFAULT 'Unknown',
        official_url TEXT DEFAULT '',
        eligibility TEXT DEFAULT 'Unknown',
        eligibility_status TEXT DEFAULT 'Needs clarification', -- Appears eligible, Appears ineligible, Needs clarification
        eligibility_explanation TEXT DEFAULT '',
        department TEXT DEFAULT 'Unknown',
        evidence_snippet TEXT DEFAULT 'Unknown',
        claims_evidence TEXT DEFAULT '{}',
        source_url TEXT NOT NULL,
        fit_score INTEGER DEFAULT 0,
        fit_reason TEXT DEFAULT '',
        is_demo INTEGER DEFAULT 0,
        notes TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (job_id) REFERENCES research_jobs(id) ON DELETE CASCADE
    )
    """)

    # 5. Discovered Professors and Faculty Members
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS professors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER NOT NULL,
        profile_version INTEGER DEFAULT 1,
        name TEXT NOT NULL,
        title TEXT DEFAULT 'Unknown',
        department TEXT DEFAULT 'Unknown',
        university TEXT DEFAULT 'Unknown',
        lab_group TEXT DEFAULT 'Unknown',
        lab_url TEXT DEFAULT '',
        affiliation_evidence TEXT DEFAULT 'None stated in source',
        official_profile_url TEXT DEFAULT '',
        email TEXT DEFAULT 'Not found',
        email_source_url TEXT DEFAULT '',
        email_date_observed TEXT DEFAULT '',
        research_interests TEXT DEFAULT 'Unknown',
        publications_projects TEXT DEFAULT 'None stated in source',
        recruitment_status TEXT DEFAULT 'Unstated',
        recruitment_evidence TEXT DEFAULT 'None stated in source',
        position_funding_type TEXT DEFAULT 'Unstated',
        position_funding_evidence TEXT DEFAULT 'None stated in source',
        contact_instructions TEXT DEFAULT 'Standard academic inquiry',
        match_score INTEGER DEFAULT 0,
        research_overlap_score INTEGER DEFAULT 0,
        experience_fit_score INTEGER DEFAULT 0,
        degree_fit_score INTEGER DEFAULT 0,
        recruitment_fit_score INTEGER DEFAULT 0,
        match_reason TEXT DEFAULT '',
        match_reasons TEXT DEFAULT '[]',
        missing_information TEXT DEFAULT '[]',
        score_breakdown TEXT DEFAULT '{}',
        evidence_snippet TEXT DEFAULT 'Unknown',
        source_url TEXT NOT NULL,
        is_heuristic_score INTEGER DEFAULT 1,
        is_demo INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (job_id) REFERENCES research_jobs(id) ON DELETE CASCADE
    )
    """)

    # 6. Outreach Email Drafts (Sending strictly disabled)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS email_drafts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER,
        professor_id INTEGER,
        scholarship_id INTEGER,
        profile_version INTEGER DEFAULT 1,
        recipient_name TEXT NOT NULL,
        recipient_email TEXT NOT NULL,
        recipient_role TEXT DEFAULT 'Faculty / PI',
        draft_type TEXT DEFAULT 'Professor Research Inquiry',
        subject TEXT NOT NULL,
        body_text TEXT NOT NULL,
        can_send INTEGER DEFAULT 0,
        safety_notice TEXT DEFAULT 'Sending is disabled by default. Please review, edit, copy, and send from your academic email client.',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (job_id) REFERENCES research_jobs(id) ON DELETE CASCADE,
        FOREIGN KEY (professor_id) REFERENCES professors(id) ON DELETE SET NULL,
        FOREIGN KEY (scholarship_id) REFERENCES scholarships(id) ON DELETE SET NULL
    )
    """)

    # 6b. Editable Outreach Instructions & Template Settings
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS outreach_settings (
        id INTEGER PRIMARY KEY DEFAULT 1,
        purpose TEXT DEFAULT 'PhD Advisorship & Research Assistantship Inquiry',
        target_degree_intake TEXT DEFAULT 'Ph.D. in Computer Science (Fall 2026)',
        tone_and_length TEXT DEFAULT 'Professional, concise, scholarly; under 200 words',
        specific_request TEXT DEFAULT 'Request a brief 15-minute introductory video call to discuss potential research synergy and prospective Ph.D. opportunities.',
        background_to_emphasize TEXT DEFAULT 'Strong foundation in AI/ML research, 3.95 GPA, hands-on PyTorch engineering, and published work in NLP.',
        signature TEXT DEFAULT 'Sincerely,\n[Candidate Name]\nApplicant, Graduate Research\nEmail: candidate@alumni.univ.edu\nPortfolio: https://github.com/scholarscout-candidate',
        proposed_attachments TEXT DEFAULT 'Academic CV (PDF), Unofficial Transcript, 1-page Research Summary',
        optional_wording_preferences TEXT DEFAULT 'Focus strictly on specific lab publications and neuro-symbolic research; avoid generic flattery or assumptions about guaranteed funding.',
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 6c. Email Accounts for Controlled Sending (OAuth2 / Sandbox / Custom SMTP)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS email_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        provider_type TEXT NOT NULL, -- mock_sandbox, gmail_oauth, outlook_oauth, custom_smtp
        email_address TEXT NOT NULL,
        credentials_json TEXT DEFAULT '{}', -- Backend secure vault storage only
        is_active INTEGER DEFAULT 1,
        hourly_limit INTEGER DEFAULT 20,
        daily_limit INTEGER DEFAULT 100,
        delay_between_sends_sec INTEGER DEFAULT 15,
        reply_sync_enabled INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 6d. Durable Outbound Queue
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS email_outbound_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        draft_id INTEGER NOT NULL,
        account_id INTEGER NOT NULL,
        recipient_email TEXT NOT NULL,
        recipient_name TEXT DEFAULT '',
        subject TEXT NOT NULL,
        body_text TEXT NOT NULL,
        attachments_json TEXT DEFAULT '[]',
        content_hash TEXT NOT NULL,
        status TEXT DEFAULT 'queued', -- queued, provider-accepted, failed, uncertain, cancelled
        attempts INTEGER DEFAULT 0,
        max_attempts INTEGER DEFAULT 3,
        scheduled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        sent_at TIMESTAMP,
        provider_message_id TEXT DEFAULT '',
        error_message TEXT DEFAULT '',
        reconciliation_needed INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (draft_id) REFERENCES email_drafts(id) ON DELETE CASCADE,
        FOREIGN KEY (account_id) REFERENCES email_accounts(id) ON DELETE CASCADE
    )
    """)

    # 6e. Audit Log for Outbound Operations & Message IDs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS email_audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        draft_id INTEGER,
        queue_id INTEGER,
        account_id INTEGER,
        recipient_email TEXT NOT NULL,
        action TEXT NOT NULL,
        provider_message_id TEXT DEFAULT '',
        details_json TEXT DEFAULT '{}',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 6f. Do-Not-Contact (DNC) Suppression List
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS do_not_contact (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pattern TEXT NOT NULL UNIQUE, -- exact email or @domain.edu
        reason TEXT DEFAULT 'Explicit opt-out / user suppressed',
        source TEXT DEFAULT 'user_manual',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 6g. Synchronized Replies & Follow-Up Halting Log
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS email_replies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL,
        sender_email TEXT NOT NULL,
        subject TEXT DEFAULT '',
        snippet TEXT DEFAULT '',
        provider_message_id TEXT DEFAULT '',
        provider_thread_id TEXT DEFAULT '',
        is_opt_out INTEGER DEFAULT 0,
        received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (account_id) REFERENCES email_accounts(id) ON DELETE CASCADE
    )
    """)

    # 6h. System & Controlled Sending Global Settings
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 7. Discovered & Cached Pages (for crawl tracking)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS crawl_pages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER NOT NULL,
        url TEXT NOT NULL,
        normalized_url TEXT,
        page_title TEXT,
        page_type TEXT DEFAULT 'general', -- scholarships_funding, admissions_eligibility, degree_programs, departments, faculty_directories, research_labs, funded_positions, general
        page_status TEXT DEFAULT 'success', -- success, blocked, inaccessible, failed, scanned_document, skipped
        status_code INTEGER,
        status_reason TEXT DEFAULT '',
        selection_reason TEXT DEFAULT '',
        retrieval_method TEXT DEFAULT 'http', -- http, playwright, pdf, cache
        content_hash TEXT DEFAULT '',
        byte_size INTEGER DEFAULT 0,
        depth INTEGER DEFAULT 0,
        is_external INTEGER DEFAULT 0,
        external_domain_type TEXT DEFAULT 'official_university',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (job_id) REFERENCES research_jobs(id) ON DELETE CASCADE
    )
    """)

    # 8. Page Content Cache & Content Hash Storage
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS page_cache (
        url TEXT PRIMARY KEY,
        content_hash TEXT,
        status_code INTEGER,
        page_title TEXT,
        text_content TEXT,
        html_content TEXT,
        links_json TEXT,
        emails_json TEXT,
        retrieval_method TEXT DEFAULT 'http',
        created_at_epoch REAL
    )
    """)

    # 9. Discovered External Scholarship Providers & Third-Party Leads
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS external_leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER NOT NULL,
        domain TEXT NOT NULL,
        lead_title TEXT,
        url TEXT NOT NULL,
        lead_type TEXT DEFAULT 'external_lead', -- national_scholarship_agency, external_fellowship_foundation, government_grant_portal, external_lead
        context_snippet TEXT DEFAULT '',
        source_page_url TEXT DEFAULT '',
        status TEXT DEFAULT 'discovered', -- discovered, reviewed, approved, rejected
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (job_id) REFERENCES research_jobs(id) ON DELETE CASCADE
    )
    """)

    # 10. Search Query & Results Cache (Discovery Mode)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS search_cache (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        query_hash TEXT UNIQUE NOT NULL,
        query_text TEXT NOT NULL,
        provider TEXT NOT NULL,
        results_json TEXT NOT NULL,
        result_count INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 11. Tracked University Bookmarks and Personal Notes
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS university_bookmarks (
        domain TEXT PRIMARY KEY,
        university_name TEXT NOT NULL,
        country TEXT DEFAULT 'Unknown',
        lead_url TEXT DEFAULT '',
        is_shortlisted INTEGER DEFAULT 0,
        notes TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 12. Evidence History and Diff Tracking (Deadlines, funding, recruitment, contact info)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS evidence_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_type TEXT NOT NULL, -- 'scholarship', 'professor'
        entity_id INTEGER NOT NULL,
        field_name TEXT NOT NULL,
        old_value TEXT,
        new_value TEXT,
        old_evidence TEXT,
        new_evidence TEXT,
        source_url TEXT,
        job_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 13. Scheduled Rechecks for Shortlisted Opportunities
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS scheduled_rechecks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target_type TEXT NOT NULL, -- 'scholarship', 'professor', 'all_shortlisted'
        target_id INTEGER,
        target_title TEXT,
        target_url TEXT,
        frequency TEXT DEFAULT 'weekly',
        is_enabled INTEGER DEFAULT 1,
        last_run_at TIMESTAMP,
        next_run_at TIMESTAMP,
        last_status TEXT DEFAULT 'pending',
        last_job_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Run migrations for existing databases to add profile fields if missing
    existing_prof_cols = [row["name"] for row in cursor.execute("PRAGMA table_info(profiles)").fetchall()]
    prof_cols_to_add = [
        ("nationality", "TEXT DEFAULT 'Unknown'"),
        ("current_residence", "TEXT DEFAULT 'Unknown'"),
        ("current_degree", "TEXT DEFAULT 'Unknown'"),
        ("current_institution", "TEXT DEFAULT 'Unknown'"),
        ("graduation_date", "TEXT DEFAULT 'Unknown'"),
        ("broad_subject", "TEXT DEFAULT 'Unknown'"),
        ("specific_interests", "TEXT DEFAULT ''"),
        ("preferred_countries", "TEXT DEFAULT '[]'"),
        ("excluded_countries", "TEXT DEFAULT '[]'"),
        ("intended_intake", "TEXT DEFAULT 'Unknown'"),
        ("english_tests", "TEXT DEFAULT 'Unknown'"),
        ("projects", "TEXT DEFAULT ''"),
        ("publications", "TEXT DEFAULT ''"),
        ("research_experience", "TEXT DEFAULT ''"),
        ("technical_skills", "TEXT DEFAULT ''"),
        ("funding_needs", "TEXT DEFAULT '[]'"),
        ("funding_notes", "TEXT DEFAULT ''"),
        ("portfolio_url", "TEXT DEFAULT ''"),
        ("github_url", "TEXT DEFAULT ''"),
        ("website_url", "TEXT DEFAULT ''"),
        ("version", "INTEGER DEFAULT 1")
    ]
    for col, col_type in prof_cols_to_add:
        if col not in existing_prof_cols:
            try:
                cursor.execute(f"ALTER TABLE profiles ADD COLUMN {col} {col_type}")
            except Exception as mig_err:
                logger.warning(f"[DB Migration] Could not add profile column {col}: {mig_err}")

    # Run migrations for existing databases to add LLM tracking, discovery, budgets, and checkpoint columns to research_jobs
    existing_job_cols = [row["name"] for row in cursor.execute("PRAGMA table_info(research_jobs)").fetchall()]
    rj_cols_to_add = [
        ("profile_version", "INTEGER DEFAULT 1"),
        ("llm_requests_count", "INTEGER DEFAULT 0"),
        ("llm_prompt_tokens", "INTEGER DEFAULT 0"),
        ("llm_completion_tokens", "INTEGER DEFAULT 0"),
        ("llm_total_tokens", "INTEGER DEFAULT 0"),
        ("scope", "TEXT DEFAULT 'all'"),
        ("max_pages", "INTEGER DEFAULT 15"),
        ("max_depth", "INTEGER DEFAULT 3"),
        ("time_limit_seconds", "INTEGER DEFAULT 120"),
        ("job_type", "TEXT DEFAULT 'url_research'"),
        ("discovery_queries", "TEXT DEFAULT '[]'"),
        ("discovered_institutions", "TEXT DEFAULT '[]'"),
        ("coverage_report", "TEXT DEFAULT '{}'"),
        ("is_paused", "INTEGER DEFAULT 0"),
        ("pause_reason", "TEXT DEFAULT ''"),
        ("stop_reason", "TEXT DEFAULT ''"),
        ("time_budget_sec", "INTEGER DEFAULT 120"),
        ("page_budget", "INTEGER DEFAULT 15"),
        ("request_budget", "INTEGER DEFAULT 50"),
        ("token_budget", "INTEGER DEFAULT 100000"),
        ("elapsed_seconds", "REAL DEFAULT 0.0"),
        ("checkpoint_json", "TEXT DEFAULT '{}'"),
        ("retries_count", "INTEGER DEFAULT 0"),
        ("max_retries", "INTEGER DEFAULT 3"),
        ("is_scheduled_recheck", "INTEGER DEFAULT 0"),
        ("recheck_target_type", "TEXT DEFAULT ''"),
        ("recheck_target_id", "INTEGER"),
        ("search_queries_count", "INTEGER DEFAULT 0"),
        ("search_results_count", "INTEGER DEFAULT 0")
    ]
    for col, col_type in rj_cols_to_add:
        if col not in existing_job_cols:
            try:
                cursor.execute(f"ALTER TABLE research_jobs ADD COLUMN {col} {col_type}")
            except Exception as mig_err:
                logger.warning(f"[DB Migration] Could not add column {col} to research_jobs: {mig_err}")

    # Run migrations for profile_version on scholarships, professors, email_drafts
    for table_name in ["scholarships", "professors", "email_drafts"]:
        t_cols = [row["name"] for row in cursor.execute(f"PRAGMA table_info({table_name})").fetchall()]
        if "profile_version" not in t_cols:
            try:
                cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN profile_version INTEGER DEFAULT 1")
            except Exception as e:
                logger.warning(f"[DB Migration] Could not add profile_version to {table_name}: {e}")

    # Run migrations for crawl_pages columns
    existing_cp_cols = [row["name"] for row in cursor.execute("PRAGMA table_info(crawl_pages)").fetchall()]
    cp_cols_to_add = [
        ("normalized_url", "TEXT"),
        ("page_status", "TEXT DEFAULT 'success'"),
        ("status_reason", "TEXT DEFAULT ''"),
        ("selection_reason", "TEXT DEFAULT ''"),
        ("content_hash", "TEXT DEFAULT ''"),
        ("byte_size", "INTEGER DEFAULT 0"),
        ("depth", "INTEGER DEFAULT 0"),
        ("is_external", "INTEGER DEFAULT 0"),
        ("external_domain_type", "TEXT DEFAULT 'official_university'")
    ]
    for col, col_type in cp_cols_to_add:
        if col not in existing_cp_cols:
            try:
                cursor.execute(f"ALTER TABLE crawl_pages ADD COLUMN {col} {col_type}")
            except Exception as mig_err:
                logger.warning(f"[DB Migration] Could not add column {col} to crawl_pages: {mig_err}")

    # Run migrations for scholarships columns
    existing_s_cols = [row["name"] for row in cursor.execute("PRAGMA table_info(scholarships)").fetchall()]
    s_cols_to_add = [
        ("university", "TEXT DEFAULT 'Unknown'"),
        ("country", "TEXT DEFAULT 'Unknown'"),
        ("program", "TEXT DEFAULT 'Unknown'"),
        ("degree_level", "TEXT DEFAULT 'Unknown'"),
        ("funding_category", "TEXT DEFAULT 'Unclear funding'"),
        ("intake_and_year", "TEXT DEFAULT 'Unknown'"),
        ("international_eligibility", "TEXT DEFAULT 'Unknown'"),
        ("nationality_restrictions", "TEXT DEFAULT 'None stated'"),
        ("academic_requirements", "TEXT DEFAULT 'Unknown'"),
        ("tuition_coverage", "TEXT DEFAULT 'Unknown'"),
        ("stipend_amount", "TEXT DEFAULT 'Unknown'"),
        ("stipend_currency", "TEXT DEFAULT 'Unknown'"),
        ("stipend_frequency", "TEXT DEFAULT 'Unknown'"),
        ("funding_duration", "TEXT DEFAULT 'Unknown'"),
        ("insurance_and_travel", "TEXT DEFAULT 'None stated'"),
        ("other_costs", "TEXT DEFAULT 'Unknown'"),
        ("obligations", "TEXT DEFAULT 'Unknown'"),
        ("renewal_conditions", "TEXT DEFAULT 'Unknown'"),
        ("application_fee", "TEXT DEFAULT 'None stated'"),
        ("deadline_date", "TEXT DEFAULT 'Unknown'"),
        ("opportunity_status", "TEXT DEFAULT 'unknown'"),
        ("application_route", "TEXT DEFAULT 'Unknown'"),
        ("official_url", "TEXT DEFAULT ''"),
        ("eligibility_status", "TEXT DEFAULT 'Needs clarification'"),
        ("eligibility_explanation", "TEXT DEFAULT ''"),
        ("claims_evidence", "TEXT DEFAULT '{}'"),
        ("discovered_via_query", "TEXT DEFAULT ''"),
        ("is_shortlisted", "INTEGER DEFAULT 0"),
        ("notes", "TEXT DEFAULT ''"),
        ("last_checked_at", "TIMESTAMP"),
        ("is_stale", "INTEGER DEFAULT 0")
    ]
    for col, col_type in s_cols_to_add:
        if col not in existing_s_cols:
            try:
                cursor.execute(f"ALTER TABLE scholarships ADD COLUMN {col} {col_type}")
                if col == "last_checked_at":
                    cursor.execute("UPDATE scholarships SET last_checked_at = created_at WHERE last_checked_at IS NULL")
            except Exception as mig_err:
                logger.warning(f"[DB Migration] Could not add column {col} to scholarships: {mig_err}")

    # Run migrations for professors columns
    existing_p_cols = [row["name"] for row in cursor.execute("PRAGMA table_info(professors)").fetchall()]
    p_cols_to_add = [
        ("university", "TEXT DEFAULT 'Unknown'"),
        ("official_profile_url", "TEXT DEFAULT ''"),
        ("lab_url", "TEXT DEFAULT ''"),
        ("affiliation_evidence", "TEXT DEFAULT 'None stated in source'"),
        ("publications_projects", "TEXT DEFAULT 'None stated in source'"),
        ("email_source_url", "TEXT DEFAULT ''"),
        ("email_date_observed", "TEXT DEFAULT ''"),
        ("contact_instructions", "TEXT DEFAULT 'Standard academic inquiry'"),
        ("recruitment_status", "TEXT DEFAULT 'Unstated'"),
        ("recruitment_evidence", "TEXT DEFAULT 'None stated in source'"),
        ("position_funding_type", "TEXT DEFAULT 'Unstated'"),
        ("position_funding_evidence", "TEXT DEFAULT 'None stated in source'"),
        ("research_overlap_score", "INTEGER DEFAULT 0"),
        ("experience_fit_score", "INTEGER DEFAULT 0"),
        ("degree_fit_score", "INTEGER DEFAULT 0"),
        ("recruitment_fit_score", "INTEGER DEFAULT 0"),
        ("match_reasons", "TEXT DEFAULT '[]'"),
        ("missing_information", "TEXT DEFAULT '[]'"),
        ("score_breakdown", "TEXT DEFAULT '{}'"),
        ("is_heuristic_score", "INTEGER DEFAULT 1"),
        ("discovered_via_query", "TEXT DEFAULT ''"),
        ("is_shortlisted", "INTEGER DEFAULT 0"),
        ("notes", "TEXT DEFAULT ''"),
        ("last_checked_at", "TIMESTAMP"),
        ("is_stale", "INTEGER DEFAULT 0")
    ]
    for col, col_type in p_cols_to_add:
        if col not in existing_p_cols:
            try:
                cursor.execute(f"ALTER TABLE professors ADD COLUMN {col} {col_type}")
                if col == "last_checked_at":
                    cursor.execute("UPDATE professors SET last_checked_at = created_at WHERE last_checked_at IS NULL")
            except Exception as mig_err:
                logger.warning(f"[DB Migration] Could not add column {col} to professors: {mig_err}")

    # Run migrations for email_drafts columns
    existing_d_cols = [row["name"] for row in cursor.execute("PRAGMA table_info(email_drafts)").fetchall()]
    d_cols_to_add = [
        ("attachments", "TEXT DEFAULT '[\"Academic CV (PDF)\"]'"),
        ("evidence_used", "TEXT DEFAULT '{}'"),
        ("outreach_instructions", "TEXT DEFAULT '{}'"),
        ("contact_instructions_flag", "TEXT DEFAULT 'standard'"),
        ("contact_instructions_notes", "TEXT DEFAULT ''"),
        ("unsupported_claims_flag", "INTEGER DEFAULT 0"),
        ("unsupported_claims_notes", "TEXT DEFAULT ''"),
        ("status", "TEXT DEFAULT 'draft'"),
        ("is_reviewed", "INTEGER DEFAULT 0"),
        ("approval_status", "TEXT DEFAULT 'draft'"),
        ("content_hash", "TEXT DEFAULT ''"),
        ("approved_content_hash", "TEXT DEFAULT ''"),
        ("approved_at", "TIMESTAMP"),
        ("approved_by", "TEXT DEFAULT ''"),
        ("parent_draft_id", "INTEGER"),
        ("follow_up_sequence", "INTEGER DEFAULT 0"),
        ("reply_status", "TEXT DEFAULT 'no_reply'"),
        ("last_reply_at", "TIMESTAMP")
    ]
    for col, col_type in d_cols_to_add:
        if col not in existing_d_cols:
            try:
                cursor.execute(f"ALTER TABLE email_drafts ADD COLUMN {col} {col_type}")
            except Exception as mig_err:
                logger.warning(f"[DB Migration] Could not add column {col} to email_drafts: {mig_err}")

    # Seed default outreach settings if none exists
    cursor.execute("SELECT COUNT(*) as cnt FROM outreach_settings")
    if cursor.fetchone()["cnt"] == 0:
        cursor.execute("""
        INSERT INTO outreach_settings (
            id, purpose, target_degree_intake, tone_and_length, specific_request,
            background_to_emphasize, signature, proposed_attachments, optional_wording_preferences
        ) VALUES (
            1,
            'PhD Advisorship & Research Assistantship Inquiry',
            'Ph.D. in Computer Science (Fall 2026)',
            'Professional, concise, scholarly; under 200 words',
            'Request a brief 15-minute introductory video call to discuss potential research synergy and prospective Ph.D. opportunities.',
            'Strong foundation in AI/ML research, 3.95 GPA, hands-on PyTorch engineering, and published work in NLP.',
            'Sincerely,\n[Candidate Name]\nApplicant, Graduate Research\nEmail: candidate@alumni.univ.edu\nPortfolio: https://github.com/scholarscout-candidate',
            'Academic CV (PDF), Unofficial Transcript, 1-page Research Summary',
            'Focus strictly on specific lab publications and neuro-symbolic research; avoid generic flattery or assumptions about guaranteed funding.'
        )
        """)

    # Seed default Mock Sandbox Account if none exists (Zero-risk testing environment)
    cursor.execute("SELECT COUNT(*) as cnt FROM email_accounts")
    if cursor.fetchone()["cnt"] == 0:
        cursor.execute("""
        INSERT INTO email_accounts (
            id, name, provider_type, email_address, credentials_json,
            is_active, hourly_limit, daily_limit, delay_between_sends_sec, reply_sync_enabled
        ) VALUES (
            1,
            'Mock Sandbox Environment (Safe Offline Testing)',
            'mock_sandbox',
            'sandbox@scholarscout.local',
            '{"simulation_mode": "normal"}',
            1, 50, 200, 5, 1
        )
        """)

    # Seed default global system settings
    cursor.execute("""
    INSERT OR IGNORE INTO system_settings (key, value) VALUES
    ('sending_master_enabled', '0'),
    ('max_hourly_outbound', '20'),
    ('duplicate_window_days', '30'),
    ('default_account_id', '1'),
    ('auto_reconcile_timeouts', '1')
    """)

    # Seed initial sample Do-Not-Contact entry
    cursor.execute("""
    INSERT OR IGNORE INTO do_not_contact (pattern, reason, source) VALUES
    ('optout-sample@university.edu', 'Sample suppression pattern for testing', 'system_seed')
    """)

    # Create indices for query performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_scholarships_job ON scholarships(job_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_scholarships_shortlisted ON scholarships(is_shortlisted)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_professors_job ON professors(job_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_professors_shortlisted ON professors(is_shortlisted)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_drafts_job ON email_drafts(job_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_drafts_status ON email_drafts(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_drafts_approval ON email_drafts(approval_status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON research_jobs(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_profile_versions ON profile_versions(profile_id, version)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_crawl_pages_job ON crawl_pages(job_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_external_leads_job ON external_leads(job_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_search_cache_hash ON search_cache(query_hash)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_univ_bookmarks_shortlisted ON university_bookmarks(is_shortlisted)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_outbound_queue_status ON email_outbound_queue(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_recipient ON email_audit_log(recipient_email)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_evidence_history_entity ON evidence_history(entity_type, entity_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_rechecks_enabled ON scheduled_rechecks(is_enabled, next_run_at)")

    conn.commit()

    # Seed default sample profile if none exists
    cursor.execute("SELECT COUNT(*) as cnt FROM profiles")
    if cursor.fetchone()["cnt"] == 0:
        cursor.execute("""
        INSERT INTO profiles (
            name, nationality, current_residence, current_degree, current_institution,
            current_major, gpa, graduation_date, target_degree, broad_subject,
            target_field, specific_interests, research_interests, preferred_countries,
            excluded_countries, intended_intake, english_tests, projects, publications,
            research_experience, technical_skills, background_summary, funding_needs,
            funding_notes, portfolio_url, github_url, website_url, version, country_of_origin, is_active
        ) VALUES (
            'Alex Rivera',
            'International',
            'Germany',
            'B.S. in Computer Science',
            'Technical University of Munich',
            'Computer Science',
            '3.92 / 4.0',
            'June 2025',
            'Ph.D.',
            'Computer Science',
            'Artificial Intelligence & Systems',
            'Large Language Models, Multi-Agent Systems, Neural Reasoning',
            'Large Language Models, Safe AI Alignment, Multi-Agent Systems, Neural Reasoning',
            '["United States", "United Kingdom", "Canada", "Germany"]',
            '[]',
            'Fall 2025',
            'TOEFL iBT 112 (R:30, L:29, S:26, W:27)',
            'ScholarScout Autonomous Research Agent, LLM Benchmark Suite',
            '1 workshop paper at NeurIPS LLM Agent Evaluation Workshop',
            'Undergraduate Research Assistant in NLP Laboratory (2 years)',
            'Python, PyTorch, C++, CUDA, FastMCP, Transformers',
            'BS in Computer Science. Experience in deep learning architectures, PyTorch, and NLP research.',
            '["full_tuition", "living_stipend", "health_insurance"]',
            'Seeking fully-funded graduate research assistantship (GRA/GTA) or fellowship.',
            'https://alexrivera.dev',
            'https://github.com/alexrivera-research',
            'https://alexrivera.dev',
            1,
            'International',
            1
        )
        """)
        profile_id = cursor.lastrowid
        # Snapshot initial version
        initial_snap = {
            "name": "Alex Rivera", "target_degree": "Ph.D.", "gpa": "3.92 / 4.0",
            "broad_subject": "Computer Science", "research_interests": "LLMs, Multi-Agent Systems"
        }
        cursor.execute("""
        INSERT INTO profile_versions (profile_id, version, snapshot_json)
        VALUES (?, 1, ?)
        """, (profile_id, json.dumps(initial_snap)))
        conn.commit()

    conn.close()
    logger.info("Database initialized successfully.")

# --- Profiles CRUD ---

def get_active_profile() -> Optional[Dict[str, Any]]:
    """Get the active student profile."""
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM profiles WHERE is_active = 1 ORDER BY updated_at DESC LIMIT 1").fetchone()
    conn.close()
    return dict(row) if row else None

def get_all_profiles() -> List[Dict[str, Any]]:
    """Get all saved profiles."""
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM profiles ORDER BY updated_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_profile_by_id(profile_id: int) -> Optional[Dict[str, Any]]:
    """Get profile by ID."""
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def save_profile(data: Dict[str, Any]) -> int:
    """Create or update student profile with automatic version incrementing and snapshotting."""
    conn = get_db_connection()
    cursor = conn.cursor()
    profile_id = data.get("id")

    name = (data.get("full_name") or data.get("name") or "Prospective Student").strip()
    target_degree = data.get("target_degree", "Ph.D.").strip()
    broad_subject = (data.get("broad_subject") or data.get("target_field") or data.get("current_major") or "Computer Science").strip()
    current_major = (data.get("current_major") or broad_subject).strip()
    target_field = (data.get("target_field") or broad_subject).strip()
    research_interests = (data.get("specific_interests") or data.get("research_interests") or "").strip()
    specific_interests = (data.get("specific_interests") or research_interests).strip()
    gpa = (data.get("gpa") or "Unknown").strip()
    nationality = (data.get("nationality") or data.get("country_of_origin") or "Unknown").strip()
    country_of_origin = nationality
    current_residence = (data.get("current_residence") or "Unknown").strip()
    current_degree = (data.get("current_degree") or "Unknown").strip()
    current_institution = (data.get("current_institution") or "Unknown").strip()
    graduation_date = (data.get("graduation_date") or "Unknown").strip()
    intended_intake = (data.get("intended_intake") or "Unknown").strip()
    english_tests = (data.get("english_tests") or "Unknown").strip()
    projects = (data.get("projects") or "").strip()
    publications = (data.get("publications") or "").strip()
    research_experience = (data.get("research_experience") or "").strip()
    technical_skills = (data.get("technical_skills") or "").strip()
    background_summary = (data.get("background_summary") or "").strip()
    funding_notes = (data.get("funding_notes") or "").strip()
    portfolio_url = (data.get("portfolio_url") or "").strip()
    github_url = (data.get("github_url") or "").strip()
    website_url = (data.get("website_url") or "").strip()
    is_active = int(data.get("is_active", 1))

    # Helper for JSON list fields
    def to_json_str(val):
        if isinstance(val, list):
            return json.dumps(val)
        if isinstance(val, str) and (val.startswith("[") and val.endswith("]")):
            return val
        if isinstance(val, str) and val.strip():
            return json.dumps([x.strip() for x in val.split(",") if x.strip()])
        return "[]"

    preferred_countries = to_json_str(data.get("preferred_countries"))
    excluded_countries = to_json_str(data.get("excluded_countries"))
    funding_needs = to_json_str(data.get("funding_needs"))

    if profile_id:
        # Fetch current version to increment
        existing = cursor.execute("SELECT version FROM profiles WHERE id = ?", (profile_id,)).fetchone()
        current_ver = existing["version"] if existing and existing["version"] else 1
        new_version = current_ver + 1

        cursor.execute("""
        UPDATE profiles SET
            name = ?, nationality = ?, current_residence = ?, current_degree = ?,
            current_institution = ?, current_major = ?, gpa = ?, graduation_date = ?,
            target_degree = ?, broad_subject = ?, target_field = ?, research_interests = ?,
            specific_interests = ?, preferred_countries = ?, excluded_countries = ?,
            intended_intake = ?, english_tests = ?, projects = ?, publications = ?,
            research_experience = ?, technical_skills = ?, background_summary = ?,
            funding_needs = ?, funding_notes = ?, portfolio_url = ?, github_url = ?,
            website_url = ?, version = ?, country_of_origin = ?, is_active = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """, (
            name, nationality, current_residence, current_degree,
            current_institution, current_major, gpa, graduation_date,
            target_degree, broad_subject, target_field, research_interests,
            specific_interests, preferred_countries, excluded_countries,
            intended_intake, english_tests, projects, publications,
            research_experience, technical_skills, background_summary,
            funding_needs, funding_notes, portfolio_url, github_url,
            website_url, new_version, country_of_origin, is_active,
            profile_id
        ))
        
        # Save version snapshot
        snapshot = {
            "name": name, "target_degree": target_degree, "gpa": gpa,
            "nationality": nationality, "broad_subject": broad_subject,
            "specific_interests": specific_interests, "current_degree": current_degree,
            "current_institution": current_institution, "funding_needs": funding_needs,
            "version": new_version
        }
        cursor.execute("""
        INSERT INTO profile_versions (profile_id, version, snapshot_json)
        VALUES (?, ?, ?)
        """, (profile_id, new_version, json.dumps(snapshot)))

    else:
        if is_active:
            cursor.execute("UPDATE profiles SET is_active = 0")

        new_version = 1
        cursor.execute("""
        INSERT INTO profiles (
            name, nationality, current_residence, current_degree, current_institution,
            current_major, gpa, graduation_date, target_degree, broad_subject,
            target_field, research_interests, specific_interests, preferred_countries,
            excluded_countries, intended_intake, english_tests, projects, publications,
            research_experience, technical_skills, background_summary, funding_needs,
            funding_notes, portfolio_url, github_url, website_url, version, country_of_origin, is_active
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            name, nationality, current_residence, current_degree, current_institution,
            current_major, gpa, graduation_date, target_degree, broad_subject,
            target_field, research_interests, specific_interests, preferred_countries,
            excluded_countries, intended_intake, english_tests, projects, publications,
            research_experience, technical_skills, background_summary, funding_needs,
            funding_notes, portfolio_url, github_url, website_url, new_version, country_of_origin, is_active
        ))
        profile_id = cursor.lastrowid

        snapshot = {
            "name": name, "target_degree": target_degree, "gpa": gpa,
            "nationality": nationality, "broad_subject": broad_subject,
            "specific_interests": specific_interests, "version": new_version
        }
        cursor.execute("""
        INSERT INTO profile_versions (profile_id, version, snapshot_json)
        VALUES (?, 1, ?)
        """, (profile_id, json.dumps(snapshot)))

    conn.commit()
    conn.close()
    return profile_id

def get_profile_versions(profile_id: int) -> List[Dict[str, Any]]:
    """Retrieves all version snapshots for a given profile."""
    conn = get_db_connection()
    rows = conn.execute("""
    SELECT * FROM profile_versions WHERE profile_id = ? ORDER BY version DESC
    """, (profile_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_profile_version(profile_id: int, version: int) -> Optional[Dict[str, Any]]:
    """Retrieves a specific version snapshot."""
    conn = get_db_connection()
    row = conn.execute("""
    SELECT * FROM profile_versions WHERE profile_id = ? AND version = ?
    """, (profile_id, version)).fetchone()
    conn.close()
    return dict(row) if row else None

# --- Search Cache & Quota Management (Discovery Mode) ---

def get_cached_search(query_hash: str, max_age_days: int = 7) -> Optional[Dict[str, Any]]:
    """Retrieves cached search query results if within TTL."""
    conn = get_db_connection()
    row = conn.execute("""
    SELECT query_hash, query_text, provider, results_json, result_count, created_at
    FROM search_cache
    WHERE query_hash = ? AND datetime(created_at, '+' || ? || ' days') >= datetime('now')
    """, (query_hash, max_age_days)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    try:
        d["results"] = json.loads(d["results_json"] or "[]")
    except Exception:
        d["results"] = []
    return d

def set_cached_search(
    query_hash: str,
    query_text: str,
    provider: str,
    results: List[Dict[str, Any]],
    count: int = 0
):
    """Caches search query results."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO search_cache (query_hash, query_text, provider, results_json, result_count, created_at)
    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(query_hash) DO UPDATE SET
        results_json = excluded.results_json,
        result_count = excluded.result_count,
        created_at = CURRENT_TIMESTAMP
    """, (
        query_hash,
        query_text,
        provider,
        json.dumps(results),
        count or len(results)
    ))
    conn.commit()
    conn.close()

# --- Persistent Research Jobs Queue CRUD ---

def enqueue_research_job(
    university_url: str,
    profile_id: Optional[int] = None,
    university_name: str = "",
    profile_version: int = 1,
    scope: str = "all",
    max_pages: int = 15,
    max_depth: int = 3,
    time_limit_seconds: int = 120,
    job_type: str = "url_research",
    discovery_queries: Optional[List[Dict[str, Any]]] = None
) -> int:
    """Creates a new queued research job in SQLite recording scope, limits, and profile version."""
    conn = get_db_connection()
    cursor = conn.cursor()
    queries_json = json.dumps(discovery_queries or [])
    cursor.execute("""
    INSERT INTO research_jobs (
        profile_id, profile_version, university_url, university_name,
        scope, max_pages, max_depth, time_limit_seconds,
        job_type, discovery_queries, status, current_step, logs
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', 'Queued in background worker', '[]')
    """, (
        profile_id, profile_version, university_url.strip(),
        university_name.strip() or university_url.strip(),
        scope.strip() if scope else "all",
        max_pages, max_depth, time_limit_seconds,
        job_type.strip() if job_type else "url_research",
        queries_json
    ))
    job_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return job_id

def get_next_queued_job() -> Optional[Dict[str, Any]]:
    """Picks the oldest queued job for processing."""
    conn = get_db_connection()
    row = conn.execute("""
    SELECT * FROM research_jobs WHERE status = 'queued' ORDER BY id ASC LIMIT 1
    """).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["logs"] = json.loads(d["logs"] or "[]")
    if d.get("discovery_queries"):
        try:
            d["discovery_queries"] = json.loads(d["discovery_queries"])
        except Exception:
            d["discovery_queries"] = []
    if d.get("discovered_institutions"):
        try:
            d["discovered_institutions"] = json.loads(d["discovered_institutions"])
        except Exception:
            d["discovered_institutions"] = []
    if d.get("coverage_report"):
        try:
            d["coverage_report"] = json.loads(d["coverage_report"])
        except Exception:
            d["coverage_report"] = {}
    return d

def update_job_status(
    job_id: int,
    status: str,
    current_step: Optional[str] = None,
    progress_pct: Optional[int] = None,
    pages_crawled: Optional[int] = None,
    scholarships_count: Optional[int] = None,
    professors_count: Optional[int] = None,
    error_message: Optional[str] = None,
    university_name: Optional[str] = None,
    llm_requests_count: Optional[int] = None,
    llm_prompt_tokens: Optional[int] = None,
    llm_completion_tokens: Optional[int] = None,
    llm_total_tokens: Optional[int] = None,
    is_paused: Optional[int] = None,
    pause_reason: Optional[str] = None,
    stop_reason: Optional[str] = None,
    checkpoint_json: Optional[Union[str, Dict[str, Any]]] = None,
    retries_count: Optional[int] = None,
    elapsed_seconds: Optional[float] = None,
    time_budget_sec: Optional[int] = None,
    page_budget: Optional[int] = None,
    request_budget: Optional[int] = None,
    token_budget: Optional[int] = None,
    coverage_report: Optional[Dict[str, Any]] = None,
    search_queries_count: Optional[int] = None,
    search_results_count: Optional[int] = None,
    discovered_institutions: Optional[List[Dict[str, Any]]] = None
):
    """Updates research job progress, metrics, pause states, budgets, checkpoints, and discovery coverage."""
    conn = get_db_connection()
    cursor = conn.cursor()

    fields = ["status = ?"]
    values: List[Any] = [status]

    if current_step is not None:
        fields.append("current_step = ?")
        values.append(current_step)
    if progress_pct is not None:
        fields.append("progress_pct = ?")
        values.append(progress_pct)
    if pages_crawled is not None:
        fields.append("pages_crawled = ?")
        values.append(pages_crawled)
    if scholarships_count is not None:
        fields.append("scholarships_count = ?")
        values.append(scholarships_count)
    if professors_count is not None:
        fields.append("professors_count = ?")
        values.append(professors_count)
    if error_message is not None:
        fields.append("error_message = ?")
        values.append(error_message)
    if university_name is not None:
        fields.append("university_name = ?")
        values.append(university_name)
    if llm_requests_count is not None:
        fields.append("llm_requests_count = ?")
        values.append(llm_requests_count)
    if llm_prompt_tokens is not None:
        fields.append("llm_prompt_tokens = ?")
        values.append(llm_prompt_tokens)
    if llm_completion_tokens is not None:
        fields.append("llm_completion_tokens = ?")
        values.append(llm_completion_tokens)
    if llm_total_tokens is not None:
        fields.append("llm_total_tokens = ?")
        values.append(llm_total_tokens)
    if is_paused is not None:
        fields.append("is_paused = ?")
        values.append(is_paused)
    if pause_reason is not None:
        fields.append("pause_reason = ?")
        values.append(pause_reason)
    if stop_reason is not None:
        fields.append("stop_reason = ?")
        values.append(stop_reason)
    if checkpoint_json is not None:
        fields.append("checkpoint_json = ?")
        values.append(json.dumps(checkpoint_json) if isinstance(checkpoint_json, dict) else str(checkpoint_json))
    if retries_count is not None:
        fields.append("retries_count = ?")
        values.append(retries_count)
    if elapsed_seconds is not None:
        fields.append("elapsed_seconds = ?")
        values.append(elapsed_seconds)
    if time_budget_sec is not None:
        fields.append("time_budget_sec = ?")
        values.append(time_budget_sec)
    if page_budget is not None:
        fields.append("page_budget = ?")
        values.append(page_budget)
    if request_budget is not None:
        fields.append("request_budget = ?")
        values.append(request_budget)
    if token_budget is not None:
        fields.append("token_budget = ?")
        values.append(token_budget)
    if coverage_report is not None:
        fields.append("coverage_report = ?")
        values.append(json.dumps(coverage_report))
    if search_queries_count is not None:
        fields.append("search_queries_count = ?")
        values.append(search_queries_count)
    if search_results_count is not None:
        fields.append("search_results_count = ?")
        values.append(search_results_count)
    if discovered_institutions is not None:
        fields.append("discovered_institutions = ?")
        values.append(json.dumps(discovered_institutions))

    if status == 'running':
        fields.append("started_at = COALESCE(started_at, CURRENT_TIMESTAMP)")
    elif status in ('completed', 'partially_completed', 'failed', 'cancelled'):
        fields.append("completed_at = CURRENT_TIMESTAMP")

    values.append(job_id)
    sql = f"UPDATE research_jobs SET {', '.join(fields)} WHERE id = ?"
    cursor.execute(sql, tuple(values))
    conn.commit()
    conn.close()

def save_job_checkpoint(job_id: int, checkpoint: Dict[str, Any], elapsed_seconds: float = 0.0):
    """Saves checkpoint data for resumable research jobs."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE research_jobs
    SET checkpoint_json = ?, elapsed_seconds = ?
    WHERE id = ?
    """, (json.dumps(checkpoint), elapsed_seconds, job_id))
    conn.commit()
    conn.close()

def get_job_checkpoint(job_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves saved checkpoint state for resuming a research job."""
    conn = get_db_connection()
    row = conn.execute("SELECT checkpoint_json FROM research_jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()
    if not row or not row["checkpoint_json"]:
        return None
    try:
        return json.loads(row["checkpoint_json"])
    except Exception:
        return None

def record_evidence_change(
    cursor: sqlite3.Cursor,
    entity_type: str, # 'scholarship', 'professor'
    entity_id: int,
    field_name: str,
    old_value: Any,
    new_value: Any,
    old_evidence: str = "",
    new_evidence: str = "",
    source_url: str = "",
    job_id: Optional[int] = None
):
    """Records an atomic historical change to tracked opportunity fields or faculty contact info."""
    cursor.execute("""
    INSERT INTO evidence_history (
        entity_type, entity_id, field_name, old_value, new_value,
        old_evidence, new_evidence, source_url, job_id, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (
        entity_type,
        entity_id,
        field_name,
        str(old_value) if old_value is not None else "",
        str(new_value) if new_value is not None else "",
        str(old_evidence or ""),
        str(new_evidence or ""),
        str(source_url or ""),
        job_id
    ))

def get_evidence_history(entity_type: str, entity_id: int) -> List[Dict[str, Any]]:
    """Retrieves chronological audit trail of changes for a specific scholarship or professor."""
    conn = get_db_connection()
    rows = conn.execute("""
    SELECT eh.*, rj.university_name as job_university_name
    FROM evidence_history eh
    LEFT JOIN research_jobs rj ON eh.job_id = rj.id
    WHERE eh.entity_type = ? AND eh.entity_id = ?
    ORDER BY eh.created_at DESC, eh.id DESC
    """, (entity_type, entity_id)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_recent_evidence_changes(limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieves recent changes across all scholarships and faculty leads."""
    conn = get_db_connection()
    rows = conn.execute("""
    SELECT eh.*, rj.university_name as job_university_name
    FROM evidence_history eh
    LEFT JOIN research_jobs rj ON eh.job_id = rj.id
    ORDER BY eh.created_at DESC, eh.id DESC
    LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def mark_stale_records(stale_days: int = 30) -> Dict[str, int]:
    """Marks scholarships and professors as stale if not checked within stale_days."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE scholarships
    SET is_stale = 1
    WHERE datetime(last_checked_at) < datetime('now', '-' || ? || ' days')
    """, (stale_days,))
    s_cnt = cursor.rowcount

    cursor.execute("""
    UPDATE professors
    SET is_stale = 1
    WHERE datetime(last_checked_at) < datetime('now', '-' || ? || ' days')
    """, (stale_days,))
    p_cnt = cursor.rowcount

    conn.commit()
    conn.close()
    return {"stale_scholarships": s_cnt, "stale_professors": p_cnt}

def pause_job(job_id: int, reason: str = "Quota limit reached") -> bool:
    """Pauses an active research/discovery job."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE research_jobs
    SET status = 'paused', is_paused = 1, pause_reason = ?, stop_reason = ?, current_step = ?
    WHERE id = ? AND status IN ('running', 'queued')
    """, (reason, reason, f"Paused: {reason}", job_id))
    success = cursor.rowcount > 0
    conn.commit()
    conn.close()
    if success:
        append_job_log(job_id, f"Job paused: {reason}", "warning")
    return success

def resume_job(job_id: int) -> bool:
    """Resumes a paused research/discovery job."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE research_jobs
    SET status = 'queued', is_paused = 0, pause_reason = '', current_step = 'Resumed by user'
    WHERE id = ? AND status = 'paused'
    """, (job_id,))
    success = cursor.rowcount > 0
    conn.commit()
    conn.close()
    if success:
        append_job_log(job_id, "Job resumed by user.", "info")
    return success

def update_job_coverage(job_id: int, coverage: Dict[str, Any]):
    """Stores coverage report on a research job."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE research_jobs SET coverage_report = ? WHERE id = ?
    """, (json.dumps(coverage), job_id))
    conn.commit()
    conn.close()

def get_job_coverage(job_id: int) -> Dict[str, Any]:
    """Retrieves coverage report for a job."""
    conn = get_db_connection()
    row = conn.execute("SELECT coverage_report FROM research_jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()
    default_report = {
        "disclaimer": "ScholarScout performs targeted discovery across configured search providers and official academic portals. It does not claim exhaustive indexing of every university worldwide.",
        "summary": {
            "queries_planned": 0,
            "queries_executed": 0,
            "total_results_found": 0,
            "discovered_institutions_count": 0,
            "skipped_count": 0,
            "status": "Coverage report compiling or pending job execution."
        },
        "queries": [],
        "discovered_institutions": [],
        "skipped_institutions": [],
        "external_leads": []
    }
    if not row or not row["coverage_report"]:
        return default_report
    try:
        data = json.loads(row["coverage_report"])
        if isinstance(data, dict) and data:
            if "disclaimer" not in data:
                data["disclaimer"] = default_report["disclaimer"]
            return data
        return default_report
    except Exception:
        return default_report

def append_job_log(job_id: int, message: str, level: str = "info"):
    """Appends a log message to the persistent job log."""
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT logs FROM research_jobs WHERE id = ?", (job_id,)).fetchone()
    if row:
        logs = json.loads(row["logs"] or "[]")
        logs.append({
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "level": level,
            "message": message
        })
        # Keep last 200 logs
        logs = logs[-200:]
        cursor.execute("UPDATE research_jobs SET logs = ? WHERE id = ?", (json.dumps(logs), job_id))
        conn.commit()
    conn.close()

def get_job(job_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve full job details."""
    conn = get_db_connection()
    row = conn.execute("""
    SELECT rj.*, p.name as profile_name
    FROM research_jobs rj
    LEFT JOIN profiles p ON rj.profile_id = p.id
    WHERE rj.id = ?
    """, (job_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["logs"] = json.loads(d["logs"] or "[]")
    if d.get("discovery_queries"):
        try:
            d["discovery_queries"] = json.loads(d["discovery_queries"])
        except Exception:
            d["discovery_queries"] = []
    if d.get("discovered_institutions"):
        try:
            d["discovered_institutions"] = json.loads(d["discovered_institutions"])
        except Exception:
            d["discovered_institutions"] = []
    if d.get("coverage_report"):
        try:
            d["coverage_report"] = json.loads(d["coverage_report"])
        except Exception:
            d["coverage_report"] = {}
    if d.get("checkpoint_json"):
        try:
            d["checkpoint"] = json.loads(d["checkpoint_json"])
        except Exception:
            d["checkpoint"] = {}
    return d

def get_all_jobs() -> List[Dict[str, Any]]:
    """Retrieve all jobs ordered by newest first."""
    conn = get_db_connection()
    rows = conn.execute("""
    SELECT rj.*, p.name as profile_name
    FROM research_jobs rj
    LEFT JOIN profiles p ON rj.profile_id = p.id
    ORDER BY rj.id DESC
    """).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["logs"] = json.loads(d["logs"] or "[]")
        if d.get("discovery_queries"):
            try:
                d["discovery_queries"] = json.loads(d["discovery_queries"])
            except Exception:
                d["discovery_queries"] = []
        if d.get("discovered_institutions"):
            try:
                d["discovered_institutions"] = json.loads(d["discovered_institutions"])
            except Exception:
                d["discovered_institutions"] = []
        if d.get("coverage_report"):
            try:
                d["coverage_report"] = json.loads(d["coverage_report"])
            except Exception:
                d["coverage_report"] = {}
        if d.get("checkpoint_json"):
            try:
                d["checkpoint"] = json.loads(d["checkpoint_json"])
            except Exception:
                d["checkpoint"] = {}
        result.append(d)
    return result

def cancel_job(job_id: int) -> bool:
    """Marks a job as cancelled with stop reason."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE research_jobs
    SET status = 'cancelled', current_step = 'Cancelled by user', stop_reason = 'Cancelled by user', completed_at = CURRENT_TIMESTAMP
    WHERE id = ? AND status IN ('queued', 'running', 'paused')
    """, (job_id,))
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated

# --- Scholarships & Professors CRUD ---

def insert_scholarships(job_id: int, scholarships_data: List[Dict[str, Any]], profile_version: int = 1) -> int:
    """
    Inserts or idempotently updates structured scholarship findings.
    Preserves confirmed user edits, shortlisted state, and notes.
    Tracks changes in deadlines, funding terms, eligibility, and opportunity status in evidence_history.
    """
    if not scholarships_data:
        return 0
    conn = get_db_connection()
    cursor = conn.cursor()
    count = 0

    for s in scholarships_data:
        title = (s.get("title") or "").strip()
        if not title or title.lower() in ("unknown", "n/a", "none"):
            continue

        university = (s.get("university") or "Unknown").strip()
        official_url = (s.get("official_url") or "").strip()
        source_url = (s.get("source_url") or "").strip()
        claims_ev = s.get("claims_evidence", {})
        claims_json = json.dumps(claims_ev) if isinstance(claims_ev, dict) else str(claims_ev or "{}")

        # Idempotent match: check if existing record exists by (title + university) OR official_url OR (source_url + title)
        existing = None
        if official_url:
            existing = cursor.execute(
                "SELECT * FROM scholarships WHERE official_url = ?", (official_url,)
            ).fetchone()
        if not existing and title and university != "Unknown":
            existing = cursor.execute(
                "SELECT * FROM scholarships WHERE LOWER(title) = ? AND LOWER(university) = ?",
                (title.lower(), university.lower())
            ).fetchone()
        if not existing and source_url:
            existing = cursor.execute(
                "SELECT * FROM scholarships WHERE source_url = ? AND LOWER(title) = ?",
                (source_url, title.lower())
            ).fetchone()

        if existing:
            ex_dict = dict(existing)
            s_id = ex_dict["id"]

            # Diff tracked fields & record to evidence history
            tracked_fields = [
                ("deadline", ex_dict.get("deadline"), s.get("deadline")),
                ("deadline_date", ex_dict.get("deadline_date"), s.get("deadline_date")),
                ("funding_category", ex_dict.get("funding_category"), s.get("funding_category")),
                ("tuition_coverage", ex_dict.get("tuition_coverage"), s.get("tuition_coverage")),
                ("stipend_amount", ex_dict.get("stipend_amount"), s.get("stipend_amount")),
                ("opportunity_status", ex_dict.get("opportunity_status"), s.get("opportunity_status")),
                ("eligibility_status", ex_dict.get("eligibility_status"), s.get("eligibility_status")),
                ("official_url", ex_dict.get("official_url"), official_url),
            ]

            for fname, old_v, new_v in tracked_fields:
                if new_v and new_v not in ("Unknown", "None stated", "") and old_v != new_v:
                    record_evidence_change(
                        cursor=cursor,
                        entity_type="scholarship",
                        entity_id=s_id,
                        field_name=fname,
                        old_value=old_v,
                        new_value=new_v,
                        old_evidence=ex_dict.get("evidence_snippet", ""),
                        new_evidence=s.get("evidence_snippet", ""),
                        source_url=source_url or official_url,
                        job_id=job_id
                    )

            # Update fields while strictly preserving user notes, is_shortlisted, and keeping higher fit_score
            fit_score = max(int(ex_dict.get("fit_score", 0)), int(s.get("fit_score", 50)))
            discovered_q = ex_dict.get("discovered_via_query") or s.get("discovered_via_query", "")

            cursor.execute("""
            UPDATE scholarships SET
                job_id = COALESCE(?, job_id),
                funding_category = COALESCE(NULLIF(?, 'Unclear funding'), funding_category),
                funding_type = COALESCE(NULLIF(?, 'Unknown'), funding_type),
                tuition_coverage = COALESCE(NULLIF(?, 'Unknown'), tuition_coverage),
                stipend_amount = COALESCE(NULLIF(?, 'Unknown'), stipend_amount),
                stipend_currency = COALESCE(NULLIF(?, 'Unknown'), stipend_currency),
                stipend_frequency = COALESCE(NULLIF(?, 'Unknown'), stipend_frequency),
                deadline = COALESCE(NULLIF(?, 'Unknown'), deadline),
                deadline_date = COALESCE(NULLIF(?, 'Unknown'), deadline_date),
                opportunity_status = COALESCE(NULLIF(?, 'unknown'), opportunity_status),
                eligibility_status = COALESCE(NULLIF(?, 'Needs clarification'), eligibility_status),
                eligibility_explanation = COALESCE(NULLIF(?, ''), eligibility_explanation),
                official_url = COALESCE(NULLIF(?, ''), official_url),
                evidence_snippet = COALESCE(NULLIF(?, 'Unknown'), evidence_snippet),
                claims_evidence = ?,
                fit_score = ?,
                discovered_via_query = ?,
                last_checked_at = CURRENT_TIMESTAMP,
                is_stale = 0
            WHERE id = ?
            """, (
                job_id,
                s.get("funding_category", "Unclear funding"),
                s.get("funding_type", "Unknown"),
                s.get("tuition_coverage", "Unknown"),
                s.get("stipend_amount", "Unknown"),
                s.get("stipend_currency", "Unknown"),
                s.get("stipend_frequency", "Unknown"),
                s.get("deadline", "Unknown"),
                s.get("deadline_date", "Unknown"),
                s.get("opportunity_status", "unknown"),
                s.get("eligibility_status", "Needs clarification"),
                s.get("eligibility_explanation", ""),
                official_url,
                s.get("evidence_snippet", "Unknown"),
                claims_json,
                fit_score,
                discovered_q,
                s_id
            ))
            count += 1
        else:
            cursor.execute("""
            INSERT INTO scholarships (
                job_id, profile_version, title, university, country, program, degree_level,
                funding_category, funding_type, intake_and_year, international_eligibility, nationality_restrictions,
                academic_requirements, tuition_coverage, stipend_amount, stipend_currency, stipend_frequency,
                amount, currency, funding_duration, insurance_and_travel, other_costs, obligations, renewal_conditions,
                application_fee, deadline, deadline_date, opportunity_status, application_route, official_url,
                eligibility, eligibility_status, eligibility_explanation, department, evidence_snippet,
                claims_evidence, source_url, fit_score, fit_reason, is_demo, notes, discovered_via_query,
                last_checked_at, is_stale
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?,
                CURRENT_TIMESTAMP, 0
            )
            """, (
                job_id,
                profile_version,
                title,
                university,
                s.get("country", "Unknown"),
                s.get("program", "Unknown"),
                s.get("degree_level", "Unknown"),
                s.get("funding_category", "Unclear funding"),
                s.get("funding_type", "Unknown"),
                s.get("intake_and_year", "Unknown"),
                s.get("international_eligibility", "Unknown"),
                s.get("nationality_restrictions", "None stated"),
                s.get("academic_requirements", "Unknown"),
                s.get("tuition_coverage", "Unknown"),
                s.get("stipend_amount", "Unknown"),
                s.get("stipend_currency", "Unknown"),
                s.get("stipend_frequency", "Unknown"),
                s.get("amount", "Unknown"),
                s.get("currency", "Unknown"),
                s.get("funding_duration", "Unknown"),
                s.get("insurance_and_travel", "None stated"),
                s.get("other_costs", "Unknown"),
                s.get("obligations", "Unknown"),
                s.get("renewal_conditions", "Unknown"),
                s.get("application_fee", "None stated"),
                s.get("deadline", "Unknown"),
                s.get("deadline_date", "Unknown"),
                s.get("opportunity_status", "unknown"),
                s.get("application_route", "Unknown"),
                official_url,
                s.get("eligibility", "Unknown"),
                s.get("eligibility_status", "Needs clarification"),
                s.get("eligibility_explanation", ""),
                s.get("department", "Unknown"),
                s.get("evidence_snippet", "Unknown"),
                claims_json,
                source_url,
                int(s.get("fit_score", 50)),
                s.get("fit_reason", ""),
                int(s.get("is_demo", 0)),
                s.get("notes", ""),
                s.get("discovered_via_query", "")
            ))
            count += 1

    conn.commit()
    conn.close()
    return count

def insert_professors(job_id: int, professors_data: List[Dict[str, Any]], profile_version: int = 1) -> int:
    """
    Inserts or merges matching faculty members into SQLite with intelligent deduplication,
    affiliation preservation, verified email tracking, query provenance, and evidence history tracking.
    Preserves confirmed user notes and shortlist status.
    """
    if not professors_data:
        return 0
    conn = get_db_connection()
    cursor = conn.cursor()
    count = 0

    for p in professors_data:
        name = (p.get("name") or "").strip()
        if not name or name.lower() in ("unknown", "n/a", "none"):
            continue

        university = (p.get("university") or "Unknown").strip()
        email = (p.get("email") or "Not found").strip()
        official_profile_url = (p.get("official_profile_url") or "").strip()
        source_url = (p.get("source_url") or "").strip()

        score_breakdown_json = json.dumps(p.get("score_breakdown", {})) if isinstance(p.get("score_breakdown"), dict) else str(p.get("score_breakdown") or "{}")
        match_reasons_json = json.dumps(p.get("match_reasons", [])) if isinstance(p.get("match_reasons"), list) else str(p.get("match_reasons") or "[]")
        missing_info_json = json.dumps(p.get("missing_information", [])) if isinstance(p.get("missing_information"), list) else str(p.get("missing_information") or "[]")

        # Idempotent match: name + university OR verified email OR official profile url
        existing = None
        if email and email not in ("Not found", "Unknown", ""):
            existing = cursor.execute(
                "SELECT * FROM professors WHERE LOWER(email) = ?", (email.lower(),)
            ).fetchone()
        if not existing and official_profile_url:
            existing = cursor.execute(
                "SELECT * FROM professors WHERE official_profile_url = ?", (official_profile_url,)
            ).fetchone()
        if not existing and name and university != "Unknown":
            existing = cursor.execute(
                "SELECT * FROM professors WHERE LOWER(name) = ? AND LOWER(university) = ?",
                (name.lower(), university.lower())
            ).fetchone()
        if not existing:
            existing = cursor.execute(
                "SELECT * FROM professors WHERE job_id = ? AND LOWER(name) = ?",
                (job_id, name.lower())
            ).fetchone()

        if existing:
            ex_dict = dict(existing)
            p_id = ex_dict["id"]

            # Diff tracked fields (recruitment status, recruitment evidence, email, funding type, contact instructions)
            tracked_fields = [
                ("email", ex_dict.get("email"), email),
                ("recruitment_status", ex_dict.get("recruitment_status"), p.get("recruitment_status")),
                ("position_funding_type", ex_dict.get("position_funding_type"), p.get("position_funding_type")),
                ("contact_instructions", ex_dict.get("contact_instructions"), p.get("contact_instructions")),
                ("research_interests", ex_dict.get("research_interests"), p.get("research_interests")),
            ]

            for fname, old_v, new_v in tracked_fields:
                if new_v and new_v not in ("Unstated", "Unknown", "Not found", "") and old_v != new_v:
                    record_evidence_change(
                        cursor=cursor,
                        entity_type="professor",
                        entity_id=p_id,
                        field_name=fname,
                        old_value=old_v,
                        new_value=new_v,
                        old_evidence=ex_dict.get("recruitment_evidence", ""),
                        new_evidence=p.get("recruitment_evidence", "") or p.get("evidence_snippet", ""),
                        source_url=source_url or official_profile_url,
                        job_id=job_id
                    )

            # Merge affiliations
            merged_dept = ex_dict.get("department", "Unknown")
            new_dept = p.get("department", "Unknown")
            if new_dept != "Unknown" and new_dept not in merged_dept:
                merged_dept = f"{merged_dept}; {new_dept}" if merged_dept != "Unknown" else new_dept

            merged_lab = ex_dict.get("lab_group", "Unknown")
            new_lab = p.get("lab_group", "Unknown")
            if new_lab != "Unknown" and new_lab not in merged_lab:
                merged_lab = f"{merged_lab}; {new_lab}" if merged_lab != "Unknown" else new_lab

            # Email update if previously missing
            curr_email = ex_dict.get("email", "Not found")
            email_to_use = curr_email
            email_src_to_use = ex_dict.get("email_source_url", "")
            email_date_to_use = ex_dict.get("email_date_observed", "")
            if curr_email in ("Not found", "Unknown", None, "") and email not in ("Not found", "Unknown", None, ""):
                email_to_use = email
                email_src_to_use = p.get("email_source_url", source_url)
                email_date_to_use = p.get("email_date_observed", datetime.now(timezone.utc).strftime("%Y-%m-%d"))

            # Recruitment status update
            rec_status = ex_dict.get("recruitment_status", "Unstated")
            rec_ev = ex_dict.get("recruitment_evidence", "None stated in source")
            contact_inst = ex_dict.get("contact_instructions", "Standard academic inquiry")
            if p.get("recruitment_status") not in ("Unstated", "Unknown", None) and rec_status == "Unstated":
                rec_status = p.get("recruitment_status")
                rec_ev = p.get("recruitment_evidence", rec_ev)
                contact_inst = p.get("contact_instructions", contact_inst)

            pos_funding = ex_dict.get("position_funding_type", "Unstated")
            pos_ev = ex_dict.get("position_funding_evidence", "None stated in source")
            if p.get("position_funding_type") not in ("Unstated", "Unknown", None) and pos_funding == "Unstated":
                pos_funding = p.get("position_funding_type")
                pos_ev = p.get("position_funding_evidence", pos_ev)

            curr_pub = ex_dict.get("publications_projects", "None stated in source")
            new_pub = p.get("publications_projects", "None stated in source")
            merged_pub = curr_pub
            if new_pub not in ("None stated in source", "Unknown", "") and new_pub not in curr_pub:
                merged_pub = f"{curr_pub} | {new_pub}" if curr_pub != "None stated in source" else new_pub

            match_score = max(int(ex_dict.get("match_score", 0)), int(p.get("match_score", 0)))
            r_overlap = max(int(ex_dict.get("research_overlap_score", 0)), int(p.get("research_overlap_score", 0)))
            exp_fit = max(int(ex_dict.get("experience_fit_score", 0)), int(p.get("experience_fit_score", 0)))
            deg_fit = max(int(ex_dict.get("degree_fit_score", 0)), int(p.get("degree_fit_score", 0)))
            rec_fit = max(int(ex_dict.get("recruitment_fit_score", 0)), int(p.get("recruitment_fit_score", 0)))

            discovered_q = ex_dict.get("discovered_via_query") or p.get("discovered_via_query", "")

            cursor.execute("""
            UPDATE professors SET
                job_id = COALESCE(?, job_id),
                department = ?,
                lab_group = ?,
                lab_url = COALESCE(NULLIF(lab_url, ''), ?),
                official_profile_url = COALESCE(NULLIF(official_profile_url, ''), ?),
                email = ?,
                email_source_url = ?,
                email_date_observed = ?,
                recruitment_status = ?,
                recruitment_evidence = ?,
                position_funding_type = ?,
                position_funding_evidence = ?,
                contact_instructions = ?,
                publications_projects = ?,
                match_score = ?,
                research_overlap_score = ?,
                experience_fit_score = ?,
                degree_fit_score = ?,
                recruitment_fit_score = ?,
                match_reason = ?,
                match_reasons = ?,
                missing_information = ?,
                score_breakdown = ?,
                discovered_via_query = ?,
                last_checked_at = CURRENT_TIMESTAMP,
                is_stale = 0
            WHERE id = ?
            """, (
                job_id,
                merged_dept,
                merged_lab,
                p.get("lab_url", ""),
                official_profile_url or ex_dict.get("official_profile_url", ""),
                email_to_use,
                email_src_to_use,
                email_date_to_use,
                rec_status,
                rec_ev,
                pos_funding,
                pos_ev,
                contact_inst,
                merged_pub,
                match_score,
                r_overlap,
                exp_fit,
                deg_fit,
                rec_fit,
                p.get("match_reason") or ex_dict.get("match_reason", ""),
                match_reasons_json,
                missing_info_json,
                score_breakdown_json,
                discovered_q,
                p_id
            ))
            count += 1
        else:
            cursor.execute("""
            INSERT INTO professors (
                job_id, profile_version, name, title, department, university,
                lab_group, lab_url, affiliation_evidence, official_profile_url,
                email, email_source_url, email_date_observed, research_interests,
                publications_projects, recruitment_status, recruitment_evidence,
                position_funding_type, position_funding_evidence, contact_instructions,
                match_score, research_overlap_score, experience_fit_score, degree_fit_score,
                recruitment_fit_score, match_reason, match_reasons, missing_information,
                score_breakdown, evidence_snippet, source_url, is_heuristic_score, is_demo,
                discovered_via_query, last_checked_at, is_stale
            ) VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, CURRENT_TIMESTAMP, 0
            )
            """, (
                job_id,
                profile_version,
                name,
                p.get("title", "Unknown"),
                p.get("department", "Unknown"),
                university,
                p.get("lab_group", "Unknown"),
                p.get("lab_url", ""),
                p.get("affiliation_evidence", "None stated in source"),
                official_profile_url or source_url,
                email,
                p.get("email_source_url", ""),
                p.get("email_date_observed", ""),
                p.get("research_interests", "Unknown"),
                p.get("publications_projects", "None stated in source"),
                p.get("recruitment_status", "Unstated"),
                p.get("recruitment_evidence", "None stated in source"),
                p.get("position_funding_type", "Unstated"),
                p.get("position_funding_evidence", "None stated in source"),
                p.get("contact_instructions", "Standard academic inquiry"),
                int(p.get("match_score", 50)),
                int(p.get("research_overlap_score", 0)),
                int(p.get("experience_fit_score", 0)),
                int(p.get("degree_fit_score", 0)),
                int(p.get("recruitment_fit_score", 0)),
                p.get("match_reason", ""),
                match_reasons_json,
                missing_info_json,
                score_breakdown_json,
                p.get("evidence_snippet", "Unknown"),
                source_url,
                1,
                int(p.get("is_demo", 0)),
                p.get("discovered_via_query", "")
            ))
            count += 1

    conn.commit()
    conn.close()
    return count

def get_scholarships(
    job_id: Optional[int] = None,
    min_fit_score: int = 0,
    funding_category: Optional[str] = None,
    eligibility_status: Optional[str] = None,
    opportunity_status: Optional[str] = None,
    is_shortlisted: Optional[bool] = None,
    search: Optional[str] = None,
    country: Optional[str] = None,
    degree_level: Optional[str] = None,
    sort_by: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Queries scholarships with optional job_id and rich filtering and sorting."""
    conn = get_db_connection()
    conditions = ["s.fit_score >= ?"]
    params: List[Any] = [min_fit_score]

    if job_id:
        conditions.append("s.job_id = ?")
        params.append(job_id)
    if funding_category and funding_category != "all":
        conditions.append("s.funding_category = ?")
        params.append(funding_category)
    if eligibility_status and eligibility_status != "all":
        conditions.append("s.eligibility_status = ?")
        params.append(eligibility_status)
    if opportunity_status and opportunity_status != "all":
        conditions.append("s.opportunity_status = ?")
        params.append(opportunity_status)
    if is_shortlisted is not None:
        conditions.append("s.is_shortlisted = ?")
        params.append(1 if is_shortlisted else 0)
    if country and country != "all" and country.strip():
        conditions.append("LOWER(s.country) LIKE ?")
        params.append(f"%{country.strip().lower()}%")
    if degree_level and degree_level != "all" and degree_level.strip():
        conditions.append("LOWER(s.degree_level) LIKE ?")
        params.append(f"%{degree_level.strip().lower()}%")
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        conditions.append("(LOWER(s.title) LIKE ? OR LOWER(s.university) LIKE ? OR LOWER(s.department) LIKE ? OR LOWER(s.program) LIKE ? OR LOWER(s.notes) LIKE ?)")
        params.extend([term, term, term, term, term])

    # Sorting
    if sort_by == "deadline":
        order_clause = "CASE WHEN s.deadline_date IN ('Unknown', 'None stated', '') THEN 1 ELSE 0 END, s.deadline_date ASC, s.fit_score DESC"
    elif sort_by == "university":
        order_clause = "s.university ASC, s.fit_score DESC"
    elif sort_by == "title":
        order_clause = "s.title ASC, s.fit_score DESC"
    elif sort_by == "recent":
        order_clause = "s.created_at DESC, s.id DESC"
    else: # default fit_score
        order_clause = "s.fit_score DESC, s.id DESC"

    where_clause = " WHERE " + " AND ".join(conditions)
    sql = f"""
    SELECT s.*, rj.university_name, rj.university_url
    FROM scholarships s
    JOIN research_jobs rj ON s.job_id = rj.id
    {where_clause}
    ORDER BY {order_clause}
    """
    rows = conn.execute(sql, tuple(params)).fetchall()
    conn.close()

    result = []
    for r in rows:
        d = dict(r)
        if d.get("claims_evidence"):
            try:
                d["claims_evidence"] = json.loads(d["claims_evidence"])
            except Exception:
                d["claims_evidence"] = {}
        else:
            d["claims_evidence"] = {}
        result.append(d)
    return result


def get_professors(
    job_id: Optional[int] = None,
    min_match_score: int = 0,
    recruitment_status: Optional[str] = None,
    has_email: Optional[bool] = None,
    search: Optional[str] = None,
    department: Optional[str] = None,
    is_shortlisted: Optional[bool] = None,
    university: Optional[str] = None,
    sort_by: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Queries faculty with optional job_id and rich filtering and sorting with JSON parsing."""
    conn = get_db_connection()
    conditions = ["p.match_score >= ?"]
    params: List[Any] = [min_match_score]

    if job_id:
        conditions.append("p.job_id = ?")
        params.append(job_id)
    if recruitment_status and recruitment_status != "all":
        conditions.append("LOWER(p.recruitment_status) = ?")
        params.append(recruitment_status.lower())
    if has_email is True:
        conditions.append("p.email NOT IN ('Not found', 'Unknown', 'None', '') AND p.email LIKE '%@%'")
    elif has_email is False:
        conditions.append("(p.email IN ('Not found', 'Unknown', 'None', '') OR p.email NOT LIKE '%@%')")
    if department and department != "all":
        conditions.append("LOWER(p.department) LIKE ?")
        params.append(f"%{department.lower()}%")
    if university and university != "all" and university.strip():
        conditions.append("LOWER(p.university) LIKE ?")
        params.append(f"%{university.strip().lower()}%")
    if is_shortlisted is not None:
        conditions.append("p.is_shortlisted = ?")
        params.append(1 if is_shortlisted else 0)
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        conditions.append("(LOWER(p.name) LIKE ? OR LOWER(p.department) LIKE ? OR LOWER(p.research_interests) LIKE ? OR LOWER(p.lab_group) LIKE ? OR LOWER(p.university) LIKE ? OR LOWER(p.notes) LIKE ?)")
        params.extend([term, term, term, term, term, term])

    # Sorting
    if sort_by == "name":
        order_clause = "p.name ASC"
    elif sort_by == "department":
        order_clause = "p.department ASC, p.match_score DESC"
    elif sort_by == "university":
        order_clause = "p.university ASC, p.match_score DESC"
    elif sort_by == "recent":
        order_clause = "p.created_at DESC, p.id DESC"
    else: # default match_score
        order_clause = "p.match_score DESC, p.id DESC"

    where_clause = " WHERE " + " AND ".join(conditions)
    sql = f"""
    SELECT p.*, rj.university_name, rj.university_url
    FROM professors p
    JOIN research_jobs rj ON p.job_id = rj.id
    {where_clause}
    ORDER BY {order_clause}
    """
    rows = conn.execute(sql, tuple(params)).fetchall()
    conn.close()

    result = []
    for r in rows:
        d = dict(r)
        # Parse JSON fields safely
        for json_field, default_val in [
            ("score_breakdown", {}),
            ("match_reasons", []),
            ("missing_information", [])
        ]:
            if d.get(json_field):
                try:
                    d[json_field] = json.loads(d[json_field])
                except Exception:
                    d[json_field] = default_val
            else:
                d[json_field] = default_val
        result.append(d)
    return result

# --- Outreach Instructions & Email Drafts CRUD ---

def get_outreach_settings() -> Dict[str, Any]:
    """Retrieves user's editable outreach instructions & template settings."""
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM outreach_settings WHERE id = 1").fetchone()
    conn.close()
    if row:
        return dict(row)
    # Default fallback
    return {
        "id": 1,
        "purpose": "PhD Advisorship & Research Assistantship Inquiry",
        "target_degree_intake": "Ph.D. in Computer Science (Fall 2026)",
        "tone_and_length": "Professional, concise, scholarly; under 200 words",
        "specific_request": "Request a brief 15-minute introductory video call to discuss potential research synergy and prospective Ph.D. opportunities.",
        "background_to_emphasize": "Strong foundation in AI/ML research, 3.95 GPA, hands-on PyTorch engineering, and published work in NLP.",
        "signature": "Sincerely,\n[Candidate Name]\nApplicant, Graduate Research\nEmail: candidate@alumni.univ.edu\nPortfolio: https://github.com/scholarscout-candidate",
        "proposed_attachments": "Academic CV (PDF), Unofficial Transcript, 1-page Research Summary",
        "optional_wording_preferences": "Focus strictly on specific lab publications and neuro-symbolic research; avoid generic flattery or assumptions about guaranteed funding."
    }

def save_outreach_settings(data: Dict[str, Any]) -> Dict[str, Any]:
    """Updates user's editable outreach instructions & template settings."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE outreach_settings SET
        purpose = ?,
        target_degree_intake = ?,
        tone_and_length = ?,
        specific_request = ?,
        background_to_emphasize = ?,
        signature = ?,
        proposed_attachments = ?,
        optional_wording_preferences = ?,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = 1
    """, (
        data.get("purpose", "").strip(),
        data.get("target_degree_intake", "").strip(),
        data.get("tone_and_length", "").strip(),
        data.get("specific_request", "").strip(),
        data.get("background_to_emphasize", "").strip(),
        data.get("signature", "").strip(),
        data.get("proposed_attachments", "").strip(),
        data.get("optional_wording_preferences", "").strip()
    ))
    if cursor.rowcount == 0:
        cursor.execute("""
        INSERT INTO outreach_settings (
            id, purpose, target_degree_intake, tone_and_length, specific_request,
            background_to_emphasize, signature, proposed_attachments, optional_wording_preferences
        ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("purpose", "").strip(),
            data.get("target_degree_intake", "").strip(),
            data.get("tone_and_length", "").strip(),
            data.get("specific_request", "").strip(),
            data.get("background_to_emphasize", "").strip(),
            data.get("signature", "").strip(),
            data.get("proposed_attachments", "").strip(),
            data.get("optional_wording_preferences", "").strip()
        ))
    conn.commit()
    conn.close()
    return get_outreach_settings()

def save_email_draft(data: Dict[str, Any]) -> int:
    """
    Saves or updates an outreach email draft.
    Computes exact version content hash.
    Automatically invalidates prior approval if recipient, subject, body, or attachments are edited.
    """
    from backend.emails.security import compute_content_hash

    conn = get_db_connection()
    cursor = conn.cursor()
    draft_id = data.get("id")
    profile_version = data.get("profile_version", 1)

    raw_attachments = data.get("attachments", ["Academic CV (PDF)"])
    if isinstance(raw_attachments, str):
        try:
            attachments_list = json.loads(raw_attachments)
        except Exception:
            attachments_list = [raw_attachments]
    else:
        attachments_list = raw_attachments or ["Academic CV (PDF)"]

    attachments_val = json.dumps(attachments_list)

    evidence_val = data.get("evidence_used", {})
    if isinstance(evidence_val, dict):
        evidence_val = json.dumps(evidence_val)

    outreach_inst_val = data.get("outreach_instructions", {})
    if isinstance(outreach_inst_val, dict):
        outreach_inst_val = json.dumps(outreach_inst_val)

    recipient_email = data.get("recipient_email", "").strip()
    recipient_name = data.get("recipient_name", "").strip()
    subject = data.get("subject", "").strip()
    body_text = data.get("body_text", "").strip()

    # Calculate current version hash
    current_content_hash = compute_content_hash(
        recipient_email=recipient_email,
        subject=subject,
        body_text=body_text,
        attachments=attachments_list
    )

    if draft_id:
        # Check existing draft to detect if edits invalidate approval
        existing_row = cursor.execute("SELECT approval_status, approved_content_hash FROM email_drafts WHERE id = ?", (draft_id,)).fetchone()
        approval_status = data.get("approval_status", "draft")
        approved_content_hash = data.get("approved_content_hash")

        if existing_row:
            prev_approved_hash = existing_row["approved_content_hash"]
            if prev_approved_hash and prev_approved_hash != current_content_hash:
                # Content changed! Invalidate approval
                approval_status = "draft"
                approved_content_hash = None
            elif existing_row["approval_status"] == "approved" and prev_approved_hash == current_content_hash:
                approval_status = "approved"
                approved_content_hash = prev_approved_hash

        cursor.execute("""
        UPDATE email_drafts SET
            subject = ?,
            body_text = ?,
            recipient_name = ?,
            recipient_email = ?,
            recipient_role = ?,
            draft_type = ?,
            attachments = ?,
            evidence_used = ?,
            outreach_instructions = ?,
            contact_instructions_flag = ?,
            contact_instructions_notes = ?,
            unsupported_claims_flag = ?,
            unsupported_claims_notes = ?,
            status = ?,
            is_reviewed = ?,
            content_hash = ?,
            approval_status = ?,
            approved_content_hash = ?,
            follow_up_sequence = ?,
            parent_draft_id = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """, (
            subject,
            body_text,
            recipient_name,
            recipient_email,
            data.get("recipient_role", "Faculty / PI").strip(),
            data.get("draft_type", "Professor Research Inquiry").strip(),
            attachments_val,
            evidence_val,
            outreach_inst_val,
            data.get("contact_instructions_flag", "standard").strip(),
            data.get("contact_instructions_notes", "").strip(),
            1 if data.get("unsupported_claims_flag") else 0,
            data.get("unsupported_claims_notes", "").strip(),
            data.get("status", "draft").strip(),
            1 if data.get("is_reviewed") else 0,
            current_content_hash,
            approval_status,
            approved_content_hash,
            data.get("follow_up_sequence", 0),
            data.get("parent_draft_id"),
            draft_id
        ))
    else:
        cursor.execute("""
        INSERT INTO email_drafts (
            job_id, professor_id, scholarship_id, profile_version, recipient_name,
            recipient_email, recipient_role, draft_type, subject, body_text,
            attachments, evidence_used, outreach_instructions, contact_instructions_flag,
            contact_instructions_notes, unsupported_claims_flag, unsupported_claims_notes,
            status, is_reviewed, safety_notice, content_hash, approval_status,
            follow_up_sequence, parent_draft_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("job_id"),
            data.get("professor_id"),
            data.get("scholarship_id"),
            profile_version,
            recipient_name,
            recipient_email,
            data.get("recipient_role", "Faculty / PI").strip(),
            data.get("draft_type", "Professor Research Inquiry").strip(),
            subject,
            body_text,
            attachments_val,
            evidence_val,
            outreach_inst_val,
            data.get("contact_instructions_flag", "standard").strip(),
            data.get("contact_instructions_notes", "").strip(),
            1 if data.get("unsupported_claims_flag") else 0,
            data.get("unsupported_claims_notes", "").strip(),
            data.get("status", "draft").strip(),
            1 if data.get("is_reviewed") else 0,
            data.get("safety_notice", "Sending is disabled by default. Please review, edit, approve, and send under controlled dispatch."),
            current_content_hash,
            data.get("approval_status", "draft"),
            data.get("follow_up_sequence", 0),
            data.get("parent_draft_id")
        ))
        draft_id = cursor.lastrowid

    conn.commit()
    conn.close()
    return draft_id

def _parse_draft_row(r: Any) -> Dict[str, Any]:
    """Helper to convert database row to enriched email draft dict with parsed JSON fields."""
    d = dict(r)
    d["can_send"] = 0
    # Parse attachments
    if d.get("attachments"):
        try:
            d["attachments"] = json.loads(d["attachments"])
        except Exception:
            d["attachments"] = ["Academic CV (PDF)"]
    else:
        d["attachments"] = ["Academic CV (PDF)"]

    # Parse evidence_used
    if d.get("evidence_used"):
        try:
            d["evidence_used"] = json.loads(d["evidence_used"])
        except Exception:
            d["evidence_used"] = {}
    else:
        d["evidence_used"] = {}

    # Parse outreach_instructions
    if d.get("outreach_instructions"):
        try:
            d["outreach_instructions"] = json.loads(d["outreach_instructions"])
        except Exception:
            d["outreach_instructions"] = {}
    else:
        d["outreach_instructions"] = {}

    d["approval_status"] = d.get("approval_status") or "draft"
    d["content_hash"] = d.get("content_hash") or ""
    d["approved_content_hash"] = d.get("approved_content_hash") or ""
    d["follow_up_sequence"] = d.get("follow_up_sequence") or 0
    d["reply_status"] = d.get("reply_status") or "no_reply"

    return d

def get_email_drafts(status: Optional[str] = None, search: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves all outreach email drafts with optional status and search filtering."""
    conn = get_db_connection()
    conditions = []
    params: List[Any] = []

    if status and status != "all":
        conditions.append("d.status = ?")
        params.append(status.strip())

    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        conditions.append("(LOWER(d.recipient_name) LIKE ? OR LOWER(d.recipient_email) LIKE ? OR LOWER(d.subject) LIKE ? OR LOWER(d.body_text) LIKE ? OR LOWER(p.name) LIKE ? OR LOWER(rj.university_name) LIKE ?)")
        params.extend([term, term, term, term, term, term])

    where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
    sql = f"""
    SELECT d.*, 
           rj.university_name, rj.university_url, 
           p.name as prof_name, p.department as prof_dept, p.university as prof_university,
           p.research_interests as prof_interests, p.lab_url as prof_lab_url,
           p.official_profile_url as prof_profile_url, p.contact_instructions as prof_contact_instructions,
           p.recruitment_status as prof_recruitment_status, p.recruitment_evidence as prof_recruitment_evidence
    FROM email_drafts d
    LEFT JOIN research_jobs rj ON d.job_id = rj.id
    LEFT JOIN professors p ON d.professor_id = p.id
    {where_clause}
    ORDER BY d.updated_at DESC, d.id DESC
    """
    rows = conn.execute(sql, tuple(params)).fetchall()
    conn.close()
    return [_parse_draft_row(r) for r in rows]

def get_email_draft(draft_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves a single email draft by ID with enriched professor and university data."""
    conn = get_db_connection()
    row = conn.execute("""
    SELECT d.*, 
           rj.university_name, rj.university_url, 
           p.name as prof_name, p.department as prof_dept, p.university as prof_university,
           p.research_interests as prof_interests, p.lab_url as prof_lab_url,
           p.official_profile_url as prof_profile_url, p.contact_instructions as prof_contact_instructions,
           p.recruitment_status as prof_recruitment_status, p.recruitment_evidence as prof_recruitment_evidence
    FROM email_drafts d
    LEFT JOIN research_jobs rj ON d.job_id = rj.id
    LEFT JOIN professors p ON d.professor_id = p.id
    WHERE d.id = ?
    """, (draft_id,)).fetchone()
    conn.close()
    if not row:
        return None
    return _parse_draft_row(row)

def update_email_draft_status(draft_id: int, status: str, is_reviewed: Optional[bool] = None) -> bool:
    """Updates the review and verification status of a draft."""
    conn = get_db_connection()
    cursor = conn.cursor()
    if is_reviewed is not None:
        cursor.execute("""
        UPDATE email_drafts SET status = ?, is_reviewed = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?
        """, (status.strip(), 1 if is_reviewed else 0, draft_id))
    else:
        cursor.execute("""
        UPDATE email_drafts SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?
        """, (status.strip(), draft_id))
    success = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return success

def delete_email_draft(draft_id: int) -> bool:
    """Deletes an email draft."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM email_drafts WHERE id = ?", (draft_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

def record_crawled_page(
    job_id: int,
    url: str,
    page_title: str,
    page_type: str,
    status_code: int,
    retrieval_method: str = "http",
    normalized_url: Optional[str] = None,
    page_status: str = "success",
    status_reason: str = "",
    selection_reason: str = "",
    content_hash: str = "",
    byte_size: int = 0,
    depth: int = 0,
    is_external: bool = False,
    external_domain_type: str = "official_university"
):
    """Records a crawled page with complete provenance, selection reason, content hash, and status."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO crawl_pages (
        job_id, url, normalized_url, page_title, page_type, page_status,
        status_code, status_reason, selection_reason, retrieval_method,
        content_hash, byte_size, depth, is_external, external_domain_type
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        job_id, url, normalized_url or url, page_title[:500] if page_title else "",
        page_type, page_status, status_code, status_reason, selection_reason,
        retrieval_method, content_hash, byte_size, depth,
        1 if is_external else 0, external_domain_type
    ))
    conn.commit()
    conn.close()

def get_crawled_pages(job_id: Optional[int] = None, limit: int = 500) -> List[Dict[str, Any]]:
    """Retrieves all visited pages with optional job_id filter ordered chronologically."""
    conn = get_db_connection()
    if job_id:
        rows = conn.execute("""
        SELECT * FROM crawl_pages WHERE job_id = ? ORDER BY id ASC LIMIT ?
        """, (job_id, limit)).fetchall()
    else:
        rows = conn.execute("""
        SELECT * FROM crawl_pages ORDER BY id DESC LIMIT ?
        """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def insert_external_leads(job_id: int, leads: List[Dict[str, Any]]) -> int:
    """Inserts discovered third-party funding leads for human review."""
    if not leads:
        return 0
    conn = get_db_connection()
    cursor = conn.cursor()
    count = 0
    for lead in leads:
        cursor.execute("""
        INSERT INTO external_leads (
            job_id, domain, lead_title, url, lead_type, context_snippet, source_page_url, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_id,
            lead.get("domain", ""),
            lead.get("lead_title", "External Scholarship"),
            lead.get("url", ""),
            lead.get("lead_type", "external_lead"),
            lead.get("context_snippet", ""),
            lead.get("source_page_url", ""),
            lead.get("status", "discovered")
        ))
        count += 1
    conn.commit()
    conn.close()
    return count

def get_external_leads(job_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Retrieves cataloged external funding leads."""
    conn = get_db_connection()
    if job_id:
        rows = conn.execute("""
        SELECT * FROM external_leads WHERE job_id = ? ORDER BY id DESC
        """, (job_id,)).fetchall()
    else:
        rows = conn.execute("""
        SELECT * FROM external_leads ORDER BY id DESC
        """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_stats() -> Dict[str, Any]:
    """Summary metrics for the dashboard."""
    conn = get_db_connection()
    c = conn.cursor()
    jobs_count = c.execute("SELECT COUNT(*) FROM research_jobs").fetchone()[0]
    active_jobs = c.execute("SELECT COUNT(*) FROM research_jobs WHERE status IN ('queued', 'running')").fetchone()[0]
    scholarships_count = c.execute("SELECT COUNT(*) FROM scholarships").fetchone()[0]
    professors_count = c.execute("SELECT COUNT(*) FROM professors").fetchone()[0]
    drafts_count = c.execute("SELECT COUNT(*) FROM email_drafts").fetchone()[0]
    top_scholarships = c.execute("SELECT COUNT(*) FROM scholarships WHERE fit_score >= 80").fetchone()[0]
    top_professors = c.execute("SELECT COUNT(*) FROM professors WHERE match_score >= 80").fetchone()[0]

    llm_totals = c.execute("SELECT SUM(llm_total_tokens), SUM(llm_requests_count) FROM research_jobs").fetchone()
    total_llm_tokens = llm_totals[0] or 0
    total_llm_requests = llm_totals[1] or 0

    conn.close()

    return {
        "jobs_count": jobs_count,
        "active_jobs": active_jobs,
        "scholarships_count": scholarships_count,
        "professors_count": professors_count,
        "drafts_count": drafts_count,
        "top_scholarships": top_scholarships,
        "top_professors": top_professors,
        "total_llm_tokens": total_llm_tokens,
        "total_llm_requests": total_llm_requests
    }

# --- Shortlisting, Notes & Tracked Universities ---

def extract_domain_from_url(url: str) -> str:
    """Extracts a clean normalized domain (e.g. cmu.edu) from a URL or string."""
    if not url or url.startswith("discovery://"):
        return ""
    try:
        clean_url = url if "://" in url else f"https://{url}"
        parsed = urlparse(clean_url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain.strip()
    except Exception:
        return ""

def get_tracked_universities(
    search: Optional[str] = None,
    country: Optional[str] = None,
    shortlisted_only: bool = False,
    sort_by: str = "name",
    randomize: bool = False
) -> List[Dict[str, Any]]:
    """
    Returns unified list of tracked universities aggregated from research_jobs,
    scholarships, professors, crawl_pages, university_bookmarks, and the global catalog.
    Supports country-specific listing, real-time random global sampling, and search.
    """
    import random
    from backend.discovery.global_directory import GLOBAL_UNIVERSITIES_CATALOG, normalize_country_name

    conn = get_db_connection()
    c = conn.cursor()

    # 1. University Bookmarks
    bookmarks_rows = c.execute("SELECT * FROM university_bookmarks").fetchall()
    bookmarks_map = {r["domain"]: dict(r) for r in bookmarks_rows}

    # 2. Aggregation map keyed by domain / university identifier
    univ_map: Dict[str, Dict[str, Any]] = {}

    def get_entry(dom: str, name: str = "", ctry: str = "", sample_url: str = ""):
        dom = dom.lower().strip() if dom else ""
        key = dom or (name.lower().strip() if name else "unknown")
        if not key or key in ("unknown", "n/a", "none"):
            return None
        norm_c = normalize_country_name(ctry) if ctry else "Unknown"
        if key not in univ_map:
            bookmark = bookmarks_map.get(dom or key, {})
            b_country = normalize_country_name(bookmark.get("country")) if bookmark.get("country") else "Unknown"
            final_country = b_country if b_country != "Unknown" else norm_c
            univ_map[key] = {
                "domain": dom or key,
                "university_name": bookmark.get("university_name") or name or dom or "Unknown University",
                "country": final_country,
                "lead_url": bookmark.get("lead_url") or sample_url or (f"https://{dom}" if dom and "." in dom else ""),
                "jobs_count": 0,
                "pages_crawled": 0,
                "scholarships_count": 0,
                "professors_count": 0,
                "last_checked": bookmark.get("updated_at") or "",
                "is_shortlisted": bool(bookmark.get("is_shortlisted", 0)),
                "notes": bookmark.get("notes", ""),
                "status": "catalog"
            }
        else:
            if name and (univ_map[key]["university_name"] in ("Unknown University", dom) or len(name) > len(univ_map[key]["university_name"])):
                univ_map[key]["university_name"] = name
            if norm_c != "Unknown" and (univ_map[key]["country"] in ("Unknown", "") or univ_map[key]["country"] == "USA"):
                univ_map[key]["country"] = norm_c
            if sample_url and not univ_map[key]["lead_url"]:
                univ_map[key]["lead_url"] = sample_url
        return univ_map[key]

    # Pre-seed from global directory
    for gu in GLOBAL_UNIVERSITIES_CATALOG:
        dom = gu.get("domain", "")
        name = gu.get("name", "")
        ctry = gu.get("country", "")
        url = gu.get("url", "")
        get_entry(dom, name, ctry, url)

    # Pre-populate from bookmarks
    for dom, b in bookmarks_map.items():
        entry = get_entry(dom, b.get("university_name", ""), b.get("country", ""), b.get("lead_url", ""))
        if entry:
            entry["is_shortlisted"] = bool(b.get("is_shortlisted", 0))
            entry["notes"] = b.get("notes", "")

    # Populate from research_jobs
    job_rows = c.execute("""
        SELECT id, university_name, university_url, status, pages_crawled,
               scholarships_count, professors_count, job_type, discovered_institutions,
               created_at
        FROM research_jobs
        ORDER BY created_at ASC
    """).fetchall()

    for job in job_rows:
        job_url = job["university_url"] or ""
        job_name = job["university_name"] or ""
        created_at = job["created_at"] or ""
        
        if job["job_type"] == "discovery_job" and job["discovered_institutions"]:
            try:
                insts = json.loads(job["discovered_institutions"]) if isinstance(job["discovered_institutions"], str) else job["discovered_institutions"]
                for inst in insts:
                    dom = inst.get("domain") or extract_domain_from_url(inst.get("lead_url", ""))
                    name = inst.get("name") or inst.get("institution_name") or ""
                    ctry = inst.get("country") or ""
                    lead = inst.get("lead_url") or ""
                    entry = get_entry(dom, name, ctry, lead)
                    if entry:
                        if created_at and (not entry["last_checked"] or created_at > entry["last_checked"]):
                            entry["last_checked"] = created_at
            except Exception:
                pass
        else:
            dom = extract_domain_from_url(job_url)
            entry = get_entry(dom, job_name, "", job_url)
            if entry:
                entry["jobs_count"] += 1
                entry["pages_crawled"] += (job["pages_crawled"] or 0)
                entry["scholarships_count"] += (job["scholarships_count"] or 0)
                entry["professors_count"] += (job["professors_count"] or 0)
                if job["status"] == "completed":
                    entry["status"] = "crawled"
                elif job["status"] in ("running", "queued"):
                    entry["status"] = "active"
                if created_at and (not entry["last_checked"] or created_at > entry["last_checked"]):
                    entry["last_checked"] = created_at

    # Populate / refine from scholarships
    s_rows = c.execute("""
        SELECT university, country, COUNT(*) as cnt, MAX(created_at) as last_seen, MAX(source_url) as sample_source
        FROM scholarships
        GROUP BY university, country
    """).fetchall()
    for s in s_rows:
        name = s["university"]
        ctry = s["country"]
        cnt = s["cnt"]
        last_seen = s["last_seen"]
        sample_url = s["sample_source"]
        dom = extract_domain_from_url(sample_url)
        entry = get_entry(dom, name, ctry, sample_url)
        if entry:
            if entry["scholarships_count"] < cnt:
                entry["scholarships_count"] = cnt
            if last_seen and (not entry["last_checked"] or last_seen > entry["last_checked"]):
                entry["last_checked"] = last_seen
            if ctry and ctry != "Unknown":
                entry["country"] = ctry

    # Populate / refine from professors
    p_rows = c.execute("""
        SELECT university, COUNT(*) as cnt, MAX(created_at) as last_seen, MAX(source_url) as sample_source
        FROM professors
        GROUP BY university
    """).fetchall()
    for p in p_rows:
        name = p["university"]
        cnt = p["cnt"]
        last_seen = p["last_seen"]
        sample_url = p["sample_source"]
        dom = extract_domain_from_url(sample_url)
        entry = get_entry(dom, name, "", sample_url)
        if entry:
            if entry["professors_count"] < cnt:
                entry["professors_count"] = cnt
            if last_seen and (not entry["last_checked"] or last_seen > entry["last_checked"]):
                entry["last_checked"] = last_seen

    conn.close()

    items = list(univ_map.values())

    # Apply filters
    if shortlisted_only:
        items = [u for u in items if u["is_shortlisted"]]
    if country and country.strip() and country.lower() != "all":
        norm_filter_country = normalize_country_name(country).lower()
        items = [
            u for u in items
            if norm_filter_country in u["country"].lower() or country.strip().lower() in u["country"].lower()
        ]
    if search and search.strip():
        s_term = search.strip().lower()
        items = [
            u for u in items
            if s_term in u["university_name"].lower()
            or s_term in u["domain"].lower()
            or s_term in u["country"].lower()
            or s_term in u["notes"].lower()
        ]

    # Apply sorting
    if sort_by == "random" or randomize:
        random.seed()
        random.shuffle(items)
    elif sort_by == "scholarships":
        items.sort(key=lambda x: (x["scholarships_count"], x["professors_count"]), reverse=True)
    elif sort_by == "professors":
        items.sort(key=lambda x: (x["professors_count"], x["scholarships_count"]), reverse=True)
    elif sort_by == "pages":
        items.sort(key=lambda x: x["pages_crawled"], reverse=True)
    elif sort_by == "country":
        items.sort(key=lambda x: (x["country"].lower(), x["university_name"].lower()))
    elif sort_by == "recent":
        items.sort(key=lambda x: x["last_checked"] or "", reverse=True)
    else: # name
        items.sort(key=lambda x: x["university_name"].lower())

    return items

def create_or_update_university(
    domain: str,
    university_name: str,
    country: str = "Unknown",
    lead_url: str = "",
    notes: str = "",
    is_shortlisted: Optional[bool] = None
) -> Dict[str, Any]:
    """Creates or updates a tracked university in university_bookmarks."""
    from backend.discovery.global_directory import normalize_country_name
    if not domain:
        domain = extract_domain_from_url(lead_url)
    domain = domain.lower().strip()
    norm_country = normalize_country_name(country) if country else "Unknown"
    
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT * FROM university_bookmarks WHERE domain = ?", (domain,)).fetchone()
    if row:
        new_shortlist = bool(row["is_shortlisted"]) if is_shortlisted is None else bool(is_shortlisted)
        new_notes = notes.strip() if notes is not None else (row["notes"] or "")
        new_name = university_name.strip() if university_name else row["university_name"]
        new_country = norm_country if norm_country != "Unknown" else row["country"]
        new_lead = lead_url.strip() if lead_url else row["lead_url"]
        
        cursor.execute("""
            UPDATE university_bookmarks
            SET university_name = ?, country = ?, lead_url = ?, is_shortlisted = ?, notes = ?, updated_at = CURRENT_TIMESTAMP
            WHERE domain = ?
        """, (new_name, new_country, new_lead, 1 if new_shortlist else 0, new_notes, domain))
    else:
        new_shortlist = bool(is_shortlisted) if is_shortlisted is not None else False
        cursor.execute("""
            INSERT INTO university_bookmarks (domain, university_name, country, lead_url, is_shortlisted, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (domain, university_name.strip() or domain, norm_country, lead_url.strip(), 1 if new_shortlist else 0, (notes or "").strip()))
    
    conn.commit()
    conn.close()
    return {
        "domain": domain,
        "university_name": university_name or domain,
        "country": norm_country,
        "lead_url": lead_url,
        "is_shortlisted": bool(is_shortlisted),
        "notes": notes
    }

def delete_university_bookmark(domain: str) -> bool:
    """Deletes/untracks a university from university_bookmarks."""
    if not domain:
        return False
    domain = domain.lower().strip()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM university_bookmarks WHERE domain = ?", (domain,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

def toggle_university_shortlist(
    domain: str,
    is_shortlisted: Optional[bool] = None,
    university_name: str = "",
    country: str = "",
    lead_url: str = ""
) -> bool:
    """Toggles or sets the shortlist status for a university domain."""
    if not domain:
        return False
    domain = domain.lower().strip()
    conn = get_db_connection()
    cursor = conn.cursor()
    
    row = cursor.execute("SELECT * FROM university_bookmarks WHERE domain = ?", (domain,)).fetchone()
    if row:
        current = bool(row["is_shortlisted"])
        new_val = (not current) if is_shortlisted is None else bool(is_shortlisted)
        cursor.execute("""
            UPDATE university_bookmarks
            SET is_shortlisted = ?, updated_at = CURRENT_TIMESTAMP
            WHERE domain = ?
        """, (1 if new_val else 0, domain))
    else:
        new_val = True if is_shortlisted is None else bool(is_shortlisted)
        cursor.execute("""
            INSERT INTO university_bookmarks (domain, university_name, country, lead_url, is_shortlisted, notes)
            VALUES (?, ?, ?, ?, ?, '')
        """, (domain, university_name or domain, country or "Unknown", lead_url or "", 1 if new_val else 0))
    
    conn.commit()
    conn.close()
    return new_val

def save_university_notes(
    domain: str,
    notes: str,
    university_name: str = "",
    country: str = "",
    lead_url: str = ""
) -> bool:
    """Saves personal notes for a university domain."""
    if not domain:
        return False
    domain = domain.lower().strip()
    conn = get_db_connection()
    cursor = conn.cursor()
    
    row = cursor.execute("SELECT * FROM university_bookmarks WHERE domain = ?", (domain,)).fetchone()
    if row:
        cursor.execute("""
            UPDATE university_bookmarks
            SET notes = ?, updated_at = CURRENT_TIMESTAMP
            WHERE domain = ?
        """, (notes.strip(), domain))
    else:
        cursor.execute("""
            INSERT INTO university_bookmarks (domain, university_name, country, lead_url, is_shortlisted, notes)
            VALUES (?, ?, ?, ?, 0, ?)
        """, (domain, university_name or domain, country or "Unknown", lead_url or "", notes.strip()))
    
    conn.commit()
    conn.close()
    return True

def toggle_scholarship_shortlist(scholarship_id: int, is_shortlisted: Optional[bool] = None) -> bool:
    """Toggles or sets shortlist status for a scholarship finding."""
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT is_shortlisted FROM scholarships WHERE id = ?", (scholarship_id,)).fetchone()
    if not row:
        conn.close()
        return False
    current = bool(row["is_shortlisted"])
    new_val = (not current) if is_shortlisted is None else bool(is_shortlisted)
    cursor.execute("UPDATE scholarships SET is_shortlisted = ? WHERE id = ?", (1 if new_val else 0, scholarship_id))
    conn.commit()
    conn.close()
    return new_val

def save_scholarship_notes(scholarship_id: int, notes: str) -> bool:
    """Saves personal notes for a scholarship finding."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE scholarships SET notes = ? WHERE id = ?", (notes.strip(), scholarship_id))
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated

def toggle_professor_shortlist(professor_id: int, is_shortlisted: Optional[bool] = None) -> bool:
    """Toggles or sets shortlist status for a professor finding."""
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT is_shortlisted FROM professors WHERE id = ?", (professor_id,)).fetchone()
    if not row:
        conn.close()
        return False
    current = bool(row["is_shortlisted"])
    new_val = (not current) if is_shortlisted is None else bool(is_shortlisted)
    cursor.execute("UPDATE professors SET is_shortlisted = ? WHERE id = ?", (1 if new_val else 0, professor_id))
    conn.commit()
    conn.close()
    return new_val

def save_professor_notes(professor_id: int, notes: str) -> bool:
    """Saves personal notes for a professor finding."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE professors SET notes = ? WHERE id = ?", (notes.strip(), professor_id))
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated

def get_shortlist_items() -> Dict[str, Any]:
    """Returns all shortlisted universities, scholarships, and professors."""
    universities = get_tracked_universities(shortlisted_only=True)
    scholarships = get_scholarships(is_shortlisted=True)
    professors = get_professors(is_shortlisted=True)
    
    return {
        "total_count": len(universities) + len(scholarships) + len(professors),
        "universities": universities,
        "scholarships": scholarships,
        "professors": professors
    }

def get_overview_data() -> Dict[str, Any]:
    """Aggregated real database statistics and top items for the Executive Overview screen."""
    stats = get_stats()
    all_jobs = get_all_jobs()
    top_scholarships = get_scholarships(min_fit_score=60)[:6]
    top_professors = get_professors(min_match_score=60)[:6]
    shortlist_summary = get_shortlist_items()
    tracked_univs = get_tracked_universities()
    
    conn = get_db_connection()
    c = conn.cursor()
    
    # Funding categories breakdown
    f_cat_counts = {}
    for r in c.execute("SELECT funding_category, COUNT(*) as cnt FROM scholarships GROUP BY funding_category").fetchall():
        f_cat_counts[r["funding_category"]] = r["cnt"]
        
    # Recruitment breakdown
    rec_counts = {}
    for r in c.execute("SELECT recruitment_status, COUNT(*) as cnt FROM professors GROUP BY recruitment_status").fetchall():
        rec_counts[r["recruitment_status"]] = r["cnt"]
        
    # Jobs status breakdown
    job_status_counts = {}
    for r in c.execute("SELECT status, COUNT(*) as cnt FROM research_jobs GROUP BY status").fetchall():
        job_status_counts[r["status"]] = r["cnt"]
        
    # Verified emails count
    verified_emails = c.execute("SELECT COUNT(*) FROM professors WHERE email NOT IN ('Not found', 'Unknown', 'None', '') AND email LIKE '%@%'").fetchone()[0]
    
    conn.close()
    
    return {
        "stats": stats,
        "total_universities_tracked": len(tracked_univs),
        "verified_emails_count": verified_emails,
        "job_status_breakdown": job_status_counts,
        "funding_categories_breakdown": f_cat_counts,
        "recruitment_status_breakdown": rec_counts,
        "shortlist_counts": {
            "total": shortlist_summary["total_count"],
            "universities": len(shortlist_summary["universities"]),
            "scholarships": len(shortlist_summary["scholarships"]),
            "professors": len(shortlist_summary["professors"])
        },
        "recent_jobs": all_jobs[:8],
        "top_scholarships": top_scholarships,
        "top_professors": top_professors
    }

if __name__ == "__main__":
    init_db()
