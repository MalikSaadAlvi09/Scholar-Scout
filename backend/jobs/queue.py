"""
Persistent Research Job Queue & Background Worker.
Processes university research runs, autonomous discovery jobs, and scheduled rechecks asynchronously from SQLite.
Supports:
1. Lifecycle states: queued, running, paused, completed, partially_completed, failed, cancelled.
2. Resuming from checkpoints saved after each completed page/institution.
3. Budgets enforcement: page budget, request budget, time budget, and token budget.
4. Transparent stop reasons explaining why jobs concluded or paused.
5. Bounded retries for transient network/LLM failures.
"""

import time
import asyncio
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse
from backend.config import config
from backend.database import (
    get_next_queued_job,
    update_job_status,
    append_job_log,
    get_job,
    get_profile_by_id,
    get_active_profile,
    insert_scholarships,
    insert_professors,
    record_crawled_page,
    insert_external_leads,
    update_job_coverage,
    save_job_checkpoint,
    get_job_checkpoint
)
from backend.discovery.crawler import UniversityCrawler
from backend.discovery.search_providers import get_search_provider
from backend.discovery.engine import DiscoveryEngine
from backend.funding.extractor import extract_funding_opportunities
from backend.professors.matcher import match_professors
from backend.emails.generator import create_outreach_draft
from backend.llm.budget import job_budget_tracker
from backend.logging_utils import logger

class ResearchJobWorker:
    def __init__(self):
        self._is_running = False
        self._current_task: Optional[asyncio.Task] = None

    def start(self):
        """Starts the persistent background worker loop."""
        if not self._is_running:
            self._is_running = True
            self._current_task = asyncio.create_task(self._worker_loop())
            logger.info("[Job Queue] Persistent research job worker started.")

    def stop(self):
        """Stops the worker gracefully."""
        self._is_running = False
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()
            logger.info("[Job Queue] Persistent worker loop cancelled.")

    async def _worker_loop(self):
        """Continuously checks for queued research jobs in SQLite."""
        while self._is_running:
            try:
                job = get_next_queued_job()
                if job:
                    if job.get("job_type") == "agent_gathering_job":
                        from backend.agents.gathering_agent import gathering_agent, AgentRunConfig
                        cfg_data = {}
                        if job.get("discovery_queries"):
                            try:
                                import json
                                cfg_data = json.loads(job["discovery_queries"]) if isinstance(job["discovery_queries"], str) else job["discovery_queries"]
                            except Exception:
                                cfg_data = {}
                        run_cfg = AgentRunConfig(
                            degree_levels=cfg_data.get("degree_levels", ["PhD"]),
                            subject=cfg_data.get("subject", "Computer Science"),
                            preferred_countries=cfg_data.get("preferred_countries", []),
                            max_universities=int(cfg_data.get("max_universities") or job.get("max_pages") or 5),
                            max_faculty_per_univ=int(cfg_data.get("max_faculty_per_univ", 5)),
                            max_pages_per_univ=int(cfg_data.get("max_pages_per_univ", 10)),
                            time_limit_sec=int(job.get("time_budget_sec") or 300)
                        )
                        await gathering_agent.execute_agent_pipeline(job["id"], run_cfg)
                    elif job.get("job_type") == "discovery_job":
                        await self._process_discovery_job(job)
                    else:
                        await self._process_url_research_job(job)
                else:
                    await asyncio.sleep(2.0)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Job Queue] Unexpected error in worker loop: {e}")
                await asyncio.sleep(3.0)

    async def _process_url_research_job(self, job: Dict[str, Any]):
        """Executes a single university research job pipeline from a known URL with budgets and checkpoints."""
        job_id = job["id"]
        university_url = job["university_url"]
        profile_id = job.get("profile_id")
        start_job_time = time.time()
        
        # Load associated student profile
        profile = None
        if profile_id:
            profile = get_profile_by_id(profile_id)
        if not profile:
            profile = get_active_profile() or {}

        # Parse university name from domain if not provided
        parsed_url = urlparse(university_url)
        domain_name = parsed_url.netloc.replace("www.", "")
        guessed_name = domain_name.split(".")[0].title() + " University"
        uni_name = job.get("university_name") or guessed_name

        # Enforce configurable budgets
        scope = job.get("scope", "all")
        page_budget = int(job.get("page_budget") or job.get("max_pages") or config.crawl_max_pages)
        time_budget = int(job.get("time_budget_sec") or job.get("time_limit_seconds") or 120)
        token_budget = int(job.get("token_budget") or 100000)
        request_budget = int(job.get("request_budget") or 50)
        max_depth = int(job.get("max_depth", 3))

        # Mark as running
        update_job_status(
            job_id=job_id,
            status="running",
            current_step="Connecting to academic portal",
            progress_pct=10,
            university_name=uni_name,
            page_budget=page_budget,
            time_budget_sec=time_budget,
            token_budget=token_budget,
            request_budget=request_budget
        )
        append_job_log(job_id, f"Starting research run for {uni_name} ({university_url}) · Budgets: {page_budget} pages, {time_budget}s, {token_budget} tokens")

        all_scholarships: List[Dict[str, Any]] = []
        all_professors: List[Dict[str, Any]] = []
        pages_processed = 0
        transient_failures = 0

        def log_cb(msg: str, lvl: str = "info"):
            append_job_log(job_id, msg, lvl)

        try:
            crawler = UniversityCrawler(
                seed_url=university_url,
                scope=scope,
                max_pages=page_budget,
                max_depth=max_depth,
                time_limit_seconds=time_budget,
                log_callback=log_cb
            )

            # Check if resuming from an existing checkpoint
            existing_checkpoint = job.get("checkpoint") or get_job_checkpoint(job_id)
            if existing_checkpoint:
                crawler.load_checkpoint(existing_checkpoint)
                pages_processed = crawler.stats.get("pages_crawled", 0)
                log_cb(f"Resuming research run from checkpoint ({pages_processed} pages previously explored).", "info")

            update_job_status(
                job_id=job_id,
                status="running",
                current_step=f"Exploring academic pages (Scope: {scope})",
                progress_pct=20
            )

            stop_reason = "Completed all scheduled pages"

            async for page_info in crawler.crawl():
                # Check for cancellation or pause
                fresh_job = get_job(job_id)
                if fresh_job and fresh_job["status"] in ("cancelled", "paused"):
                    save_job_checkpoint(job_id, crawler.get_checkpoint(), time.time() - start_job_time)
                    append_job_log(job_id, f"Job execution {fresh_job['status']} by user. Checkpoint saved.", "warning")
                    return

                pages_processed = crawler.stats["pages_crawled"]
                page_url = page_info["url"]
                page_title = page_info["title"]
                page_type = page_info["page_type"]
                page_status = page_info.get("page_status", "success")
                text_content = page_info.get("text_content", "")
                emails = page_info.get("emails", [])

                if page_status in ("failed", "inaccessible"):
                    transient_failures += 1

                # Record page with complete provenance in crawl history
                record_crawled_page(
                    job_id=job_id,
                    url=page_url,
                    normalized_url=page_info.get("normalized_url"),
                    page_title=page_title,
                    page_type=page_type,
                    page_status=page_status,
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

                # Skip LLM extraction for empty or blocked pages
                if text_content:
                    # Extract Funding if relevant
                    is_funding_scope = any(s in ("all", "funding", "positions") for s in crawler.active_scopes)
                    if is_funding_scope and (page_type in ("scholarships_funding", "funded_positions", "admissions_eligibility", "general") or any(k in page_url.lower() for k in ["funding", "scholarship", "financial", "aid", "cost", "fellowship", "assistantship", "bursary"])):
                        log_cb(f"Analyzing funding & scholarships from: {page_title or page_url}")
                        found_funding = await extract_funding_opportunities(page_url, text_content, profile, job_id=job_id)
                        if found_funding:
                            inserted_f = insert_scholarships(job_id, found_funding, profile.get("version", 1))
                            all_scholarships.extend(found_funding)
                            log_cb(f"Discovered {inserted_f} funding opportunities on {page_title or page_url}", "success")

                    # Extract Professors & Faculty if relevant
                    is_faculty_scope = any(s in ("all", "faculty", "positions") for s in crawler.active_scopes)
                    if is_faculty_scope and (page_type in ("faculty_directories", "research_labs", "departments", "funded_positions", "general") or any(k in page_url.lower() for k in ["faculty", "people", "directory", "professor", "staff", "research", "lab"])):
                        log_cb(f"Matching professors and academic emails from: {page_title or page_url}")
                        found_profs = await match_professors(
                            page_url=page_url,
                            text_content=text_content,
                            emails_found=emails,
                            profile=profile,
                            job_id=job_id,
                            university_name=uni_name
                        )
                        if found_profs:
                            inserted_p = insert_professors(job_id, found_profs, profile.get("version", 1))
                            all_professors.extend(found_profs)
                            log_cb(f"Identified {inserted_p} matching faculty members on {page_title or page_url}", "success")

                # Get current token usage for the job
                usage = job_budget_tracker.get_job_usage(job_id)
                elapsed_cur = round(time.time() - start_job_time, 2)

                # Save checkpoint after each processed page
                chk = crawler.get_checkpoint()
                save_job_checkpoint(job_id, chk, elapsed_cur)

                # Check token budget
                if usage["total_tokens"] >= token_budget:
                    stop_reason = f"Token budget reached ({usage['total_tokens']}/{token_budget} tokens)"
                    log_cb(f"Reached token budget limit: {usage['total_tokens']} tokens. Pausing LLM parsing.", "warning")
                    break

                # Check request budget
                if usage["requests"] >= request_budget:
                    stop_reason = f"AI request budget reached ({usage['requests']}/{request_budget} requests)"
                    log_cb(f"Reached LLM request budget limit ({request_budget}). Stopping extra extraction.", "warning")
                    break

                # Check time budget
                if elapsed_cur >= time_budget:
                    stop_reason = f"Time budget reached ({time_budget}s)"
                    log_cb(f"Reached crawl time limit ({time_budget}s).", "warning")
                    break

                # Update progress
                progress = min(25 + int((pages_processed / max(page_budget, 1)) * 60), 85)
                update_job_status(
                    job_id=job_id,
                    status="running",
                    current_step=f"Processed {pages_processed}/{page_budget} pages ({len(all_scholarships)} awards, {len(all_professors)} professors, {usage['total_tokens']} AI tokens)",
                    progress_pct=progress,
                    pages_crawled=pages_processed,
                    scholarships_count=len(all_scholarships),
                    professors_count=len(all_professors),
                    llm_requests_count=usage["requests"],
                    llm_prompt_tokens=usage["prompt_tokens"],
                    llm_completion_tokens=usage["completion_tokens"],
                    llm_total_tokens=usage["total_tokens"],
                    elapsed_seconds=elapsed_cur
                )

            # Generate sample outreach drafts for top matching faculty
            update_job_status(job_id=job_id, status="running", current_step="Generating outreach drafts for top faculty", progress_pct=90)
            
            eligible_profs = [
                p for p in all_professors 
                if int(p.get("match_score", 0)) >= 65 
                and p.get("recruitment_status") != "Not accepting students"
                and "do not email" not in (p.get("contact_instructions", "")).lower()
            ]
            if not eligible_profs:
                eligible_profs = [p for p in all_professors if int(p.get("match_score", 0)) >= 60][:2]

            top_profs = eligible_profs[:2]
            for prof in top_profs:
                log_cb(f"Synthesizing personalized outreach draft for {prof.get('name')} (Sending Disabled)")
                await create_outreach_draft(
                    recipient_name=prof.get("name", "Faculty Member"),
                    recipient_email=prof.get("email", "Not found"),
                    recipient_role="Faculty / PI",
                    draft_type="Professor Research Inquiry",
                    context_title=prof.get("research_interests", "Faculty Research Group"),
                    context_details=prof.get("evidence_snippet", "Faculty Profile"),
                    profile=profile,
                    job_id=job_id
                )

            # Record discovered external scholarship leads for human review
            if crawler.external_leads:
                lead_count = insert_external_leads(job_id, crawler.external_leads)
                log_cb(f"Cataloged {lead_count} external funding agency leads for review.", "info")

            # Finalize Job with final token usage and honest status
            final_usage = job_budget_tracker.get_job_usage(job_id)
            final_elapsed = round(time.time() - start_job_time, 2)
            
            # Determine if partially_completed or completed
            final_status = "completed"
            if transient_failures > 0 and (len(all_scholarships) > 0 or len(all_professors) > 0 or pages_processed > 0):
                final_status = "partially_completed"
                stop_reason = f"Completed with {transient_failures} unreachable/blocked pages · {stop_reason}"

            update_job_status(
                job_id=job_id,
                status=final_status,
                current_step=f"Research {final_status.replace('_', ' ')} · {stop_reason}",
                stop_reason=stop_reason,
                progress_pct=100,
                pages_crawled=pages_processed,
                scholarships_count=len(all_scholarships),
                professors_count=len(all_professors),
                llm_requests_count=final_usage["requests"],
                llm_prompt_tokens=final_usage["prompt_tokens"],
                llm_completion_tokens=final_usage["completion_tokens"],
                llm_total_tokens=final_usage["total_tokens"],
                elapsed_seconds=final_elapsed
            )
            append_job_log(
                job_id,
                f"Research {final_status.replace('_', ' ')}: {stop_reason}. Found {len(all_scholarships)} awards and {len(all_professors)} faculty matches in {final_elapsed}s.",
                "success"
            )
            logger.info(f"[Job Queue] Concluded job #{job_id} ({final_status}): {stop_reason}")

        except Exception as e:
            err_str = str(e)
            logger.error(f"[Job Queue] Job #{job_id} failed: {err_str}")
            append_job_log(job_id, f"Error occurred during research: {err_str}", "error")
            err_usage = job_budget_tracker.get_job_usage(job_id)
            update_job_status(
                job_id=job_id,
                status="failed",
                current_step="Failed due to processing error",
                stop_reason=f"Failed: {err_str}",
                error_message=err_str,
                llm_requests_count=err_usage["requests"],
                llm_prompt_tokens=err_usage["prompt_tokens"],
                llm_completion_tokens=err_usage["completion_tokens"],
                llm_total_tokens=err_usage["total_tokens"],
                elapsed_seconds=round(time.time() - start_job_time, 2)
            )

    async def _process_discovery_job(self, job: Dict[str, Any]):
        """
        Executes an autonomous Discovery Mode job with checkpoints, quotas, and transparent stop reasons.
        """
        job_id = job["id"]
        profile_id = job.get("profile_id")
        start_job_time = time.time()

        # Load profile
        profile = None
        if profile_id:
            profile = get_profile_by_id(profile_id)
        if not profile:
            profile = get_active_profile() or {}

        def log_cb(msg: str, lvl: str = "info"):
            append_job_log(job_id, msg, lvl)

        # 1. Check Search Provider
        provider = get_search_provider()
        if not provider.is_configured():
            err_msg = "No search provider configured. Please add an API key for Tavily, SerpAPI, or Brave in Settings, or use University URL Mode."
            update_job_status(
                job_id=job_id,
                status="failed",
                current_step="Search Provider Not Configured",
                stop_reason="Missing search provider credentials",
                error_message=err_msg
            )
            log_cb(err_msg, "error")
            return

        # Budgets
        max_queries = int(job.get("search_queries_count") or config.search_max_queries)
        max_unis = int(job.get("max_pages") or config.discovery_max_universities)
        token_budget = int(job.get("token_budget") or 150000)
        time_budget = int(job.get("time_budget_sec") or 300)

        update_job_status(
            job_id=job_id,
            status="running",
            current_step=f"Executing discovery queries via {provider.display_name}",
            progress_pct=10,
            university_name=f"Discovery Mode ({provider.display_name})",
            token_budget=token_budget,
            time_budget_sec=time_budget
        )
        log_cb(f"Starting Discovery Mode using provider: {provider.display_name} · Limits: {max_queries} queries, {max_unis} institutions")

        try:
            # 2. Run Discovery Engine
            engine = DiscoveryEngine(
                search_provider=provider,
                max_queries=max_queries,
                max_results_per_query=config.search_max_results,
                max_universities=max_unis
            )

            custom_queries = job.get("discovery_queries")
            disc_result = await engine.discover_institutions(profile, custom_queries=custom_queries)

            if not disc_result.get("success"):
                err_msg = disc_result.get("error", "Discovery failed.")
                update_job_status(
                    job_id=job_id,
                    status="failed",
                    current_step="Discovery failed",
                    stop_reason=f"Search failure: {err_msg}",
                    error_message=err_msg
                )
                log_cb(err_msg, "error")
                return

            discovered_unis = disc_result.get("discovered_institutions", [])
            coverage_report = disc_result.get("coverage_report", {})
            ext_leads = disc_result.get("external_leads", [])

            if ext_leads:
                lead_cnt = insert_external_leads(job_id, ext_leads)
                log_cb(f"Cataloged {lead_cnt} external funding agency leads.", "info")

            update_job_status(
                job_id=job_id,
                status="running",
                current_step=f"Discovered {len(discovered_unis)} institutions across {len(coverage_report.get('queries', []))} queries",
                progress_pct=25,
                discovered_institutions=discovered_unis,
                coverage_report=coverage_report,
                search_queries_count=len(coverage_report.get("queries", [])),
                search_results_count=coverage_report.get("summary", {}).get("total_results_found", 0)
            )

            log_cb(f"Discovered {len(discovered_unis)} academic institutions. Exploring official portals with checkpointing...", "success")

            # 3. Official Source Exploration with Checkpoint and Budget Tracking
            all_scholarships: List[Dict[str, Any]] = []
            all_professors: List[Dict[str, Any]] = []
            researched_institutions: List[Dict[str, Any]] = []
            inaccessible_institutions: List[Dict[str, Any]] = []

            scope = job.get("scope", "all")
            pages_per_uni = min(int(job.get("page_budget") or 10), 15)
            stop_reason = "Completed all discovered institutions"

            # Check checkpoint for starting institution index
            start_idx = 0
            existing_checkpoint = job.get("checkpoint") or get_job_checkpoint(job_id)
            if existing_checkpoint and "current_institution_idx" in existing_checkpoint:
                start_idx = existing_checkpoint["current_institution_idx"]
                researched_institutions = existing_checkpoint.get("researched_institutions", [])
                inaccessible_institutions = existing_checkpoint.get("inaccessible_institutions", [])
                log_cb(f"Resuming discovery job from institution #{start_idx+1}/{len(discovered_unis)}.", "info")

            for idx in range(start_idx, len(discovered_unis)):
                uni = discovered_unis[idx]
                
                # Check for cancellation or pause
                fresh_job = get_job(job_id)
                if fresh_job and fresh_job.get("status") in ("cancelled", "paused"):
                    checkpoint_data = {
                        "current_institution_idx": idx,
                        "researched_institutions": researched_institutions,
                        "inaccessible_institutions": inaccessible_institutions,
                        "elapsed_seconds": time.time() - start_job_time
                    }
                    save_job_checkpoint(job_id, checkpoint_data, time.time() - start_job_time)
                    log_cb(f"Discovery run {fresh_job['status']} by user. Institution checkpoint saved.", "warning")
                    return

                # Check time budget
                if (time.time() - start_job_time) > time_budget:
                    stop_reason = f"Time budget limit reached ({time_budget}s)"
                    log_cb(f"Reached time budget limit ({time_budget}s). Finishing current results.", "warning")
                    break

                uni_name = uni.get("institution_name", "Academic Institution")
                lead_url = uni.get("lead_url")
                discovered_via = uni.get("discovered_via_query", "")

                log_cb(f"[{idx+1}/{len(discovered_unis)}] Researching official portal: {uni_name} ({lead_url})")

                try:
                    crawler = UniversityCrawler(
                        seed_url=lead_url,
                        scope=scope,
                        max_pages=pages_per_uni,
                        max_depth=3,
                        time_limit_seconds=60,
                        log_callback=log_cb
                    )

                    uni_scholarships = 0
                    uni_professors = 0
                    uni_pages = 0

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
                            # Extract funding
                            is_funding_scope = any(s in ("all", "funding", "positions") for s in crawler.active_scopes)
                            if is_funding_scope and (page_type in ("scholarships_funding", "funded_positions", "admissions_eligibility", "general") or any(k in page_url.lower() for k in ["funding", "scholarship", "financial", "aid", "cost", "fellowship", "assistantship", "bursary"])):
                                found_f = await extract_funding_opportunities(page_url, text_content, profile, job_id=job_id)
                                if found_f:
                                    for f_item in found_f:
                                        f_item["discovered_via_query"] = discovered_via
                                    inserted_f = insert_scholarships(job_id, found_f, profile.get("version", 1))
                                    all_scholarships.extend(found_f)
                                    uni_scholarships += inserted_f

                            # Extract professors
                            is_faculty_scope = any(s in ("all", "faculty", "positions") for s in crawler.active_scopes)
                            if is_faculty_scope and (page_type in ("faculty_directories", "research_labs", "departments", "funded_positions", "general") or any(k in page_url.lower() for k in ["faculty", "people", "directory", "professor", "staff", "research", "lab"])):
                                found_p = await match_professors(
                                    page_url=page_url,
                                    text_content=text_content,
                                    emails_found=emails,
                                    profile=profile,
                                    job_id=job_id,
                                    university_name=uni_name
                                )
                                if found_p:
                                    for p_item in found_p:
                                        p_item["discovered_via_query"] = discovered_via
                                    inserted_p = insert_professors(job_id, found_p, profile.get("version", 1))
                                    all_professors.extend(found_p)
                                    uni_professors += inserted_p

                    researched_institutions.append({
                        "institution_name": uni_name,
                        "domain": uni.get("root_domain"),
                        "lead_url": lead_url,
                        "pages_crawled": uni_pages,
                        "scholarships_found": uni_scholarships,
                        "professors_found": uni_professors,
                        "discovered_via_query": discovered_via
                    })

                except Exception as crawl_err:
                    log_cb(f"Could not explore {uni_name}: {crawl_err}", "warning")
                    inaccessible_institutions.append({
                        "institution_name": uni_name,
                        "domain": uni.get("root_domain"),
                        "url": lead_url,
                        "error": str(crawl_err),
                        "discovered_via_query": discovered_via
                    })

                # Checkpoint after completed institution
                checkpoint_data = {
                    "current_institution_idx": idx + 1,
                    "researched_institutions": researched_institutions,
                    "inaccessible_institutions": inaccessible_institutions,
                    "elapsed_seconds": time.time() - start_job_time
                }
                save_job_checkpoint(job_id, checkpoint_data, time.time() - start_job_time)

                # Check token budget
                usage = job_budget_tracker.get_job_usage(job_id)
                if usage["total_tokens"] >= token_budget:
                    stop_reason = f"Token budget reached ({usage['total_tokens']}/{token_budget} tokens)"
                    log_cb(f"Token budget reached ({token_budget}). Stopping discovery expansion.", "warning")
                    break

                # Update progress
                progress = 25 + int(((idx + 1) / max(len(discovered_unis), 1)) * 60)
                update_job_status(
                    job_id=job_id,
                    status="running",
                    current_step=f"Researched {idx+1}/{len(discovered_unis)} institutions ({len(all_scholarships)} awards, {len(all_professors)} faculty)",
                    progress_pct=progress,
                    scholarships_count=len(all_scholarships),
                    professors_count=len(all_professors),
                    llm_requests_count=usage["requests"],
                    llm_prompt_tokens=usage["prompt_tokens"],
                    llm_completion_tokens=usage["completion_tokens"],
                    llm_total_tokens=usage["total_tokens"],
                    elapsed_seconds=round(time.time() - start_job_time, 2)
                )

            # 4. Generate Outreach Draft for top match
            eligible_profs = [
                p for p in all_professors 
                if int(p.get("match_score", 0)) >= 65 
                and p.get("recruitment_status") != "Not accepting students"
                and "do not email" not in (p.get("contact_instructions", "")).lower()
            ]
            if not eligible_profs and all_professors:
                eligible_profs = [p for p in all_professors if int(p.get("match_score", 0)) >= 60][:2]

            for prof in eligible_profs[:2]:
                log_cb(f"Synthesizing personalized outreach draft for {prof.get('name')} (Sending Disabled)")
                await create_outreach_draft(
                    recipient_name=prof.get("name", "Faculty Member"),
                    recipient_email=prof.get("email", "Not found"),
                    recipient_role="Faculty / PI",
                    draft_type="Professor Research Inquiry",
                    context_title=prof.get("research_interests", "Faculty Research Group"),
                    context_details=prof.get("evidence_snippet", "Faculty Profile"),
                    profile=profile,
                    job_id=job_id
                )

            # 5. Compile Final Coverage Report
            coverage_report["researched_institutions"] = researched_institutions
            coverage_report["inaccessible_institutions"] = inaccessible_institutions
            coverage_report["summary"]["researched_count"] = len(researched_institutions)
            coverage_report["summary"]["inaccessible_count"] = len(inaccessible_institutions)
            coverage_report["summary"]["total_scholarships_found"] = len(all_scholarships)
            coverage_report["summary"]["total_professors_found"] = len(all_professors)

            final_usage = job_budget_tracker.get_job_usage(job_id)
            final_elapsed = round(time.time() - start_job_time, 2)

            final_status = "completed"
            if len(inaccessible_institutions) > 0 and len(researched_institutions) > 0:
                final_status = "partially_completed"
                stop_reason = f"Completed with {len(inaccessible_institutions)} inaccessible institution portals"

            update_job_status(
                job_id=job_id,
                status=final_status,
                current_step=f"Autonomous discovery {final_status.replace('_', ' ')} · {stop_reason}",
                stop_reason=stop_reason,
                progress_pct=100,
                scholarships_count=len(all_scholarships),
                professors_count=len(all_professors),
                coverage_report=coverage_report,
                llm_requests_count=final_usage["requests"],
                llm_prompt_tokens=final_usage["prompt_tokens"],
                llm_completion_tokens=final_usage["completion_tokens"],
                llm_total_tokens=final_usage["total_tokens"],
                elapsed_seconds=final_elapsed
            )
            log_cb(
                f"Discovery {final_status.replace('_', ' ')}! Verified {len(researched_institutions)} institutions, "
                f"found {len(all_scholarships)} scholarships and {len(all_professors)} professors in {final_elapsed}s. "
                f"(AI Tokens: {final_usage['total_tokens']})",
                "success"
            )

        except Exception as e:
            err_str = str(e)
            logger.error(f"[Job Queue] Discovery Job #{job_id} failed: {err_str}")
            log_cb(f"Error during discovery: {err_str}", "error")
            err_usage = job_budget_tracker.get_job_usage(job_id)
            update_job_status(
                job_id=job_id,
                status="failed",
                current_step="Failed during discovery run",
                stop_reason=f"Failed: {err_str}",
                error_message=err_str,
                llm_requests_count=err_usage["requests"],
                llm_prompt_tokens=err_usage["prompt_tokens"],
                llm_completion_tokens=err_usage["completion_tokens"],
                llm_total_tokens=err_usage["total_tokens"],
                elapsed_seconds=round(time.time() - start_job_time, 2)
            )

job_worker = ResearchJobWorker()
