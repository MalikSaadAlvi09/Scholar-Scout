"""
FastAPI REST API Routes for ScholarScout.
Provides endpoints for health check, profiles with versioning & CV extraction,
research jobs, autonomous discovery mode, scholarships, professors, email drafts, and settings.
"""

from typing import Optional, List, Dict, Any, Union
from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File, Response
from pydantic import BaseModel, Field
import platform
from datetime import datetime, timezone
import json

from backend.config import config
from backend.database import (
    get_db_connection,
    get_all_profiles,
    get_active_profile,
    get_profile_by_id,
    enqueue_research_job,
    get_all_jobs,
    get_job,
    cancel_job,
    pause_job,
    resume_job,
    get_job_coverage,
    get_scholarships,
    get_professors,
    get_email_drafts,
    get_email_draft,
    save_email_draft,
    update_email_draft_status,
    delete_email_draft,
    get_outreach_settings,
    save_outreach_settings,
    get_stats,
    get_crawled_pages,
    get_external_leads,
    get_tracked_universities,
    create_or_update_university,
    delete_university_bookmark,
    toggle_university_shortlist,
    save_university_notes,
    toggle_scholarship_shortlist,
    save_scholarship_notes,
    toggle_professor_shortlist,
    save_professor_notes,
    get_shortlist_items,
    get_overview_data,
    get_evidence_history,
    get_recent_evidence_changes,
    mark_stale_records
)
from backend.export.data_exporter import (
    export_scholarships_csv,
    export_scholarships_json,
    export_professors_csv,
    export_professors_json,
    export_sources_csv,
    export_sources_json,
    export_outreach_csv,
    export_outreach_json,
    export_redacted_diagnostics,
    export_gathering_pipeline_excel,
    export_gathering_pipeline_csv
)
from backend.agents.gathering_agent import gathering_agent, AgentRunConfig
from backend.config import config, NVIDIA_MODELS_CATALOG
from backend.export.backup_manager import (
    create_database_backup,
    list_database_backups,
    restore_database_backup,
    delete_database_backup
)
from backend.jobs.rechecks import (
    get_scheduled_rechecks,
    create_scheduled_recheck,
    update_scheduled_recheck,
    delete_scheduled_recheck,
    check_and_run_due_rechecks
)
from backend.profiles.manager import (
    get_current_profile,
    update_or_create_profile,
    get_profile_history,
    get_task_specific_profile,
    calculate_completeness
)
from backend.profiles.cv_parser import extract_facts_from_cv
from backend.discovery.search_providers import get_search_provider
from backend.discovery.query_generator import generate_discovery_queries
from backend.discovery.engine import DiscoveryEngine
from backend.llm.client import ai_client
from backend.llm.nemotron_client import nemotron_client
from backend.llm.exceptions import MissingCredentialsError
from backend.emails.generator import create_outreach_draft
from backend.logging_utils import logger

router = APIRouter(prefix="/api")

# --- Request/Response Models ---

class ProfileRequest(BaseModel):
    id: Optional[int] = None
    full_name: Optional[str] = None
    name: Optional[str] = None
    nationality: Optional[str] = "Unknown"
    country_of_origin: Optional[str] = None
    current_residence: Optional[str] = "Unknown"

    current_degree: Optional[str] = "Unknown"
    current_institution: Optional[str] = "Unknown"
    current_major: Optional[str] = "Computer Science"
    gpa: Optional[str] = "Unknown"
    graduation_date: Optional[str] = "Unknown"

    target_degree: Optional[str] = "Ph.D."
    broad_subject: Optional[str] = "Computer Science"
    target_field: Optional[str] = None
    specific_interests: Optional[str] = ""
    research_interests: Optional[str] = None
    intended_intake: Optional[str] = "Unknown"

    preferred_countries: Optional[Union[List[str], str]] = None
    excluded_countries: Optional[Union[List[str], str]] = None

    english_tests: Optional[str] = "Unknown"

    projects: Optional[str] = ""
    publications: Optional[str] = ""
    research_experience: Optional[str] = ""
    technical_skills: Optional[str] = ""
    background_summary: Optional[str] = ""

    funding_needs: Optional[Union[List[str], str]] = None
    funding_notes: Optional[str] = ""

    portfolio_url: Optional[str] = ""
    github_url: Optional[str] = ""
    website_url: Optional[str] = ""

    is_active: bool = Field(True)

class ResearchJobRequest(BaseModel):
    university_url: Optional[str] = Field(None, json_schema_extra={"example": "https://cs.cmu.edu"})
    university_urls: Optional[Union[List[str], str]] = Field(None, description="One or more target university URLs")
    university_name: Optional[str] = Field(None, json_schema_extra={"example": "Carnegie Mellon University"})
    profile_id: Optional[int] = None
    scope: str = Field("all", description="Research scope: all, funding, faculty, admissions_programs, positions")
    max_pages: Optional[int] = Field(None, description="Max pages to crawl per university")
    max_depth: Optional[int] = Field(3, description="Max link depth")
    time_limit_seconds: Optional[int] = Field(120, description="Max crawl duration in seconds")

class DiscoveryQueryGenerateRequest(BaseModel):
    profile_id: Optional[int] = None
    max_queries: Optional[int] = 5
    custom_keywords: Optional[Union[List[str], str]] = None

class DiscoveryStartRequest(BaseModel):
    profile_id: Optional[int] = None
    scope: str = "all"
    max_universities: Optional[int] = None
    max_queries: Optional[int] = None
    queries: Optional[List[Dict[str, Any]]] = None
    custom_keywords: Optional[Union[List[str], str]] = None
    max_pages: Optional[int] = None
    max_depth: Optional[int] = None
    time_limit_seconds: Optional[int] = None

class OutreachSettingsUpdateRequest(BaseModel):
    purpose: Optional[str] = None
    target_degree_intake: Optional[str] = None
    tone_and_length: Optional[str] = None
    specific_request: Optional[str] = None
    background_to_emphasize: Optional[str] = None
    signature: Optional[str] = None
    proposed_attachments: Optional[str] = None
    optional_wording_preferences: Optional[str] = None

class EmailDraftGenerateRequest(BaseModel):
    job_id: Optional[int] = None
    professor_id: Optional[int] = None
    scholarship_id: Optional[int] = None
    recipient_name: str
    recipient_email: str
    recipient_role: str = "Faculty / PI"
    draft_type: str = "Professor Research Inquiry"
    context_title: str = ""
    context_details: str = ""
    custom_instructions: Optional[Dict[str, Any]] = None

class BatchEmailDraftGenerateRequest(BaseModel):
    professor_ids: List[int]
    job_id: Optional[int] = None
    custom_instructions: Optional[Dict[str, Any]] = None

class EmailDraftUpdateRequest(BaseModel):
    subject: Optional[str] = None
    body_text: Optional[str] = None
    recipient_name: Optional[str] = None
    recipient_email: Optional[str] = None
    recipient_role: Optional[str] = None
    draft_type: Optional[str] = None
    attachments: Optional[List[str]] = None
    status: Optional[str] = None
    is_reviewed: Optional[bool] = None
    clear_claims_warning: Optional[bool] = False

class DraftStatusUpdateRequest(BaseModel):
    status: str
    is_reviewed: Optional[bool] = None
    force: Optional[bool] = False

class EmailAccountCreateRequest(BaseModel):
    name: str = Field(..., description="Human-readable account label")
    provider_type: str = Field("mock_sandbox", description="mock_sandbox, gmail_oauth, outlook_oauth, custom_smtp")
    email_address: str = Field(..., description="Sender academic email address")
    credentials: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Backend authentication config/tokens")
    hourly_limit: Optional[int] = 20
    daily_limit: Optional[int] = 100
    delay_between_sends_sec: Optional[int] = 15
    reply_sync_enabled: Optional[bool] = False
    is_active: Optional[bool] = True

class EmailAccountUpdateRequest(BaseModel):
    name: Optional[str] = None
    provider_type: Optional[str] = None
    email_address: Optional[str] = None
    credentials: Optional[Dict[str, Any]] = None
    hourly_limit: Optional[int] = None
    daily_limit: Optional[int] = None
    delay_between_sends_sec: Optional[int] = None
    reply_sync_enabled: Optional[bool] = None
    is_active: Optional[bool] = None

class MasterSendingToggleRequest(BaseModel):
    enabled: bool = Field(..., description="True to activate controlled sending, False to disable")
    confirmation_ack: Optional[bool] = Field(True, description="Explicit user confirmation")
    reason: Optional[str] = "User action"

class BatchApproveRequest(BaseModel):
    draft_ids: List[int]

class BatchQueueRequest(BaseModel):
    draft_ids: List[int]
    account_id: Optional[int] = None

class DoNotContactRequest(BaseModel):
    pattern: str = Field(..., description="Exact email or @domain.edu to suppress")
    reason: Optional[str] = "User manual suppression"

class FollowupGenerateRequest(BaseModel):
    parent_draft_id: int
    days_elapsed: Optional[int] = 7

class ShortlistToggleRequest(BaseModel):
    is_shortlisted: Optional[bool] = None
    university_name: Optional[str] = None
    country: Optional[str] = None
    lead_url: Optional[str] = None

class NotesUpdateRequest(BaseModel):
    notes: str = ""
    university_name: Optional[str] = None
    country: Optional[str] = None
    lead_url: Optional[str] = None

class UniversityCreateRequest(BaseModel):
    university_name: str = Field(..., description="Full official university name")
    lead_url: str = Field(..., description="Official website URL")
    domain: Optional[str] = Field(None, description="Domain identifier (e.g. mit.edu)")
    country: Optional[str] = Field("Unknown", description="Country name")
    notes: Optional[str] = Field("", description="Personal application notes")
    is_shortlisted: Optional[bool] = Field(False, description="Shortlist flag")

class UniversityUpdateRequest(BaseModel):
    university_name: Optional[str] = None
    lead_url: Optional[str] = None
    country: Optional[str] = None
    notes: Optional[str] = None
    is_shortlisted: Optional[bool] = None

class SettingsUpdateRequest(BaseModel):
    api_base_url: Optional[str] = None
    api_key: Optional[str] = None
    api_keys: Optional[Union[List[str], str]] = None
    model_name: Optional[str] = None
    fallback_models: Optional[Union[List[str], str]] = None
    crawl_max_pages: Optional[int] = None
    llm_timeout: Optional[float] = None
    llm_max_concurrency: Optional[int] = None
    job_max_llm_requests: Optional[int] = None
    job_max_llm_tokens: Optional[int] = None
    search_provider: Optional[str] = None
    search_api_key: Optional[str] = None
    search_max_queries: Optional[int] = None
    search_max_results: Optional[int] = None
    discovery_max_universities: Optional[int] = None

# --- Health Check ---

@router.get("/health")
async def health_check():
    """Application health check endpoint."""
    search_prov = get_search_provider()
    return {
        "status": "healthy",
        "app_name": "ScholarScout",
        "version": "1.0.0",
        "database": "sqlite_connected",
        "llm_configured": ai_client.is_configured(),
        "model_name": config.llm_model,
        "api_base_url": config.llm_base_url,
        "search_configured": search_prov.is_configured(),
        "search_provider": search_prov.provider_name,
        "llm_timeout": config.llm_timeout,
        "llm_max_concurrency": config.llm_max_concurrency,
        "job_max_llm_requests": config.job_max_llm_requests,
        "job_max_llm_tokens": config.job_max_llm_tokens,
        "server_time": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform()
    }

# --- Dashboard Stats & Executive Overview ---

@router.get("/stats")
async def get_dashboard_statistics():
    """Summary statistics for dashboard top cards."""
    return get_stats()

@router.get("/overview")
async def get_overview_dashboard_data():
    """Returns complete real database analytics, metrics, recent jobs, and top items for the Overview screen."""
    return get_overview_data()

# --- Profiles with Versioning & CV Extraction ---

@router.get("/profile")
async def get_current_active_profile_route():
    """Retrieve current active candidate profile with calculated completeness checklist."""
    return get_current_profile()

@router.post("/profile")
async def update_or_create_candidate_profile_route(req: ProfileRequest):
    """Save or update academic profile with automatic version incrementing and snapshotting."""
    saved_profile = update_or_create_profile(req.model_dump())
    return {
        "success": True,
        "profile": saved_profile,
        "version": saved_profile.get("version", 1),
        "message": f"Profile saved successfully (Version #{saved_profile.get('version', 1)} created)."
    }

@router.get("/profile/versions")
async def get_profile_version_history():
    """Returns chronological audit snapshots of the profile versions."""
    active = get_active_profile()
    if not active:
        return []
    return get_profile_history(active["id"])

@router.get("/profile/privacy-preview")
async def get_profile_privacy_preview():
    """
    Data minimization preview showing exactly which profile fields are
    sent to the AI provider for each specific task.
    """
    profile = get_current_profile()
    return {
        "scholarship_eligibility": get_task_specific_profile(profile, "scholarship_eligibility"),
        "professor_matching": get_task_specific_profile(profile, "professor_matching"),
        "email_drafting": get_task_specific_profile(profile, "email_drafting")
    }

@router.post("/profile/upload-cv")
async def upload_and_parse_cv(file: UploadFile = File(...)):
    """
    Uploads a CV in PDF or DOCX format, detects scanned/empty documents,
    extracts proposed candidate facts, and returns them for human review before merging.
    """
    try:
        contents = await file.read()
        if len(contents) == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        result = await extract_facts_from_cv(
            filename=file.filename or "cv_document",
            file_bytes=contents
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[CV Upload] Error processing file: {e}")
        return {
            "success": False,
            "error_type": "upload_error",
            "message": f"Failed to parse uploaded document: {str(e)}"
        }

@router.get("/profiles")
async def list_all_candidate_profiles():
    """Retrieve list of all candidate profiles."""
    return get_all_profiles()

# --- Autonomous Discovery Mode Endpoints ---

@router.post("/discovery/generate-queries")
async def api_generate_discovery_queries(req: DiscoveryQueryGenerateRequest):
    """
    Generates tailored, precision academic search queries based on the candidate's
    target degree, broad subject, research interests, country preferences, and intake year.
    """
    profile = None
    if req.profile_id:
        profile = get_profile_by_id(req.profile_id)
    if not profile:
        profile = get_active_profile() or {}

    max_q = req.max_queries or config.search_max_queries
    queries = generate_discovery_queries(profile, max_queries=max_q, custom_keywords=req.custom_keywords)

    provider = get_search_provider()
    return {
        "success": True,
        "queries": queries,
        "provider": provider.provider_name,
        "provider_display": provider.display_name,
        "is_provider_configured": provider.is_configured(),
        "total_generated": len(queries)
    }

@router.post("/discovery/preview")
async def api_preview_discovery_leads(req: DiscoveryStartRequest):
    """
    Executes discovery search across configured provider (with query caching)
    and returns discovered institutions, root domains, and third-party leads
    WITHOUT starting full webpage crawls.
    """
    profile = None
    if req.profile_id:
        profile = get_profile_by_id(req.profile_id)
    if not profile:
        profile = get_active_profile() or {}

    provider = get_search_provider()
    if not provider.is_configured():
        raise HTTPException(
            status_code=400,
            detail=(
                "No search provider configured. Please configure an API key for Tavily, SerpAPI, or Brave Search "
                "in backend settings, or use University URL Mode to import university URLs directly."
            )
        )

    engine = DiscoveryEngine(
        search_provider=provider,
        max_queries=req.max_queries or config.search_max_queries,
        max_results_per_query=config.search_max_results,
        max_universities=req.max_universities or config.discovery_max_universities
    )

    result = await engine.discover_institutions(profile, custom_queries=req.queries)
    return result

@router.post("/discovery/start")
async def api_start_discovery_job(req: DiscoveryStartRequest):
    """
    Enqueues an autonomous Discovery Mode job in the background queue.
    """
    profile = None
    if req.profile_id:
        profile = get_profile_by_id(req.profile_id)
    if not profile:
        profile = get_active_profile() or {}

    provider = get_search_provider()
    if not provider.is_configured():
        raise HTTPException(
            status_code=400,
            detail=(
                "No search provider configured. Please configure an API key for Tavily, SerpAPI, or Brave Search "
                "in backend settings, or use University URL Mode."
            )
        )

    profile_id = profile.get("id")
    profile_version = profile.get("version", 1)

    # Generate queries if not explicitly passed
    queries = req.queries or generate_discovery_queries(
        profile,
        max_queries=req.max_queries or config.search_max_queries,
        custom_keywords=req.custom_keywords
    )

    job_id = enqueue_research_job(
        university_url=f"discovery://{provider.provider_name}",
        profile_id=profile_id,
        university_name=f"Autonomous Discovery ({provider.display_name})",
        profile_version=profile_version,
        scope=req.scope or "all",
        max_pages=req.max_universities or config.discovery_max_universities,
        job_type="discovery_job",
        discovery_queries=queries
    )

    return {
        "success": True,
        "job_id": job_id,
        "job_type": "discovery_job",
        "provider": provider.provider_name,
        "queries_count": len(queries),
        "status": "queued",
        "message": f"Autonomous Discovery Job #{job_id} enqueued ({len(queries)} focused queries)."
    }

# --- Research Jobs ---

@router.post("/jobs")
async def start_research_job(req: ResearchJobRequest):
    """
    Enqueues one or more university research jobs, recording the selected scope,
    crawl limits, and profile version used.
    """
    # Parse target URL(s)
    raw_urls: List[str] = []
    if req.university_urls:
        if isinstance(req.university_urls, list):
            raw_urls.extend(req.university_urls)
        elif isinstance(req.university_urls, str):
            # Split on commas, newlines, or whitespace
            parts = [p.strip() for p in req.university_urls.replace("\n", ",").split(",") if p.strip()]
            raw_urls.extend(parts)
    elif req.university_url:
        raw_urls.append(req.university_url.strip())

    if not raw_urls:
        raise HTTPException(status_code=400, detail="Please provide at least one university URL.")

    # Resolve active profile
    active_profile = None
    if req.profile_id:
        active_profile = get_profile_by_id(req.profile_id)
    if not active_profile:
        active_profile = get_active_profile()

    profile_id = active_profile["id"] if active_profile else None
    profile_version = active_profile.get("version", 1) if active_profile else 1

    queued_jobs = []

    for raw_url in raw_urls:
        url = raw_url.strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        max_pages = req.max_pages or config.crawl_max_pages
        max_depth = req.max_depth or 3
        time_limit = req.time_limit_seconds or 120
        scope = req.scope or "all"

        job_id = enqueue_research_job(
            university_url=url,
            profile_id=profile_id,
            university_name=req.university_name or "",
            profile_version=profile_version,
            scope=scope,
            max_pages=max_pages,
            max_depth=max_depth,
            time_limit_seconds=time_limit,
            job_type="url_research"
        )

        queued_jobs.append({
            "job_id": job_id,
            "url": url,
            "scope": scope,
            "profile_version": profile_version
        })

    primary_job_id = queued_jobs[0]["job_id"]
    return {
        "success": True,
        "job_id": primary_job_id,
        "queued_jobs": queued_jobs,
        "profile_version": profile_version,
        "status": "queued",
        "message": f"Enqueued {len(queued_jobs)} university research run(s) (Scope: {req.scope}, Profile v{profile_version})."
    }

@router.get("/jobs")
async def list_research_jobs():
    """List all research jobs."""
    return get_all_jobs()

@router.get("/jobs/{job_id}")
async def get_research_job_status(job_id: int):
    """Get single research job status, metrics, and live logs."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.get("/jobs/{job_id}/coverage")
async def get_job_coverage_report_route(job_id: int):
    """Returns the comprehensive institutional coverage report for a research/discovery job."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return get_job_coverage(job_id)

@router.post("/jobs/{job_id}/pause")
async def pause_active_job(job_id: int):
    """Pauses a running or queued job."""
    success = pause_job(job_id, reason="Paused by user")
    return {"success": success, "message": "Job paused." if success else "Job could not be paused."}

@router.post("/jobs/{job_id}/resume")
async def resume_paused_job(job_id: int):
    """Resumes a paused job."""
    success = resume_job(job_id)
    return {"success": success, "message": "Job resumed." if success else "Job could not be resumed."}

@router.get("/jobs/{job_id}/pages")
async def get_research_job_pages(job_id: int):
    """Returns the complete activity log of pages visited during the crawl."""
    return get_crawled_pages(job_id)

@router.get("/jobs/{job_id}/external-leads")
async def get_research_job_external_leads(job_id: int):
    """Returns cataloged third-party funding leads discovered for this job."""
    return get_external_leads(job_id)

@router.get("/external-leads")
async def get_all_external_leads_route():
    """Returns all cataloged external scholarship and funding leads."""
    return get_external_leads()

@router.post("/jobs/{job_id}/cancel")
async def cancel_active_research_job(job_id: int):
    """Cancel a running or queued job."""
    success = cancel_job(job_id)
    return {"success": success, "message": "Job cancelled." if success else "Job could not be cancelled."}

# --- Global Directory & Countries ---

@router.get("/directory/countries")
async def list_global_countries():
    """Returns the list of all 195+ world countries with flag emojis, region, and university counts."""
    from backend.discovery.global_directory import get_all_global_countries
    return get_all_global_countries()

@router.get("/directory/universities")
async def list_global_directory_universities(
    country: Optional[str] = None,
    search: Optional[str] = None
):
    """Returns cataloged universities from the global directory filterable by country and keyword."""
    from backend.discovery.global_directory import get_global_universities_by_country
    return get_global_universities_by_country(country=country, search=search)

# --- Universities Directory & Real-Time Management ---

@router.get("/universities")
async def list_tracked_universities(
    search: Optional[str] = None,
    country: Optional[str] = None,
    shortlisted_only: bool = False,
    sort_by: str = "name",
    randomize: bool = False
):
    """List tracked and discovered universities with opportunity counts, faculty counts, and shortlist status."""
    return get_tracked_universities(
        search=search,
        country=country,
        shortlisted_only=shortlisted_only,
        sort_by=sort_by,
        randomize=randomize
    )

@router.post("/universities")
async def create_university_route(req: UniversityCreateRequest):
    """Add a new custom university to the directory in real time."""
    from backend.database import extract_domain_from_url
    domain = req.domain or extract_domain_from_url(req.lead_url)
    if not domain:
        raise HTTPException(status_code=400, detail="Invalid university URL or domain.")
    
    result = create_or_update_university(
        domain=domain,
        university_name=req.university_name,
        country=req.country or "Unknown",
        lead_url=req.lead_url,
        notes=req.notes or "",
        is_shortlisted=req.is_shortlisted
    )
    return {"success": True, "university": result, "message": f"{req.university_name} added to directory."}

@router.put("/universities/{domain}")
async def update_university_route(domain: str, req: UniversityUpdateRequest):
    """Update details or notes for an existing tracked university in real time."""
    result = create_or_update_university(
        domain=domain,
        university_name=req.university_name or "",
        country=req.country or "Unknown",
        lead_url=req.lead_url or "",
        notes=req.notes if req.notes is not None else "",
        is_shortlisted=req.is_shortlisted
    )
    return {"success": True, "university": result, "message": f"Updated {domain}."}

@router.delete("/universities/{domain}")
async def delete_university_route(domain: str):
    """Remove / untrack a university from bookmarks in real time."""
    deleted = delete_university_bookmark(domain)
    return {"success": deleted, "domain": domain, "message": f"Removed {domain}."}

@router.post("/universities/{domain}/launch-research")
async def launch_university_research_quick_route(domain: str):
    """1-click direct research crawl launch for any university in the directory."""
    from backend.database import get_active_profile
    active_profile = get_active_profile()
    profile_id = active_profile["id"] if active_profile else None
    profile_version = active_profile.get("version", 1) if active_profile else 1

    # Look up university lead_url from tracked universities
    univs = get_tracked_universities(search=domain)
    target_url = f"https://{domain}"
    target_name = domain
    for u in univs:
        if u["domain"].lower() == domain.lower():
            if u.get("lead_url"):
                target_url = u["lead_url"]
            if u.get("university_name"):
                target_name = u["university_name"]
            break

    job_id = enqueue_research_job(
        university_url=target_url,
        profile_id=profile_id,
        university_name=target_name,
        profile_version=profile_version,
        scope="all",
        max_pages=config.crawl_max_pages,
        max_depth=3,
        time_limit_seconds=120,
        job_type="url_research"
    )

    return {
        "success": True,
        "job_id": job_id,
        "university_name": target_name,
        "target_url": target_url,
        "profile_version": profile_version,
        "message": f"Research run started for {target_name}!"
    }

@router.post("/universities/{domain}/shortlist")
async def toggle_university_shortlist_route(domain: str, req: Optional[ShortlistToggleRequest] = None):
    """Toggle shortlist bookmark for a university."""
    is_short = req.is_shortlisted if req else None
    name = req.university_name if req else ""
    country = req.country if req else ""
    lead_url = req.lead_url if req else ""
    new_status = toggle_university_shortlist(
        domain=domain,
        is_shortlisted=is_short,
        university_name=name or "",
        country=country or "",
        lead_url=lead_url or ""
    )
    return {"success": True, "domain": domain, "is_shortlisted": new_status}

@router.post("/universities/{domain}/notes")
async def save_university_notes_route(domain: str, req: NotesUpdateRequest):
    """Save personal notes for a university."""
    success = save_university_notes(
        domain=domain,
        notes=req.notes,
        university_name=req.university_name or "",
        country=req.country or "",
        lead_url=req.lead_url or ""
    )
    return {"success": success, "domain": domain, "notes": req.notes}

# --- Scholarships & Funding ---

@router.get("/scholarships")
async def list_scholarships(
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
):
    """List extracted scholarships with fit scores, evidence, source links, profile version, and rich filtering."""
    return get_scholarships(
        job_id=job_id,
        min_fit_score=min_fit_score,
        funding_category=funding_category,
        eligibility_status=eligibility_status,
        opportunity_status=opportunity_status,
        is_shortlisted=is_shortlisted,
        search=search,
        country=country,
        degree_level=degree_level,
        sort_by=sort_by
    )

@router.post("/scholarships/{scholarship_id}/shortlist")
async def toggle_scholarship_shortlist_route(scholarship_id: int, req: Optional[ShortlistToggleRequest] = None):
    """Toggle shortlist status for a scholarship finding."""
    is_short = req.is_shortlisted if req else None
    new_status = toggle_scholarship_shortlist(scholarship_id, is_short)
    return {"success": True, "scholarship_id": scholarship_id, "is_shortlisted": new_status}

@router.post("/scholarships/{scholarship_id}/notes")
async def save_scholarship_notes_route(scholarship_id: int, req: NotesUpdateRequest):
    """Save personal notes for a scholarship finding."""
    success = save_scholarship_notes(scholarship_id, req.notes)
    return {"success": success, "scholarship_id": scholarship_id, "notes": req.notes}

# --- Professors & Faculty ---

@router.get("/professors")
async def list_professors(
    job_id: Optional[int] = None,
    min_match_score: int = 0,
    recruitment_status: Optional[str] = None,
    has_email: Optional[bool] = None,
    search: Optional[str] = None,
    department: Optional[str] = None,
    is_shortlisted: Optional[bool] = None,
    university: Optional[str] = None,
    sort_by: Optional[str] = None
):
    """List matching faculty with verified academic emails, explainable heuristic scores, recruitment status, and rich filtering."""
    return get_professors(
        job_id=job_id,
        min_match_score=min_match_score,
        recruitment_status=recruitment_status,
        has_email=has_email,
        search=search,
        department=department,
        is_shortlisted=is_shortlisted,
        university=university,
        sort_by=sort_by
    )

@router.post("/professors/{professor_id}/shortlist")
async def toggle_professor_shortlist_route(professor_id: int, req: Optional[ShortlistToggleRequest] = None):
    """Toggle shortlist status for a professor finding."""
    is_short = req.is_shortlisted if req else None
    new_status = toggle_professor_shortlist(professor_id, is_short)
    return {"success": True, "professor_id": professor_id, "is_shortlisted": new_status}

@router.post("/professors/{professor_id}/notes")
async def save_professor_notes_route(professor_id: int, req: NotesUpdateRequest):
    """Save personal notes for a professor finding."""
    success = save_professor_notes(professor_id, req.notes)
    return {"success": success, "professor_id": professor_id, "notes": req.notes}

# --- Unified Shortlist ---

@router.get("/shortlist")
async def get_all_shortlisted_route():
    """Retrieve all bookmarked universities, scholarships, and professors."""
    return get_shortlist_items()

# --- Outreach Settings & Email Drafts Workspace ---

@router.get("/outreach-settings")
async def get_outreach_settings_route():
    """Retrieve user's editable outreach instructions & template settings."""
    return get_outreach_settings()

@router.post("/outreach-settings")
async def update_outreach_settings_route(req: OutreachSettingsUpdateRequest):
    """Updates user's editable outreach instructions & template settings."""
    data = req.model_dump(exclude_unset=True)
    updated = save_outreach_settings(data)
    return {"success": True, "settings": updated, "message": "Outreach instructions saved."}

@router.get("/emails")
async def list_email_drafts(
    status: Optional[str] = None,
    search: Optional[str] = None
):
    """List saved outreach email drafts (sending disabled) with optional status/search filters."""
    return get_email_drafts(status=status, search=search)

@router.get("/emails/{draft_id}")
async def get_email_draft_detail(draft_id: int):
    """Retrieve single email draft with complete evidence citations and audit notes."""
    draft = get_email_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Email draft not found.")
    return draft

@router.post("/emails/generate")
async def generate_new_email_draft(req: EmailDraftGenerateRequest):
    """Generates a personalized outreach email draft recording profile version and evidence citations."""
    profile = get_active_profile() or {}
    
    # Auto-populate recipient data from professor record if provided and missing
    recip_name = req.recipient_name
    recip_email = req.recipient_email
    ctx_title = req.context_title
    ctx_details = req.context_details

    if req.professor_id and (not recip_name or not recip_email or not ctx_title):
        conn = get_db_connection()
        p_row = conn.execute("SELECT * FROM professors WHERE id = ?", (req.professor_id,)).fetchone()
        conn.close()
        if p_row:
            p_data = dict(p_row)
            recip_name = recip_name or p_data.get("name", "Faculty Member")
            recip_email = recip_email or p_data.get("email", "unknown@university.edu")
            ctx_title = ctx_title or p_data.get("research_interests", "Faculty Research")
            ctx_details = ctx_details or f"Affiliation: {p_data.get('department', '')}, {p_data.get('university', '')}. Research Focus: {p_data.get('research_interests', '')}. Recruitment: {p_data.get('recruitment_status', '')}."

    draft = await create_outreach_draft(
        recipient_name=recip_name,
        recipient_email=recip_email,
        recipient_role=req.recipient_role,
        draft_type=req.draft_type,
        context_title=ctx_title,
        context_details=ctx_details,
        profile=profile,
        job_id=req.job_id,
        professor_id=req.professor_id,
        scholarship_id=req.scholarship_id,
        custom_instructions=req.custom_instructions
    )
    return {"success": True, "draft": draft}

@router.post("/emails/generate-batch")
async def generate_batch_email_drafts(req: BatchEmailDraftGenerateRequest):
    """Generates distinct, personalized outreach drafts for a list of selected professors."""
    profile = get_active_profile() or {}
    if not req.professor_ids:
        raise HTTPException(status_code=400, detail="No professor IDs provided for batch generation.")

    generated_drafts = []
    conn = get_db_connection()
    for prof_id in req.professor_ids:
        p_row = conn.execute("SELECT * FROM professors WHERE id = ?", (prof_id,)).fetchone()
        if not p_row:
            continue
        p = dict(p_row)
        draft = await create_outreach_draft(
            recipient_name=p.get("name", "Faculty Member"),
            recipient_email=p.get("email", "unknown@university.edu"),
            recipient_role="Faculty / PI",
            draft_type="Professor Research Inquiry",
            context_title=p.get("research_interests", "Faculty Research Group"),
            context_details=f"University: {p.get('university', '')}. Department: {p.get('department', '')}. Research Areas: {p.get('research_interests', '')}. Recruitment Status: {p.get('recruitment_status', 'Unstated')}. Evidence: {p.get('recruitment_evidence', '')}.",
            profile=profile,
            job_id=req.job_id or p.get("job_id"),
            professor_id=prof_id,
            custom_instructions=req.custom_instructions
        )
        generated_drafts.append(draft)
    conn.close()

    return {
        "success": True,
        "count": len(generated_drafts),
        "drafts": generated_drafts,
        "message": f"Generated {len(generated_drafts)} personalized outreach drafts."
    }

@router.put("/emails/{draft_id}")
async def update_draft(draft_id: int, req: EmailDraftUpdateRequest):
    """Updates an existing email draft subject, body, attachments, and audit status."""
    existing = get_email_draft(draft_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Email draft not found.")

    data = req.model_dump(exclude_unset=True)
    data["id"] = draft_id

    # If user edited text and clear_claims_warning requested, clear warnings
    if req.clear_claims_warning:
        data["unsupported_claims_flag"] = 0
        data["unsupported_claims_notes"] = ""
        if data.get("status") == "needs_review":
            data["status"] = "draft"

    save_email_draft(data)
    updated = get_email_draft(draft_id)
    return {"success": True, "draft": updated, "message": "Draft updated successfully."}

@router.put("/emails/{draft_id}/status")
async def update_draft_status_route(draft_id: int, req: DraftStatusUpdateRequest):
    """Updates the status of an outreach draft, blocking 'verified_ready' if unsupported claims exist."""
    existing = get_email_draft(draft_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Email draft not found.")

    if req.status == "verified_ready" and existing.get("unsupported_claims_flag") and not req.force:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot mark draft as Verified Ready while unsupported claims remain uncorrected: {existing.get('unsupported_claims_notes')}"
        )

    success = update_email_draft_status(draft_id, req.status, req.is_reviewed)
    return {
        "success": success,
        "draft_id": draft_id,
        "status": req.status,
        "is_reviewed": req.is_reviewed
    }

@router.get("/emails/{draft_id}/eml")
async def export_draft_as_eml(draft_id: int):
    """Generates a standard RFC 822 .eml file for opening in desktop email clients."""
    draft = get_email_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Email draft not found.")

    profile = get_active_profile() or {}
    sender_name = profile.get("name", "Applicant")
    sender_email = profile.get("email") or "applicant@scholarscout.local"
    recip_name = draft.get("recipient_name", "Faculty Member")
    recip_email = draft.get("recipient_email", "faculty@university.edu")
    subject = draft.get("subject", "Academic Outreach")
    body = draft.get("body_text", "")
    created_at = draft.get("created_at", datetime.now(timezone.utc).isoformat())

    # Build RFC 822 formatted message
    eml_lines = [
        f"From: {sender_name} <{sender_email}>",
        f"To: {recip_name} <{recip_email}>",
        f"Subject: {subject}",
        f"Date: {created_at}",
        "MIME-Version: 1.0",
        'Content-Type: text/plain; charset="utf-8"',
        f"X-ScholarScout-Draft-ID: {draft_id}",
        f"X-ScholarScout-Profile-Version: {draft.get('profile_version', 1)}",
        "X-ScholarScout-Status: draft-reviewed",
        "",
        body
    ]
    eml_content = "\r\n".join(eml_lines)
    filename = f"scholarscout_outreach_{draft_id}.eml"

    return Response(
        content=eml_content.encode("utf-8"),
        media_type="message/rfc822",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

@router.delete("/emails/{draft_id}")
async def remove_draft(draft_id: int):
    """Deletes an email draft."""
    success = delete_email_draft(draft_id)
    if not success:
        raise HTTPException(status_code=404, detail="Draft not found")
    return {"success": True, "message": "Draft deleted."}

# --- Controlled Email Sending, Accounts, Queues & Approvals ---

from backend.emails.queue_manager import (
    get_sending_settings,
    update_sending_settings,
    toggle_master_sending,
    get_email_accounts,
    get_email_account,
    save_email_account,
    delete_email_account,
    test_account_connection,
    approve_email_draft,
    batch_approve_drafts,
    get_pre_send_preview,
    enqueue_outbound_draft,
    get_outbound_queue,
    process_outbound_queue_item,
    process_outbound_queue_batch,
    reconcile_uncertain_queue_item,
    sync_account_replies,
    get_do_not_contact_list,
    add_do_not_contact,
    remove_do_not_contact,
    get_email_audit_logs
)
from backend.emails.followup_manager import generate_followup_draft

@router.get("/emails/settings")
async def get_email_sending_settings_route():
    """Returns the controlled sending master switch and outbound rate limit settings."""
    return get_sending_settings()

@router.post("/emails/settings/toggle-sending")
async def toggle_email_sending_route(req: MasterSendingToggleRequest):
    """Toggles the global controlled sending master switch."""
    result = toggle_master_sending(enabled=req.enabled, reason=req.reason or "User toggle")
    return {
        "success": True,
        "sending_master_enabled": result["sending_master_enabled"],
        "message": "Controlled sending is now ACTIVE." if result["sending_master_enabled"] else "Controlled sending is now PAUSED (Safety Mode)."
    }

@router.get("/emails/accounts")
async def list_email_accounts_route():
    """Lists connected email accounts with masked credentials."""
    return get_email_accounts()

@router.post("/emails/accounts")
async def create_or_update_email_account_route(req: EmailAccountCreateRequest):
    """Connects or updates an email account (Mock Sandbox, Google OAuth, Microsoft OAuth, SMTP)."""
    acc_id = save_email_account(req.model_dump())
    return {
        "success": True,
        "account_id": acc_id,
        "message": "Email account saved successfully."
    }

@router.delete("/emails/accounts/{account_id}")
async def remove_email_account_route(account_id: int):
    """Removes a connected email account."""
    if account_id == 1:
        raise HTTPException(status_code=400, detail="Default Mock Sandbox account cannot be removed.")
    success = delete_email_account(account_id)
    if not success:
        raise HTTPException(status_code=404, detail="Email account not found.")
    return {"success": True, "message": "Email account disconnected."}

@router.post("/emails/accounts/{account_id}/test")
async def test_email_account_route(account_id: int):
    """Validates connection and credentials for an email account."""
    res = test_account_connection(account_id)
    return res

@router.post("/emails/accounts/{account_id}/sync-replies")
async def sync_email_account_replies_route(account_id: int):
    """
    Synchronizes incoming replies from contacted professors.
    Automatically halts follow-ups when a reply or opt-out is detected.
    """
    res = sync_account_replies(account_id)
    return res

@router.get("/emails/drafts/{draft_id}/pre-send-preview")
async def get_draft_pre_send_preview_route(draft_id: int, account_id: Optional[int] = None):
    """
    Returns exact pre-send preview:
    - Recipient, Subject, Body, Attachments (sizes/types/SHA256)
    - Selected Account
    - Approval verification & exact content version hash
    - Safety checks: Do-Not-Contact suppression, Duplicate-send protection
    """
    preview = get_pre_send_preview(draft_id=draft_id, account_id=account_id)
    if "error" in preview:
        raise HTTPException(status_code=404, detail=preview["error"])
    return preview

@router.post("/emails/drafts/{draft_id}/approve")
async def approve_single_draft_route(draft_id: int):
    """Approves the exact message version of a draft, recording its content hash."""
    success, message = approve_email_draft(draft_id=draft_id)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return {"success": True, "draft_id": draft_id, "message": message}

@router.post("/emails/drafts/batch-approve")
async def batch_approve_drafts_route(req: BatchApproveRequest):
    """Approves a batch of drafts, recording exact version hashes for each."""
    return batch_approve_drafts(req.draft_ids)

@router.post("/emails/drafts/{draft_id}/queue")
async def queue_single_draft_route(draft_id: int, account_id: Optional[int] = None):
    """Enqueues an approved draft into the durable outbound dispatch queue."""
    success, message, queue_id = enqueue_outbound_draft(draft_id=draft_id, account_id=account_id)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return {"success": True, "draft_id": draft_id, "queue_id": queue_id, "message": message}

@router.post("/emails/drafts/batch-queue")
async def batch_queue_drafts_route(req: BatchQueueRequest):
    """Enqueues a batch of approved drafts into the outbound queue."""
    queued_ids = []
    failed = []
    for d_id in req.draft_ids:
        ok, msg, q_id = enqueue_outbound_draft(draft_id=d_id, account_id=req.account_id)
        if ok:
            queued_ids.append({"draft_id": d_id, "queue_id": q_id})
        else:
            failed.append({"draft_id": d_id, "error": msg})
    return {
        "success": len(queued_ids) > 0,
        "queued_count": len(queued_ids),
        "queued": queued_ids,
        "failed_count": len(failed),
        "failed": failed
    }

@router.get("/emails/queue")
async def list_outbound_queue_route(status: Optional[str] = None):
    """Lists items in the durable outbound queue."""
    return get_outbound_queue(status_filter=status)

@router.post("/emails/queue/{queue_id}/process")
async def process_single_queue_item_route(queue_id: int):
    """Dispatches a single queue item through its assigned provider."""
    res = process_outbound_queue_item(queue_id)
    return res

@router.post("/emails/queue/process-batch")
async def process_queue_batch_route(limit: int = 10):
    """Dispatches a batch of pending queued items respecting rate limits."""
    return process_outbound_queue_batch(limit=limit)

@router.post("/emails/queue/{queue_id}/reconcile")
async def reconcile_queue_item_route(queue_id: int):
    """
    Reconciles an uncertain queue item after an ambiguous network timeout.
    Queries the provider index without blindly retrying.
    """
    return reconcile_uncertain_queue_item(queue_id)

@router.delete("/emails/queue/{queue_id}")
async def cancel_queue_item_route(queue_id: int):
    """Cancels a queued message before it is dispatched."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE email_outbound_queue SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (queue_id,))
    cursor.execute("UPDATE email_drafts SET approval_status = 'cancelled' WHERE id = (SELECT draft_id FROM email_outbound_queue WHERE id = ?)", (queue_id,))
    conn.commit()
    conn.close()
    return {"success": True, "message": f"Queue item #{queue_id} cancelled."}

@router.post("/emails/drafts/{draft_id}/generate-followup")
async def generate_draft_followup_route(draft_id: int, req: Optional[FollowupGenerateRequest] = None):
    """
    Generates a respectful follow-up draft linked to prior outreach.
    Strictly halts if a reply or opt-out has been detected.
    """
    days = req.days_elapsed if req else 7
    success, message, followup_id = generate_followup_draft(parent_draft_id=draft_id, days_elapsed=days)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return {
        "success": True,
        "followup_draft_id": followup_id,
        "parent_draft_id": draft_id,
        "message": message
    }

@router.get("/emails/audit-logs")
async def list_email_audit_logs_route(limit: int = 50):
    """Returns recent email audit logs with provider message IDs and timestamps."""
    return get_email_audit_logs(limit=limit)

@router.get("/emails/dnc")
async def list_dnc_route():
    """Lists entries on the Do-Not-Contact suppression list."""
    return get_do_not_contact_list()

@router.post("/emails/dnc")
async def add_dnc_route(req: DoNotContactRequest):
    """Adds an email or domain pattern to the Do-Not-Contact list."""
    ok, msg = add_do_not_contact(pattern=req.pattern, reason=req.reason or "Manual suppression")
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg}

@router.delete("/emails/dnc/{entry_id}")
async def remove_dnc_route(entry_id: int):
    """Removes an entry from the Do-Not-Contact suppression list."""
    success = remove_do_not_contact(entry_id)
    if not success:
        raise HTTPException(status_code=404, detail="Entry not found.")
    return {"success": True, "message": "Suppression entry removed."}

# --- Settings & Search Provider Configuration ---

@router.get("/settings")
async def get_settings():
    """Retrieve public/safe application settings with masked API keys."""
    return config.get_public_settings()

@router.post("/settings")
async def update_settings(req: SettingsUpdateRequest):
    """Updates backend configuration with multi-key and model catalog support."""
    config.update_settings(
        api_base_url=req.api_base_url,
        api_key=req.api_key,
        api_keys=req.api_keys,
        model_name=req.model_name,
        fallback_models=req.fallback_models,
        crawl_max_pages=req.crawl_max_pages,
        llm_timeout=req.llm_timeout,
        llm_max_concurrency=req.llm_max_concurrency,
        job_max_llm_requests=req.job_max_llm_requests,
        job_max_llm_tokens=req.job_max_llm_tokens,
        search_provider=req.search_provider,
        search_api_key=req.search_api_key,
        search_max_queries=req.search_max_queries,
        search_max_results=req.search_max_results,
        discovery_max_universities=req.discovery_max_universities
    )
    return {"success": True, "settings": config.get_public_settings(), "message": "Settings updated successfully."}

@router.get("/settings/nvidia-models")
async def get_nvidia_models_catalog():
    """Returns the full catalog of NVIDIA NIM reasoning models."""
    return {
        "catalog": NVIDIA_MODELS_CATALOG,
        "active_model": config.llm_model,
        "fallback_models": config.llm_fallback_models,
        "total_models": len(NVIDIA_MODELS_CATALOG)
    }

@router.post("/settings/test-all-keys")
async def test_all_api_keys_endpoint():
    """Tests all configured NVIDIA API keys individually and returns health diagnostics."""
    result = await ai_client.test_all_keys()
    return result

@router.post("/settings/test-connection")
async def test_nemotron_endpoint():
    """Tests connection to configured AI provider API with detailed diagnostics."""
    result = await ai_client.test_connection()
    return result

@router.post("/settings/test-search")
async def test_search_provider_endpoint():
    """Tests configured search provider API credentials with a lightweight query."""
    provider = get_search_provider()
    result = await provider.validate_credentials()
    return result

@router.get("/settings/search-instructions")
async def get_search_provider_setup_instructions():
    """Returns documentation on configuring supported search APIs."""
    return {
        "supported_providers": [
            {
                "id": "tavily",
                "name": "Tavily Search API (Recommended)",
                "description": "AI-optimized search API designed for autonomous research agents and web fact-finding.",
                "signup_url": "https://tavily.com",
                "env_var": "TAVILY_API_KEY",
                "free_tier": "1,000 free search credits / month",
                "instructions": "1. Create a free account at https://tavily.com\n2. Copy your API Key\n3. Select 'Tavily' in ScholarScout Settings and paste your key."
            },
            {
                "id": "serpapi",
                "name": "SerpAPI (Google Search)",
                "description": "Real-time Google search results API with organic SERP ranking and site filtering.",
                "signup_url": "https://serpapi.com",
                "env_var": "SERPAPI_API_KEY",
                "free_tier": "100 free searches / month",
                "instructions": "1. Register at https://serpapi.com\n2. Retrieve your private API Key\n3. Select 'SerpAPI' in ScholarScout Settings and save."
            },
            {
                "id": "brave",
                "name": "Brave Search API",
                "description": "Independent, privacy-preserving web search index with fast JSON responses.",
                "signup_url": "https://brave.com/search/api/",
                "env_var": "BRAVE_SEARCH_API_KEY",
                "free_tier": "2,000 free queries / month",
                "instructions": "1. Sign up at https://brave.com/search/api/\n2. Generate a Web Search Subscription Token\n3. Select 'Brave' in ScholarScout Settings and paste the token."
            }
        ],
        "no_provider_fallback": "If you do not configure a search API, ScholarScout's University URL mode remains fully usable with single URL entry or batch URL-list import. Discovery does not use unauthorized search scraping workarounds."
    }

@router.get("/settings/setup-instructions")
async def get_provider_setup_instructions():
    """Returns step-by-step setup instructions for NVIDIA NIM and OpenAI-compatible endpoints."""
    err = MissingCredentialsError()
    return err.details["setup_instructions"]

# --- Exports & Redacted Diagnostics ---

@router.get("/export/{entity}")
async def export_data_endpoint(
    entity: str,
    format: str = "csv",
    job_id: Optional[int] = None,
    shortlisted_only: bool = False
):
    """
    Exports data (scholarships, professors, sources, outreach) in CSV (with formula injection defense) or JSON.
    """
    format_lower = format.lower()
    now_stamp = datetime.now().strftime("%Y%m%d")
    if entity == "scholarships":
        if format_lower == "json":
            content = export_scholarships_json(job_id=job_id, shortlisted_only=shortlisted_only)
            return Response(content=content, media_type="application/json", headers={"Content-Disposition": f"attachment; filename=scholarscout_scholarships_{now_stamp}.json"})
        else:
            content = export_scholarships_csv(job_id=job_id, shortlisted_only=shortlisted_only)
            return Response(content=content, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=scholarscout_scholarships_{now_stamp}.csv"})
    elif entity == "professors":
        if format_lower == "json":
            content = export_professors_json(job_id=job_id, shortlisted_only=shortlisted_only)
            return Response(content=content, media_type="application/json", headers={"Content-Disposition": f"attachment; filename=scholarscout_professors_{now_stamp}.json"})
        else:
            content = export_professors_csv(job_id=job_id, shortlisted_only=shortlisted_only)
            return Response(content=content, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=scholarscout_professors_{now_stamp}.csv"})
    elif entity == "sources":
        if format_lower == "json":
            content = export_sources_json(job_id=job_id)
            return Response(content=content, media_type="application/json", headers={"Content-Disposition": f"attachment; filename=scholarscout_sources_{now_stamp}.json"})
        else:
            content = export_sources_csv(job_id=job_id)
            return Response(content=content, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=scholarscout_sources_{now_stamp}.csv"})
    elif entity in ("outreach", "drafts", "queue"):
        if format_lower == "json":
            content = export_outreach_json()
            return Response(content=content, media_type="application/json", headers={"Content-Disposition": f"attachment; filename=scholarscout_outreach_{now_stamp}.json"})
        else:
            content = export_outreach_csv()
            return Response(content=content, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=scholarscout_outreach_{now_stamp}.csv"})
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported export entity '{entity}'. Choose from: scholarships, professors, sources, outreach.")

@router.get("/diagnostics/export")
async def get_redacted_diagnostics_bundle():
    """Returns a comprehensive diagnostic bundle with all API keys and credentials strictly redacted."""
    return export_redacted_diagnostics()

# --- Database Backup & Restore ---

class DatabaseBackupRequest(BaseModel):
    label: Optional[str] = None

class DatabaseRestoreRequest(BaseModel):
    filename: str

@router.get("/database/backups")
async def list_backups_endpoint():
    """Lists available database backups."""
    return {"backups": list_database_backups()}

@router.post("/database/backup")
async def create_backup_endpoint(req: DatabaseBackupRequest):
    """Creates a full transactional database backup."""
    try:
        res = create_database_backup(label=req.label)
        return res
    except Exception as e:
        logger.error(f"[Backup API] Failed: {e}")
        raise HTTPException(status_code=500, detail=f"Backup failed: {e}")

@router.post("/database/restore")
async def restore_backup_endpoint(req: DatabaseRestoreRequest):
    """Restores database from a selected backup with automatic safety snapshot."""
    try:
        res = restore_database_backup(backup_filename=req.filename)
        return res
    except Exception as e:
        logger.error(f"[Restore API] Failed: {e}")
        raise HTTPException(status_code=400, detail=f"Restore failed: {e}")

@router.delete("/database/backups/{filename}")
async def delete_backup_endpoint(filename: str):
    """Deletes a backup file."""
    success = delete_database_backup(backup_filename=filename)
    if not success:
        raise HTTPException(status_code=404, detail="Backup file not found.")
    return {"success": True, "message": f"Backup '{filename}' deleted."}

# --- Scheduled Rechecks for Shortlisted Items ---

class ScheduledRecheckCreateRequest(BaseModel):
    target_type: str # scholarship, professor, all_shortlisted
    target_id: Optional[int] = None
    target_title: str
    target_url: Optional[str] = ""
    frequency: str = "weekly" # daily, weekly, monthly

class ScheduledRecheckUpdateRequest(BaseModel):
    is_enabled: Optional[bool] = None
    frequency: Optional[str] = None

@router.get("/rechecks")
async def get_rechecks_endpoint():
    """Lists scheduled rechecks and automatically flags stale items (>30 days)."""
    mark_stale_records(stale_days=30)
    return {
        "rechecks": get_scheduled_rechecks(),
        "local_schedule_notice": "Local scheduled rechecks only run while the application is active. Missed runs are caught up in a single controlled execution on startup."
    }

@router.post("/rechecks")
async def create_recheck_endpoint(req: ScheduledRecheckCreateRequest):
    """Registers a new scheduled recheck."""
    recheck_id = create_scheduled_recheck(
        target_type=req.target_type,
        target_id=req.target_id,
        target_title=req.target_title,
        target_url=req.target_url or "",
        frequency=req.frequency
    )
    return {"success": True, "recheck_id": recheck_id, "message": "Scheduled recheck registered."}

@router.post("/rechecks/schedule-all-shortlisted")
async def schedule_all_shortlisted_endpoint(frequency: str = "weekly"):
    """Schedules recurring rechecks for all bookmarked shortlisted scholarships and faculty leads."""
    shortlist_data = get_shortlist_items()
    schol_list = shortlist_data.get("scholarships", [])
    prof_list = shortlist_data.get("professors", [])
    
    created_count = 0
    existing = get_scheduled_rechecks()
    existing_keys = {(r.get("target_type"), r.get("target_id")) for r in existing}

    for s in schol_list:
        key = ("scholarship", s["id"])
        if key not in existing_keys:
            create_scheduled_recheck(
                target_type="scholarship",
                target_id=s["id"],
                target_title=s.get("scholarship_name") or s.get("title") or f"Scholarship #{s['id']}",
                target_url=s.get("official_url") or s.get("source_url") or "",
                frequency=frequency
            )
            existing_keys.add(key)
            created_count += 1

    for p in prof_list:
        key = ("professor", p["id"])
        if key not in existing_keys:
            create_scheduled_recheck(
                target_type="professor",
                target_id=p["id"],
                target_title=p.get("name") or f"Professor #{p['id']}",
                target_url=p.get("homepage_url") or p.get("profile_url") or "",
                frequency=frequency
            )
            existing_keys.add(key)
            created_count += 1

    return {
        "success": True,
        "created_count": created_count,
        "message": f"Scheduled rechecks registered for {created_count} shortlisted item(s)."
    }

@router.put("/rechecks/{recheck_id}")
@router.patch("/rechecks/{recheck_id}")
async def update_recheck_endpoint(recheck_id: int, req: ScheduledRecheckUpdateRequest):
    """Updates a scheduled recheck."""
    success = update_scheduled_recheck(
        recheck_id=recheck_id,
        is_enabled=req.is_enabled,
        frequency=req.frequency
    )
    if not success:
        raise HTTPException(status_code=404, detail="Scheduled recheck not found.")
    return {"success": True, "message": "Scheduled recheck updated."}

@router.delete("/rechecks/{recheck_id}")
async def delete_recheck_endpoint(recheck_id: int):
    """Deletes a scheduled recheck."""
    success = delete_scheduled_recheck(recheck_id=recheck_id)
    if not success:
        raise HTTPException(status_code=404, detail="Scheduled recheck not found.")
    return {"success": True, "message": "Scheduled recheck removed."}

@router.post("/rechecks/run-due")
async def run_due_rechecks_endpoint():
    """Runs any due or overdue rechecks without launching uncontrolled duplicates."""
    executed = await check_and_run_due_rechecks()
    return {"success": True, "executed_count": len(executed), "executed": executed, "message": f"Processed {len(executed)} due recheck(s)."}

# --- Evidence History & Audit Trail ---

@router.get("/evidence-history/{entity_type}/{entity_id}")
async def get_entity_evidence_history_endpoint(entity_type: str, entity_id: int):
    """Retrieves change history and evidence diffs for a scholarship or professor."""
    history = get_evidence_history(entity_type=entity_type.lower(), entity_id=entity_id)
    return history

@router.get("/evidence-history")
async def get_recent_evidence_changes_endpoint(
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    limit: int = 50
):
    """Retrieves recent changes across all scholarships and faculty leads, or for a specific item if filtered."""
    if entity_type and entity_id is not None:
        history = get_evidence_history(entity_type=entity_type.lower(), entity_id=entity_id)
        return history
    changes = get_recent_evidence_changes(limit=limit)
    return changes

# ==============================================================================
# AUTONOMOUS SCHOLARSHIP & FACULTY GATHERING AGENT ENDPOINTS
# ==============================================================================

@router.post("/agent/start-gathering")
async def start_gathering_agent_endpoint(req: AgentRunConfig, background_tasks: BackgroundTasks):
    """
    Launches the Autonomous Scholarship & Faculty Outreach Data Gathering Agent.
    Runs asynchronously in the background.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    degrees_str = ", ".join(req.degree_levels)
    uni_display = f"Scholarship Agent: {req.subject} ({degrees_str})"

    cursor.execute("""
    INSERT INTO research_jobs (
        university_url, university_name, status, current_step,
        progress_pct, max_pages, max_depth, time_budget_sec,
        scope, job_type, discovery_queries, created_at
    ) VALUES (?, ?, 'queued', 'Agent Initializing', 0, ?, 3, ?, 'all', 'agent_gathering_job', ?, CURRENT_TIMESTAMP)
    """, (
        "https://scholarscout.agent.internal",
        uni_display,
        req.max_universities,
        req.time_limit_sec,
        json.dumps(req.model_dump())
    ))
    job_id = cursor.lastrowid
    conn.commit()
    conn.close()

    logger.info(f"[API] Enqueued Autonomous Gathering Agent Job #{job_id} for '{req.subject}' ({degrees_str})")
    return {
        "success": True,
        "job_id": job_id,
        "message": f"Autonomous data gathering initiated for {req.subject} ({degrees_str}).",
        "status_url": f"/api/agent/status/{job_id}",
        "config": req.model_dump()
    }

@router.get("/agent/status/{job_id}")
async def get_agent_status_endpoint(job_id: int):
    """
    Returns live progress, current step, university being crawled,
    scholarships/professors counts, and terminal logs for the gathering agent.
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Agent Job #{job_id} not found.")

    scholarships = get_scholarships(job_id=job_id)
    professors = get_professors(job_id=job_id)
    pages = get_crawled_pages(job_id=job_id, limit=100)

    # Calculate unique universities discovered & cataloged
    disc_unis = job.get("discovered_institutions") or []
    s_unis = set(s.get("university") for s in scholarships if s.get("university") and s.get("university") != "Unknown")
    p_unis = set(p.get("university") for p in professors if p.get("university") and p.get("university") != "Unknown")
    unis_count = max(len(disc_unis), len(s_unis | p_unis))

    # Parse logs
    raw_logs = job.get("logs", [])
    if isinstance(raw_logs, str):
        try:
            logs = json.loads(raw_logs)
        except Exception:
            logs = [{"message": raw_logs, "level": "info", "time": ""}]
    else:
        logs = raw_logs or []

    return {
        "job_id": job_id,
        "status": job.get("status", "unknown"),
        "current_step": job.get("current_step", "Processing..."),
        "progress_pct": job.get("progress_pct", 0),
        "university_name": job.get("university_name") or "Autonomous Scholarship Agent",
        "universities_count": unis_count,
        "scholarships_count": len(scholarships),
        "professors_count": len(professors),
        "pages_crawled": job.get("pages_crawled", len(pages)),
        "llm_requests_count": job.get("llm_requests_count", 0),
        "llm_total_tokens": job.get("llm_total_tokens", 0),
        "logs": logs,
        "stop_reason": job.get("stop_reason"),
        "elapsed_seconds": job.get("elapsed_seconds", 0),
        "error_message": job.get("error_message"),
        "created_at": job.get("created_at"),
        "started_at": job.get("started_at"),
        "completed_at": job.get("completed_at")
    }

@router.post("/agent/pause/{job_id}")
async def pause_gathering_agent_endpoint(job_id: int):
    """Pauses the running gathering agent and saves an execution checkpoint."""
    paused = pause_job(job_id)
    if not paused:
        raise HTTPException(status_code=400, detail="Could not pause job (not running or does not exist).")
    return {"success": True, "message": f"Agent Job #{job_id} paused. Checkpoint saved."}

@router.post("/agent/resume/{job_id}")
async def resume_gathering_agent_endpoint(job_id: int):
    """Resumes the paused gathering agent from its saved checkpoint."""
    resumed = resume_job(job_id)
    if not resumed:
        raise HTTPException(status_code=400, detail="Could not resume job (not paused or does not exist).")
    return {"success": True, "message": f"Agent Job #{job_id} resumed from checkpoint."}

@router.post("/agent/stop/{job_id}")
async def stop_gathering_agent_endpoint(job_id: int):
    """Stops and cancels the running gathering agent."""
    cancelled = cancel_job(job_id)
    if not cancelled:
        raise HTTPException(status_code=400, detail="Could not stop job.")
    return {"success": True, "message": f"Agent Job #{job_id} stopped."}

@router.get("/agent/export/{job_id}/excel")
async def export_agent_excel_endpoint(job_id: int):
    """Downloads formatted multi-sheet Excel (.xlsx) file for the gathering run."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job #{job_id} not found.")

    excel_bytes = export_gathering_pipeline_excel(job_id=job_id)
    filename = f"scholarscout_agent_results_job_{job_id}.xlsx"
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

@router.get("/agent/export/{job_id}/csv")
async def export_agent_csv_endpoint(job_id: int):
    """Downloads clean CSV file for the gathering run."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job #{job_id} not found.")

    csv_text = export_gathering_pipeline_csv(job_id=job_id)
    filename = f"scholarscout_agent_results_job_{job_id}.csv"
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

