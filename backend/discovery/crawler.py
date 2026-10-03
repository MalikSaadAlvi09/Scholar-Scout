"""
University Discovery, Academic Link Crawler & Scope-Aware Research Engine.
Performs depth-bounded, priority-queued academic website exploration with
scope filtering across funding, admissions, degree programs, departments,
faculty directories, research labs, and advertised funded positions.
"""

import time
import asyncio
from typing import List, Dict, Any, Set, Optional, Callable, AsyncGenerator, Union, Tuple
from urllib.parse import urlparse
from backend.config import config
from backend.logging_utils import logger
from backend.discovery.url_normalizer import (
    normalize_url,
    is_same_institution_domain,
    classify_domain_type
)

# --- Category Keyword Dictionaries & Classifiers ---

CATEGORY_KEYWORDS = {
    "scholarships_funding": [
        "scholarship", "scholarships", "funding", "fellowship", "fellowships",
        "financial-aid", "financialaid", "bursary", "bursaries", "grants",
        "tuition-waiver", "graduate-funding", "phd-funding", "assistantship",
        "stipend", "merit-aid", "awards", "costs-and-funding", "student-finance"
    ],
    "admissions_eligibility": [
        "admissions", "admission", "apply", "how-to-apply", "eligibility",
        "entry-requirements", "requirements", "deadlines", "application-process",
        "international-admissions", "gpa-requirement", "toefl-requirement"
    ],
    "degree_programs": [
        "programs", "degree-programs", "graduate-programs", "phd-programs",
        "masters-programs", "curriculum", "courses", "academics/degrees",
        "study-with-us", "majors", "specializations"
    ],
    "departments": [
        "departments", "department", "school", "faculty-of", "division",
        "institutes", "centers", "academic-units", "chairs", "eecs", "cs"
    ],
    "faculty_directories": [
        "faculty", "people", "directory", "professors", "faculty-directory",
        "academic-staff", "researchers", "our-people", "faculty-and-staff",
        "faculty-profiles", "faculty-roster"
    ],
    "research_labs": [
        "labs", "lab", "research-groups", "research-centers", "laboratories",
        "facilities", "research-themes", "projects", "initiatives"
    ],
    "funded_positions": [
        "vacancies", "openings", "positions", "phd-positions", "funded-positions",
        "jobs", "join-us", "postdoc-positions", "research-assistantships",
        "gra-openings", "gta-openings", "opportunities"
    ]
}

def classify_page_category(url: str, title: str, text: str) -> Tuple[str, float]:
    """
    Classifies page content into one of 7 academic scopes with a confidence score.
    Returns: (category_name, confidence_score)
    """
    url_lower = url.lower()
    title_lower = title.lower()
    sample_text = text[:2500].lower()

    scores: Dict[str, float] = {}

    for cat, keywords in CATEGORY_KEYWORDS.items():
        score = 0.0
        # URL matching (highest weight)
        for kw in keywords:
            if kw in url_lower:
                score += 3.5
            if kw in title_lower:
                score += 2.5
            # Word match in first 2500 characters
            if f" {kw} " in sample_text or f"{kw}:" in sample_text:
                score += 1.0

        scores[cat] = score

    # Find highest scoring category
    best_cat = max(scores, key=scores.get)
    best_score = scores[best_cat]

    if best_score >= 2.0:
        return best_cat, best_score
    return "general", 0.0

def calculate_priority_and_reason(
    url: str,
    anchor_text: str,
    parent_category: str,
    active_scopes: List[str],
    depth: int
) -> Tuple[int, str, str]:
    """
    Calculates crawl priority score and human-readable selection reason.
    Returns: (priority: int, selection_reason: str, predicted_category: str)
    """
    norm_text = f"{url.lower()} {anchor_text.lower()}"
    matched_cats = []
    base_priority = 50 - (depth * 10)  # Depth penalty

    for cat, kws in CATEGORY_KEYWORDS.items():
        for kw in kws:
            if kw in norm_text:
                matched_cats.append(cat)
                break

    # Scope match checks
    is_funding_scope = any(s in ("funding", "scholarships_funding", "scholarships", "all") for s in active_scopes)
    is_faculty_scope = any(s in ("faculty", "faculty_directories", "professors", "all") for s in active_scopes)
    is_positions_scope = any(s in ("positions", "funded_positions", "all") for s in active_scopes)
    is_admissions_scope = any(s in ("admissions", "admissions_eligibility", "all") for s in active_scopes)
    is_labs_scope = any(s in ("labs", "research_labs", "all") for s in active_scopes)
    is_degrees_scope = any(s in ("degrees", "degree_programs", "departments", "all") for s in active_scopes)

    if "scholarships_funding" in matched_cats:
        prio = base_priority + (50 if is_funding_scope else 20)
        reason = f"Scholarship & Funding link: '{anchor_text[:40] or url.split('/')[-1]}' (Depth {depth})"
        return prio, reason, "scholarships_funding"

    if "faculty_directories" in matched_cats:
        prio = base_priority + (45 if is_faculty_scope else 15)
        reason = f"Faculty Directory link: '{anchor_text[:40] or url.split('/')[-1]}' (Depth {depth})"
        return prio, reason, "faculty_directories"

    if "funded_positions" in matched_cats:
        prio = base_priority + (45 if is_positions_scope else 15)
        reason = f"Funded Vacancy / Position link: '{anchor_text[:40] or url.split('/')[-1]}' (Depth {depth})"
        return prio, reason, "funded_positions"

    if "admissions_eligibility" in matched_cats:
        prio = base_priority + (40 if is_admissions_scope else 20)
        reason = f"Admissions & Eligibility link: '{anchor_text[:40] or url.split('/')[-1]}' (Depth {depth})"
        return prio, reason, "admissions_eligibility"

    if "research_labs" in matched_cats:
        prio = base_priority + (35 if is_labs_scope else 15)
        reason = f"Research Lab link: '{anchor_text[:40] or url.split('/')[-1]}' (Depth {depth})"
        return prio, reason, "research_labs"

    if "degree_programs" in matched_cats or "departments" in matched_cats:
        prio = base_priority + (30 if is_degrees_scope else 15)
        reason = f"Department / Degree Program link: '{anchor_text[:40] or url.split('/')[-1]}' (Depth {depth})"
        return prio, reason, "degree_programs"

    # Generic institutional page
    prio = max(base_priority, 5)
    reason = f"Institutional link on {parent_category or 'homepage'} (Depth {depth})"
    return prio, reason, "general"

class UniversityCrawler:
    """
    Scope-aware university crawler that adheres to robots.txt, per-domain rate limits,
    configurable page/depth/time limits, SSRF protection, and isolates external leads.
    """
    def __init__(
        self,
        seed_url: str,
        scope: Union[str, List[str]] = "all",
        max_pages: Optional[int] = None,
        max_depth: int = 3,
        time_limit_seconds: int = 120,
        max_download_size_bytes: int = 5 * 1024 * 1024,
        use_cache: bool = True,
        use_playwright_fallback: bool = True,
        log_callback: Optional[Callable[[str, str], None]] = None
    ):
        self.seed_url = seed_url.strip()
        self.max_pages = max_pages or config.crawl_max_pages
        self.max_depth = max_depth
        self.time_limit_seconds = time_limit_seconds
        self.max_download_size_bytes = max_download_size_bytes
        self.use_cache = use_cache
        self.use_playwright_fallback = use_playwright_fallback
        self.log_callback = log_callback or (lambda msg, lvl: None)

        # Normalize scopes
        if isinstance(scope, str):
            self.active_scopes = [s.strip().lower() for s in scope.split(",") if s.strip()]
        else:
            self.active_scopes = [s.lower() for s in scope]
        if not self.active_scopes:
            self.active_scopes = ["all"]

        parsed = urlparse(self.seed_url)
        self.base_domain = parsed.netloc

        self.visited_urls: Set[str] = set()
        self.queue: List[Dict[str, Any]] = []
        self.external_leads: List[Dict[str, Any]] = []
        self.start_time = 0.0

        # Metrics
        self.stats = {
            "pages_crawled": 0,
            "pages_successful": 0,
            "pages_blocked": 0,
            "pages_inaccessible": 0,
            "pages_failed": 0,
            "pdfs_parsed": 0,
            "scanned_documents": 0,
            "external_leads_found": 0
        }

    def log(self, message: str, level: str = "info"):
        self.log_callback(message, level)
        if level == "error":
            logger.error(f"[Crawler] {message}")
        elif level == "warning":
            logger.warning(f"[Crawler] {message}")
        else:
            logger.info(f"[Crawler] {message}")

    def get_checkpoint(self) -> Dict[str, Any]:
        """Captures a serializable snapshot of crawler state for pausing and resuming."""
        elapsed = round(time.time() - self.start_time, 2) if self.start_time else 0.0
        return {
            "seed_url": self.seed_url,
            "visited_urls": list(self.visited_urls),
            "queue": self.queue,
            "external_leads": self.external_leads,
            "stats": dict(self.stats),
            "elapsed_seconds": elapsed,
            "active_scopes": self.active_scopes
        }

    def load_checkpoint(self, checkpoint: Dict[str, Any]):
        """Restores crawler state from a saved checkpoint."""
        if not checkpoint:
            return
        self.visited_urls = set(checkpoint.get("visited_urls", []))
        self.queue = list(checkpoint.get("queue", []))
        self.external_leads = list(checkpoint.get("external_leads", []))
        if "stats" in checkpoint:
            self.stats.update(checkpoint["stats"])
        prev_elapsed = checkpoint.get("elapsed_seconds", 0.0)
        # Adjust start_time to account for already consumed elapsed budget
        self.start_time = time.time() - prev_elapsed
        self.log(f"Resumed crawler from checkpoint ({len(self.visited_urls)} visited, {len(self.queue)} queue, {prev_elapsed}s elapsed)")

    async def crawl(self) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Executes the university research crawl and yields structured page representations.
        Supports resuming from loaded checkpoints and bounded retries for transient errors.
        """
        if not self.start_time:
            self.start_time = time.time()
        self.log(f"Starting University Research Mode on: {self.seed_url} (Scope: {', '.join(self.active_scopes)}, Max Pages: {self.max_pages}, Max Depth: {self.max_depth})")

        # Only add seed if queue is empty and no urls visited
        if not self.queue and not self.visited_urls:
            norm_seed = normalize_url(self.seed_url)
            self.queue.append({
                "url": self.seed_url,
                "normalized_url": norm_seed,
                "priority": 100,
                "depth": 0,
                "anchor": "Seed Homepage",
                "selection_reason": "Seed university URL provided by user",
                "parent_category": "homepage"
            })

        while self.queue and self.stats["pages_crawled"] < self.max_pages:
            # Check time limit
            elapsed = time.time() - self.start_time
            if elapsed > self.time_limit_seconds:
                self.log(f"Reached crawl time limit ({self.time_limit_seconds}s). Concluding run.", "warning")
                break

            # Sort queue by priority descending
            self.queue.sort(key=lambda item: item["priority"], reverse=True)
            current_item = self.queue.pop(0)
            current_url = current_item["url"]
            current_norm = current_item["normalized_url"]
            current_depth = current_item["depth"]
            selection_reason = current_item["selection_reason"]

            if current_norm in self.visited_urls:
                continue

            self.visited_urls.add(current_norm)
            self.stats["pages_crawled"] += 1

            self.log(f"[{self.stats['pages_crawled']}/{self.max_pages}] Fetching (Depth {current_depth}): {current_url} · Reason: {selection_reason}")

            # Fetch page safely with bounded retries for transient failures
            from backend.retrieval.fetcher import fetch_page
            page_data = None
            max_retries = 3
            for attempt in range(1, max_retries + 1):
                try:
                    page_data = await fetch_page(
                        url=current_url,
                        use_playwright_fallback=self.use_playwright_fallback,
                        use_cache=self.use_cache,
                        max_download_size_bytes=self.max_download_size_bytes
                    )
                    # If transient status code, retry
                    if page_data.status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
                        self.log(f"Transient HTTP {page_data.status_code} on {current_url}. Retry {attempt}/{max_retries}...", "warning")
                        await asyncio.sleep(min(2 ** attempt, 6))
                        continue
                    break
                except Exception as fetch_err:
                    if attempt < max_retries:
                        self.log(f"Transient error fetching {current_url}: {fetch_err}. Retry {attempt}/{max_retries}...", "warning")
                        await asyncio.sleep(min(2 ** attempt, 6))
                    else:
                        from backend.retrieval.fetcher import PageFetchResult
                        page_data = PageFetchResult(
                            url=current_url,
                            status_code=500,
                            page_status="failed",
                            status_reason=f"Transient network failure after {max_retries} attempts: {fetch_err}",
                            title="Error Loading Page",
                            text_content="",
                            html_content="",
                            links=[],
                            emails=[],
                            retrieval_method="http",
                            content_hash="",
                            byte_size=0
                        )

            if not page_data:
                continue

            # Update status counters
            if page_data.page_status == "success":
                self.stats["pages_successful"] += 1
                if page_data.retrieval_method == "pdf":
                    self.stats["pdfs_parsed"] += 1
            elif page_data.page_status == "scanned_document":
                self.stats["scanned_documents"] += 1
                self.log(f"Scanned image PDF detected (no selectable text): {current_url}", "warning")
            elif page_data.page_status == "blocked":
                self.stats["pages_blocked"] += 1
                self.log(f"Access blocked for {current_url}: {page_data.status_reason}", "warning")
            elif page_data.page_status == "inaccessible":
                self.stats["pages_inaccessible"] += 1
                self.log(f"Inaccessible URL {current_url}: {page_data.status_reason}", "warning")
            else:
                self.stats["pages_failed"] += 1
                self.log(f"Failed retrieval for {current_url}: {page_data.status_reason}", "warning")

            if not page_data.text_content and page_data.page_status != "scanned_document":
                # Yield even failed/blocked pages for UI visibility and accurate status reporting
                yield {
                    "url": current_url,
                    "normalized_url": current_norm,
                    "title": page_data.title or "Unreachable Page",
                    "page_type": "general",
                    "page_status": page_data.page_status,
                    "status_reason": page_data.status_reason,
                    "selection_reason": selection_reason,
                    "text_content": "",
                    "html_content": "",
                    "emails": [],
                    "status_code": page_data.status_code,
                    "retrieval_method": page_data.retrieval_method,
                    "content_hash": page_data.content_hash,
                    "byte_size": page_data.byte_size,
                    "depth": current_depth,
                    "is_external": False,
                    "external_domain_type": "official_university",
                    "pages_crawled_count": self.stats["pages_crawled"]
                }
                continue

            # Classify page intent / category
            page_category, confidence = classify_page_category(
                current_url, page_data.title, page_data.text_content
            )

            self.log(f"Read '{page_data.title or 'Untitled'}' ({page_category.upper()}) · Method: {page_data.retrieval_method.upper()} · Hash: {page_data.content_hash[:8]} · Found {len(page_data.emails)} emails, {len(page_data.links)} links")

            # Extract & evaluate new links if within max_depth
            if current_depth < self.max_depth:
                for link_info in page_data.links:
                    link_url = link_info["url"]
                    norm_link = link_info.get("normalized_url") or normalize_url(link_url)

                    if norm_link in self.visited_urls:
                        continue

                    # Classify domain type
                    domain_type, provider_or_domain = classify_domain_type(link_url, self.base_domain)

                    if domain_type == "official_university":
                        # Internal university link -> calculate priority and schedule
                        prio, reason, pred_cat = calculate_priority_and_reason(
                            link_url,
                            link_info.get("text", ""),
                            page_category,
                            self.active_scopes,
                            current_depth + 1
                        )
                        self.queue.append({
                            "url": link_url,
                            "normalized_url": norm_link,
                            "priority": prio,
                            "depth": current_depth + 1,
                            "anchor": link_info.get("text", ""),
                            "selection_reason": reason,
                            "parent_category": page_category
                        })

                    elif domain_type in ("external_scholarship_provider", "third_party_lead"):
                        # External Lead -> record for review without unconstrained external crawling
                        if not any(l["url"] == link_url for l in self.external_leads):
                            lead_title = link_info.get("text", "") or provider_or_domain
                            lead_type = "national_scholarship_agency" if domain_type == "external_scholarship_provider" else "external_lead"
                            self.external_leads.append({
                                "url": link_url,
                                "domain": provider_or_domain,
                                "lead_title": lead_title,
                                "lead_type": lead_type,
                                "context_snippet": f"Found on {page_data.title or current_url}",
                                "source_page_url": current_url
                            })
                            self.stats["external_leads_found"] += 1
                            if domain_type == "external_scholarship_provider":
                                self.log(f"Discovered external funding agency: {provider_or_domain} ({link_url})", "info")

                # Deduplicate queue keeping highest priority
                unique_queue: Dict[str, Dict[str, Any]] = {}
                for item in self.queue:
                    u = item["normalized_url"]
                    if u not in unique_queue or item["priority"] > unique_queue[u]["priority"]:
                        unique_queue[u] = item
                self.queue = list(unique_queue.values())

            # Yield enriched page object
            yield {
                "url": current_url,
                "normalized_url": current_norm,
                "title": page_data.title,
                "page_type": page_category,
                "page_status": page_data.page_status,
                "status_reason": page_data.status_reason,
                "selection_reason": selection_reason,
                "text_content": page_data.text_content,
                "html_content": page_data.html_content,
                "emails": page_data.emails,
                "status_code": page_data.status_code,
                "retrieval_method": page_data.retrieval_method,
                "content_hash": page_data.content_hash,
                "byte_size": page_data.byte_size,
                "depth": current_depth,
                "is_external": False,
                "external_domain_type": "official_university",
                "pages_crawled_count": self.stats["pages_crawled"]
            }

        elapsed_total = round(time.time() - self.start_time, 2)
        self.log(f"Crawl completed in {elapsed_total}s. Visited: {self.stats['pages_crawled']} pages ({self.stats['pages_successful']} success, {self.stats['pdfs_parsed']} PDFs, {self.stats['pages_blocked']} blocked, {self.stats['external_leads_found']} external leads)")

# Backward compatibility shims
classify_page_intent = classify_page_category
is_same_or_subdomain = is_same_institution_domain
FUNDING_KEYWORDS = CATEGORY_KEYWORDS["scholarships_funding"]
FACULTY_KEYWORDS = CATEGORY_KEYWORDS["faculty_directories"]

def calculate_url_priority(url: str, anchor_text: str = "", parent_intent: str = "general") -> int:
    prio, _, _ = calculate_priority_and_reason(url, anchor_text, parent_intent, ["all"], depth=0)
    return prio

