"""
Scholarship & Faculty Outreach Data Gathering Agent.
Autonomous pipeline orchestrator for:
1. Web Search & Global University Discovery for scholarships matching selected degree levels.
2. Official University Page Crawling & Scholarship Data Capture (Coverage, Criteria, Deadlines, Handler Contacts).
3. Faculty Discovery & Contact Extraction (Public Email, Phone, Office, Lab URLs).
4. Academic Relevance Ranking & Top-N Selection per institution.
5. Persistent Checkpointing, Pause / Resume / Stop controls, and Auto-Export generation.
"""

import asyncio
import time
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse
from pydantic import BaseModel, Field

from backend.config import config
from backend.logging_utils import logger
from backend.database import (
    get_db_connection,
    get_job,
    update_job_status,
    append_job_log,
    save_job_checkpoint,
    get_job_checkpoint,
    insert_scholarships,
    insert_professors,
    record_crawled_page,
    get_scholarships,
    get_professors
)
from backend.discovery.search_providers import get_search_provider
from backend.discovery.engine import DiscoveryEngine
from backend.discovery.crawler import UniversityCrawler
from backend.funding.extractor import extract_funding_opportunities
from backend.professors.matcher import match_professors
from backend.llm.budget import job_budget_tracker

class AgentRunConfig(BaseModel):
    """User input configuration for the Autonomous Gathering Agent."""
    degree_levels: List[str] = Field(default_factory=lambda: ["PhD"], description="Selected degree levels (BS, MS, MPhil, PhD)")
    subject: str = Field(..., min_length=2, description="Target field of study or research focus")
    preferred_countries: Optional[List[str]] = Field(default_factory=list, description="Optional target countries")
    max_universities: int = Field(default=5, ge=1, le=25, description="Max institutions to discover and crawl")
    max_faculty_per_univ: int = Field(default=5, ge=1, le=15, description="Max ranked faculty members per university")
    max_pages_per_univ: int = Field(default=10, ge=3, le=25, description="Page crawling depth per university")
    time_limit_sec: int = Field(default=300, ge=30, le=900, description="Total run time budget")

class GatheringAgentOrchestrator:
    """Orchestrates the end-to-end autonomous data gathering pipeline."""

    async def execute_agent_pipeline(self, job_id: int, run_config: AgentRunConfig):
        """Main execution entrypoint for the background gathering agent."""
        start_time = time.time()
        logger.info(f"[Gathering Agent] Starting autonomous pipeline for Job #{job_id} ({run_config.subject}, {run_config.degree_levels})")

        def log_cb(msg: str, lvl: str = "info"):
            append_job_log(job_id, msg, lvl)

        # Update initial status
        degrees_str = ", ".join(run_config.degree_levels)
        countries_str = ", ".join(run_config.preferred_countries) if run_config.preferred_countries else "Worldwide"

        update_job_status(
            job_id=job_id,
            status="running",
            current_step=f"Initializing Agent for {run_config.subject} ({degrees_str} in {countries_str})",
            progress_pct=5,
            university_name="Autonomous Scholarship Agent"
        )
        log_cb(f"🚀 Initialized Scholarship Agent: Field='{run_config.subject}', Degrees='{degrees_str}', Target='{countries_str}'")

        # Step 1: Prepare synthetic profile for the discovery engine & matcher
        agent_profile = {
            "name": "Scholarship Candidate",
            "target_degree": run_config.degree_levels[0] if run_config.degree_levels else "PhD",
            "target_field": run_config.subject,
            "research_interests": run_config.subject,
            "specific_interests": run_config.subject,
            "preferred_countries": run_config.preferred_countries or [],
            "excluded_countries": [],
            "funding_needs": ["Full tuition", "Living stipend", "Research assistantship"],
            "version": 1
        }

        # Step 2: Global Search & Institutional Discovery
        provider = get_search_provider()
        discovered_unis = []
        coverage_report = {}

        if provider.is_configured():
            log_cb(f"🔍 Searching official university sources via {provider.display_name}...")
            update_job_status(job_id=job_id, current_step=f"Searching scholarships via {provider.display_name}", progress_pct=15)

            engine = DiscoveryEngine(
                search_provider=provider,
                max_queries=5,
                max_results_per_query=10,
                max_universities=run_config.max_universities
            )
            disc_res = await engine.discover_institutions(agent_profile)
            if disc_res.get("success"):
                discovered_unis = disc_res.get("discovered_institutions", [])
                coverage_report = disc_res.get("coverage_report", {})
                log_cb(f"✅ Found {len(discovered_unis)} university candidate portals worldwide.")
            else:
                log_cb(f"Search provider note: {disc_res.get('error')}. Using curated global academic institutions.", "warning")

        # Fallback to curated global university research seeds if search returned few results
        if len(discovered_unis) < run_config.max_universities:
            from backend.discovery.global_directory import COUNTRY_NORMALIZATION_MAP
            curated_seeds = [
                {"institution_name": "Carnegie Mellon University", "root_domain": "cs.cmu.edu", "lead_url": "https://cs.cmu.edu", "country": "United States"},
                {"institution_name": "University of Oxford", "root_domain": "ox.ac.uk", "lead_url": "https://www.cs.ox.ac.uk", "country": "United Kingdom"},
                {"institution_name": "Technical University of Munich (TUM)", "root_domain": "tum.de", "lead_url": "https://www.in.tum.de", "country": "Germany"},
                {"institution_name": "ETH Zurich", "root_domain": "ethz.ch", "lead_url": "https://inf.ethz.ch", "country": "Switzerland"},
                {"institution_name": "National University of Singapore (NUS)", "root_domain": "comp.nus.edu.sg", "lead_url": "https://www.comp.nus.edu.sg", "country": "Singapore"},
                {"institution_name": "University of Toronto", "root_domain": "cs.toronto.edu", "lead_url": "https://web.cs.toronto.edu", "country": "Canada"},
                {"institution_name": "EPFL", "root_domain": "epfl.ch", "lead_url": "https://ic.epfl.ch", "country": "Switzerland"},
                {"institution_name": "University of Cambridge", "root_domain": "cst.cam.ac.uk", "lead_url": "https://www.cst.cam.ac.uk", "country": "United Kingdom"}
            ]
            # Filter seeds by preferred countries if specified
            if run_config.preferred_countries:
                norm_prefs = {COUNTRY_NORMALIZATION_MAP.get(c.lower().strip(), c.lower().strip()) for c in run_config.preferred_countries}
                curated_seeds = [s for s in curated_seeds if s["country"].lower() in norm_prefs or any(p in s["country"].lower() for p in norm_prefs)] or curated_seeds

            existing_domains = {u.get("root_domain") for u in discovered_unis}
            for seed in curated_seeds:
                if seed["root_domain"] not in existing_domains and len(discovered_unis) < run_config.max_universities:
                    discovered_unis.append(seed)
                    existing_domains.add(seed["root_domain"])

        update_job_status(
            job_id=job_id,
            current_step=f"Discovered {len(discovered_unis)} universities. Starting official crawling...",
            progress_pct=25,
            discovered_institutions=discovered_unis
        )

        all_scholarships: List[Dict[str, Any]] = []
        all_professors: List[Dict[str, Any]] = []
        researched_institutions: List[Dict[str, Any]] = []

        # Check existing checkpoint
        start_idx = 0
        existing_chk = get_job_checkpoint(job_id)
        if existing_chk and "current_institution_idx" in existing_chk:
            start_idx = existing_chk["current_institution_idx"]
            log_cb(f"Resuming gathering run from institution #{start_idx+1}/{len(discovered_unis)}.")

        # Step 3: Crawl Each University for Scholarships and Faculty
        for idx in range(start_idx, len(discovered_unis)):
            uni = discovered_unis[idx]
            uni_name = uni.get("institution_name", "Academic Institution")
            lead_url = uni.get("lead_url") or f"https://{uni.get('root_domain')}"
            uni_country = uni.get("country", "Unknown")

            # Check for cancellation or pause
            fresh_job = get_job(job_id)
            if fresh_job and fresh_job.get("status") in ("cancelled", "paused"):
                chk_data = {
                    "current_institution_idx": idx,
                    "researched_institutions": researched_institutions,
                    "elapsed_seconds": time.time() - start_time
                }
                save_job_checkpoint(job_id, chk_data, time.time() - start_time)
                log_cb(f"Gathering run {fresh_job['status']} by user. Checkpoint saved.", "warning")
                return

            if (time.time() - start_time) > run_config.time_limit_sec:
                log_cb(f"Reached time limit ({run_config.time_limit_sec}s). Finalizing captured records.", "warning")
                break

            log_cb(f"[{idx+1}/{len(discovered_unis)}] Crawling official portal: {uni_name} ({lead_url})")
            update_job_status(
                job_id=job_id,
                current_step=f"Analyzing {uni_name} for scholarships & {run_config.subject} faculty",
                university_name=uni_name,
                progress_pct=25 + int(((idx) / max(len(discovered_unis), 1)) * 60)
            )

            uni_scholarships = 0
            uni_professors = 0
            uni_pages = 0

            try:
                crawler = UniversityCrawler(
                    seed_url=lead_url,
                    scope="all",
                    max_pages=run_config.max_pages_per_univ,
                    max_depth=3,
                    time_limit_seconds=45,
                    log_callback=log_cb
                )

                async for page_info in crawler.crawl():
                    fresh_inner = get_job(job_id)
                    if fresh_inner and fresh_inner.get("status") in ("cancelled", "paused"):
                        return

                    uni_pages += 1
                    page_url = page_info["url"]
                    page_title = page_info["title"]
                    page_type = page_info["page_type"]
                    text_content = page_info.get("text_content", "")
                    emails = page_info.get("emails", [])

                    record_crawled_page(
                        job_id=job_id,
                        url=page_url,
                        normalized_url=page_info.get("normalized_url"),
                        page_title=page_title,
                        page_type=page_type,
                        page_status=page_info.get("page_status", "success"),
                        status_code=page_info.get("status_code", 200),
                        status_reason=page_info.get("status_reason", ""),
                        selection_reason=page_info.get("selection_reason", ""),
                        retrieval_method=page_info.get("retrieval_method", "http"),
                        content_hash=page_info.get("content_hash", ""),
                        byte_size=page_info.get("byte_size", 0),
                        depth=page_info.get("depth", 0),
                        is_external=page_info.get("is_external", False),
                        external_domain_type=page_info.get("external_domain_type", "official_university")
                    )

                    if text_content:
                        # Extract scholarships / funding
                        if page_type in ("scholarships_funding", "funded_positions", "admissions_eligibility", "general") or any(k in page_url.lower() for k in ["funding", "scholarship", "financial", "aid", "fellowship", "assistantship", "bursary", "cost"]):
                            found_f = await extract_funding_opportunities(page_url, text_content, agent_profile, job_id=job_id)
                            if found_f:
                                for f in found_f:
                                    f["university"] = uni_name
                                    f["country"] = uni_country
                                    f["degree_level"] = ", ".join(run_config.degree_levels)
                                inserted_f = insert_scholarships(job_id, found_f, profile_version=1)
                                all_scholarships.extend(found_f)
                                uni_scholarships += inserted_f
                                log_cb(f"Discovered {inserted_f} scholarship awards at {uni_name}", "success")

                        # Extract faculty members & research interests
                        if page_type in ("faculty_directories", "research_labs", "departments", "funded_positions", "general") or any(k in page_url.lower() for k in ["faculty", "people", "directory", "professor", "staff", "research", "lab", "group"]):
                            found_p = await match_professors(
                                page_url=page_url,
                                text_content=text_content,
                                emails_found=emails,
                                profile=agent_profile,
                                job_id=job_id,
                                university_name=uni_name
                            )
                            if found_p:
                                # Rank and filter top N per university
                                ranked_p = sorted(found_p, key=lambda x: int(x.get("match_score", 0)), reverse=True)[:run_config.max_faculty_per_univ]
                                for p in ranked_p:
                                    p["university"] = uni_name
                                inserted_p = insert_professors(job_id, ranked_p, profile_version=1)
                                all_professors.extend(ranked_p)
                                uni_professors += inserted_p
                                log_cb(f"Found {inserted_p} matching faculty in {run_config.subject} at {uni_name}", "success")

                researched_institutions.append({
                    "institution_name": uni_name,
                    "domain": uni.get("root_domain"),
                    "lead_url": lead_url,
                    "country": uni_country,
                    "pages_crawled": uni_pages,
                    "scholarships_found": uni_scholarships,
                    "professors_found": uni_professors
                })

            except Exception as e:
                log_cb(f"Warning crawling {uni_name}: {e}", "warning")

            # Save checkpoint after each university
            chk_data = {
                "current_institution_idx": idx + 1,
                "researched_institutions": researched_institutions,
                "elapsed_seconds": time.time() - start_time
            }
            save_job_checkpoint(job_id, chk_data, time.time() - start_time)

            # Update live stats
            usage = job_budget_tracker.get_job_usage(job_id)
            prog = min(25 + int(((idx + 1) / max(len(discovered_unis), 1)) * 65), 90)
            update_job_status(
                job_id=job_id,
                status="running",
                current_step=f"Researched {idx+1}/{len(discovered_unis)} universities · {len(all_scholarships)} scholarships · {len(all_professors)} faculty",
                progress_pct=prog,
                scholarships_count=len(all_scholarships),
                professors_count=len(all_professors),
                llm_requests_count=usage["requests"],
                llm_prompt_tokens=usage["prompt_tokens"],
                llm_completion_tokens=usage["completion_tokens"],
                llm_total_tokens=usage["total_tokens"],
                elapsed_seconds=round(time.time() - start_time, 2)
            )

        # Step 4: Finalize and Complete Run
        final_elapsed = round(time.time() - start_time, 2)
        final_usage = job_budget_tracker.get_job_usage(job_id)

        update_job_status(
            job_id=job_id,
            status="completed",
            current_step=f"Gathering Complete! Collected {len(all_scholarships)} scholarships and {len(all_professors)} ranked professors.",
            progress_pct=100,
            stop_reason="Completed end-to-end data gathering run",
            scholarships_count=len(all_scholarships),
            professors_count=len(all_professors),
            llm_requests_count=final_usage["requests"],
            llm_total_tokens=final_usage["total_tokens"],
            elapsed_seconds=final_elapsed
        )

        log_cb(f"🎉 Agent run successfully completed in {final_elapsed}s! Ready for Excel/CSV download.", "success")
        logger.info(f"[Gathering Agent] Job #{job_id} completed: {len(all_scholarships)} awards, {len(all_professors)} faculty in {final_elapsed}s.")

gathering_agent = GatheringAgentOrchestrator()
