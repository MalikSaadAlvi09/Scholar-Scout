# ScholarScout 🎓
> **Autonomous Academic Funding & Faculty Research Finding Agent**  
> Powered by **NVIDIA Nemotron / OpenAI-Compatible LLM Providers**, pluggable **Autonomous Search Providers**, resilient HTTP retrieval, Playwright browser fallback, transactional SQLite storage, controlled outreach email sending, and zero-risk mock sandbox verification.

---

## 🌟 Overview

**ScholarScout** is a comprehensive, production-grade academic research intelligence platform built for prospective graduate (Master's/Ph.D.) and post-graduate researchers. It combines autonomous web crawling, evidence-grounded heuristic evaluation, explainable scoring rubrics, and controlled outreach email management.

---

## 🚀 Core Capabilities & Workflows

### 1. 🔍 Autonomous Discovery Mode
- **Dynamic Query Synthesis**: Formulates focused, high-precision academic search queries dynamically based on candidate profile (target degree, broad subject, specific research interests, country preferences, intake year, and funding requirements).
- **Pluggable Search Providers**:
  - **Tavily Search API** (`tavily`): High-precision, AI-optimized web retrieval.
  - **SerpAPI** (`serpapi`): Structured Google Search engine API.
  - **Brave Search API** (`brave`): Independent, privacy-preserving web search index.
  - **Null Provider** (`none`): Clean fallback when unconfigured, keeping University URL mode fully operational without unauthorized scraping workarounds.
- **Institutional Domain Deduplication**: Isolates institutional root domains (e.g. `cmu.edu` deduplicating across `cs.cmu.edu` and `ri.cmu.edu`), filters commercial aggregators as third-party leads only, and verifies all facts directly against official university pages.
- **Deterministic Search Caching**: SQLite-backed query cache prevents duplicate API calls and conserves search credits.
- **Safety Quotas & Pause/Resume**: Strictly bounds query limits, result counts, institution limits, and total token budgets.

### 2. 🏛️ Targeted University Research & 195+ Global Directory
- **Single or Batch Crawl**: Accepts single university URLs or batch lists (with CSV / newline URL import).
- **Interactive Global Country Directory**: Built-in directory of all 195+ sovereign countries with flag icons, regional groupings, and curated university destinations.
- **1-Click Research Launch**: Immediate crawl initiation directly from any tracked university card.

### 3. 🏆 Funding Opportunities & Scholarship Extraction
- **Verbatim Evidence Citations**: Extracts verified funding details (exact amounts, eligibility, deadlines) with verbatim quote snippets and direct source links. Missing details are strictly marked as `"Unknown"`.
- **Heuristic Fit Scoring**: Multi-factor fit assessment (tuition coverage, stipend, degree level, intake alignment) with explainable rationales.
- **Audit Trail & Diffs**: Historical diff tracking for changed deadlines, funding amounts, or requirements over time.

### 4. 🔬 Faculty Matching & Public Directory Email Discovery
- **Explainable Rubric Scoring**: Multi-dimensional scoring (Research Overlap /40, Experience Fit /30, Recruitment Status /20, Domain Fit /10).
- **Recruitment Classification**: Grounded categorization (`Actively Recruiting`, `Likely Accepting`, `Not Accepting`, `Unstated in Source`).
- **Verified Public Email Discovery**: Extracts institutional faculty emails directly from university directory listings with date observed.

### 5. ✉️ Controlled Email Sending & Outreach Workspace
- **Draft-Only Safety by Default**: Automated dispatch is disabled by default; master toggle requires explicit confirmation.
- **Zero-Risk Mock Sandbox Provider**: Full offline testing of queues, quotas, delays, and simulation of recipient replies without sending external emails.
- **Exact Version Approval**: SHA-256 cryptographic hashing ensures only human-approved drafts can be queued; edits automatically invalidate approvals.
- **Pre-Send Review & Safety Checks**: Verifies recipient policies, suppresses Do-Not-Contact matches, and prevents duplicate sends within 30 days.
- **Durable Outbound Queue**: Sequential dispatch honoring hourly/daily account limits and randomized inter-send delays (10–30s).
- **Suppression & DNC List**: Suppress individual emails or entire university domains (`@harvard.edu`).
- **Immutable Sending Audit Log**: Complete event history recording all approvals, queue dispatches, provider acceptance IDs, timeouts, and reply detections.

### 6. 💾 Database Hot Backups & Safe Rollback Restores
- **Online Zero-Downtime Hot Backups**: SQLite native backup API creates verified snapshots (`PRAGMA integrity_check`) without stopping active crawls.
- **Pre-Restore Safety Snapshots**: Automatically takes a safety snapshot of the active database before executing any restore operation.

### 7. 🔄 Scheduled Rechecks & Staleness Monitoring
- **Automated Opportunity Monitoring**: Regularly re-crawls shortlisted scholarships and faculty profiles (daily, weekly, monthly).
- **Staleness Auto-Tagging**: Items unverified for >30 days are automatically flagged with `⚠️ Stale` warnings.
- **Controlled Startup Catch-up**: Missed runs while offline are safely caught up in a single controlled execution on startup.

### 9. 🤖 Autonomous Scholarship Outreach Gathering Agent ("Start Agent")
- **1-Click End-to-End Pipeline**: A single prominent header button triggers autonomous university discovery, official scholarship crawling, and faculty scraping in the background.
- **Quick Profile Input Modal**: Immediate degree multi-selection (`BS`, `MS`, `MPhil`, `Ph.D.`), subject / field of study free-text, and optional target country preferences.
- **NVIDIA Multi-Key Pool & Round-Robin Load Balancing**:
  - Accepts multiple NVIDIA API keys via `NVIDIA_API_KEYS` / `LLM_API_KEYS` in `.env` or UI Settings.
  - Automatically distributes requests across keys and seamlessly fails over on rate limits (`HTTP 429`) or quota exhaustion.
  - One-click diagnostics to verify all keys in the pool simultaneously (`POST /api/settings/test-all-keys`).
- **NVIDIA NIM Model Catalog**: Select from top-tier reasoning and fast scraping models:
  - `nvidia/llama-3.1-nemotron-70b-instruct` (Flagship / High Accuracy - Default)
  - `meta/llama-3.3-70b-instruct` (Llama 3.3 70B - High Reasoning)
  - `meta/llama-3.1-70b-instruct` (Llama 3.1 70B)
  - `deepseek-ai/deepseek-r1` (DeepSeek R1 - Advanced Math/Code Reasoning)
  - `qwen/qwen2.5-72b-instruct` (Qwen 2.5 72B - Multilingual)
  - `mistralai/mistral-large-2-instruct` (Mistral Large 2 123B)
  - `meta/llama-3.1-8b-instruct` (Llama 3.1 8B - High Throughput)
  - `mistralai/mixtral-8x7b-instruct-v0.1` (Mixtral 8x7B MoE)
  - `nvidia/nemotron-4-340b-instruct` (Nemotron 4 340B)
  - Custom model identifiers supported.
- **Strict Verification & Fact-Grounded Data Collection**:
  - Scrapes official funding pages for name, degree level, coverage (tuition/stipend), eligibility, deadline, and official URL.
  - Scrapes faculty directories for name, title, department, research interests, public email, phone, and profile URL.
  - Never fabricates contact information (leaves unlisted fields empty).
  - Preserves exact source URLs for every data point collected.
- **Live Progress UI & Resilient Job Controls**:
  - Displays real-time status, active university being processed, step indicator, and live count metrics (universities, scholarships, professors).
  - Interactive live scrolling terminal log with timestamped action events.
  - Non-destructive **Pause**, **Resume**, and **Stop** controls with automatic state checkpoints.
- **Auto-Generated Multi-Sheet Excel & CSV Exports**:
  - Produces formatted 2-sheet Excel workbooks (`.xlsx` via openpyxl) featuring:
    - **Sheet 1 (`Universities & Scholarships`)**: University, Country, Scholarship Name, Degree Level, Funding Coverage, Eligibility, Deadline, Official URL, Department Contact, Source URL.
    - **Sheet 2 (`Professors`)**: Professor Name, University, Department, Academic Title, Research Focus, Relevance Match Score (0–100), Public Email, Phone, Profile URL, Source URL.
    - Styled with professional Navy blue headers (`#1E3A8A`), auto-fitted column widths, alternating zebra rows, and spreadsheet formula injection sanitization.
  - One-click downloads available directly from the UI terminal upon completion or via `/api/agent/export/{job_id}/excel` and `/api/agent/export/{job_id}/csv`.

---

## 🏗️ Architectural Layout

```
ScholarScout/
├── backend/
│   ├── agents/             # Autonomous Gathering Agent Orchestrator & Checkpointing
│   │   └── gathering_agent.py # University search, scholarship crawl, faculty ranking & verification
│   ├── api/                # FastAPI REST API routes & schema validators
│   ├── config.py           # Configuration management (NVIDIA Multi-Key Pool, Models Catalog, limits)
│   ├── database.py         # SQLite schema initialization, indices, migrations & CRUD
│   ├── discovery/          # Autonomous discovery engine, query generator, normalizer & crawler
│   │   ├── search_providers/ # Pluggable provider interface (Tavily, SerpAPI, Brave, Null)
│   │   ├── query_generator.py # Structured academic query synthesis
│   │   ├── engine.py       # Discovery coordinator, lead filtering, quotas & coverage
│   │   ├── crawler.py      # Focused academic crawler with prioritized URL queue
│   │   ├── global_directory.py # 195+ world countries and international universities
│   │   └── url_normalizer.py # Canonical normalization & institutional domain matching
│   ├── emails/             # Controlled email workspace, approvals, queue & providers
│   │   ├── sending_manager.py # Master sending switch & dispatch orchestrator
│   │   ├── accounts.py     # Sender account manager (Sandbox, Gmail, Outlook, SMTP)
│   │   ├── queue_manager.py # Durable outbound queue, batch processing & retries
│   │   ├── dnc_manager.py  # Do-Not-Contact & domain-wide suppression list
│   │   ├── audit_logger.py # Immutable outbound sending event audit log
│   │   ├── generator.py    # Outreach draft generator with grounded evidence
│   │   └── providers/      # Mock sandbox, Gmail OAuth, Outlook OAuth, Custom SMTP
│   ├── export/             # Data exporter, formula defense & database backup manager
│   │   ├── data_exporter.py # Multi-sheet formatted Excel & CSV exports with formula protection
│   │   └── backup_manager.py# Online SQLite transactional backups & safe restore
│   ├── funding/            # Scholarship & financial aid extraction with evidence quotes
│   ├── jobs/               # Persistent SQLite-backed research job worker & rechecks
│   │   └── rechecks.py     # Scheduled recurring rechecks & staleness monitoring
│   ├── llm/                # Unified AI client, Pydantic schemas, security & budgets
│   │   ├── client.py       # Multi-key AsyncOpenAI client with round-robin rotation & 429 failover
│   │   ├── exceptions.py   # Classified AI error types with setup instructions
│   │   ├── schemas.py      # Strict Pydantic models for structured output & tokens
│   │   ├── security.py     # Prompt injection defense & untrusted content framing
│   │   ├── budget.py       # Per-job request & token budget tracker
│   │   └── nemotron_client.py # Backward-compatible facade
│   ├── logging_utils.py    # Structured logging with secret & token redaction
│   ├── main.py             # FastAPI app initialization & static routes
│   ├── profiles/           # Student academic profile manager & PDF CV parser
│   ├── professors/         # Faculty research matcher & email parser
│   └── retrieval/          # Async HTTP fetcher + SSRF guard + Playwright fallback
├── static/
│   ├── css/styles.css      # Glassmorphic dark theme, terminal styling, key badges
│   ├── js/app.js           # Frontend controller, gathering agent poller & NVIDIA key pool UI
│   └── index.html          # Single-page web dashboard (10 screens, Start Agent modal, live terminal)
├── tests/                  # Complete automated pytest test suite (156 tests)
│   ├── test_gathering_agent.py        # Autonomous agent, multi-key rotation, 429 failover & Excel exports
│   ├── test_ai_client.py              # AI client, retries, bounded repair & error classification
│   ├── test_ai_security.py            # Prompt injection defense & tag containment
│   ├── test_budgets_and_connection.py # Job budgets & connection test diagnostics
│   ├── test_controlled_email_sending.py # Account limits, DNC, hashing, queue & sandbox
│   ├── test_dashboard_routes.py       # REST API endpoints & executive overview
│   ├── test_database.py               # SQLite CRUD, transactions & schema tests
│   ├── test_discovery_search.py       # Pluggable search providers, query gen & coverage
│   ├── test_email_workspace.py        # Outreach draft workspace & clipboard safety
│   ├── test_extraction.py             # Heuristic extraction & regex tests
│   ├── test_funding_extraction.py     # Verbatim quotes & scholarship extraction
│   ├── test_global_directory.py       # 195+ country directory & university search
│   ├── test_health.py                 # Health check and public settings tests
│   ├── test_logging.py                # Secret redaction & logging tests
│   ├── test_professors_discovery.py   # Faculty matching & recruitment status
│   ├── test_profile_and_cv.py         # Profile manager & CV extraction
│   ├── test_reliability_and_exports.py # Backups, safe restore & formula injection defense
│   └── test_university_research.py     # University research mode, crawler & SSRF guard
├── run.py                  # Single-command launcher for Windows & local systems
├── requirements.txt        # Python package dependencies (including openpyxl)
├── .env.example            # Environment configuration template
├── .gitignore              # Protects keys, databases, logs, and artifacts
└── README.md               # Documentation & setup guide
```

---

## ⚙️ Environment Variables & Configuration

| Variable | Description | Default |
| :--- | :--- | :--- |
| `NVIDIA_API_KEYS` / `LLM_API_KEYS` | Multiple NVIDIA / OpenAI API keys (comma or newline separated) | `""` |
| `LLM_API_KEY` | Primary fallback API Key for NVIDIA NIM or OpenAI-compatible provider | `""` |
| `LLM_BASE_URL` | Base URL of OpenAI-compatible API endpoint | `https://integrate.api.nvidia.com/v1` |
| `LLM_MODEL` | Exact model identifier (e.g. `nvidia/llama-3.1-nemotron-70b-instruct`) | `nvidia/llama-3.1-nemotron-70b-instruct` |
| `LLM_FALLBACK_MODELS` | Comma-separated list of fallback models on provider error | `meta/llama-3.3-70b-instruct,meta/llama-3.1-70b-instruct,meta/llama-3.1-8b-instruct` |
| `LLM_TIMEOUT_SECONDS` | Maximum timeout per request in seconds | `45.0` |
| `LLM_MAX_CONCURRENCY` | Maximum concurrent requests to provider | `3` |
| `LLM_MAX_RETRIES` | Bounded retries for temporary failures (5xx / 429) | `3` |
| `JOB_MAX_LLM_REQUESTS`| Request budget limit per research run | `25` |
| `JOB_MAX_LLM_TOKENS`  | Token safety budget limit per research run | `60000` |
| `SEARCH_PROVIDER` | Search provider: `tavily`, `serpapi`, `brave`, or empty | `""` |
| `SEARCH_API_KEY` | API key for the configured search provider | `""` |
| `SEARCH_MAX_QUERIES_PER_JOB` | Maximum search queries generated per discovery run | `5` |
| `SEARCH_MAX_RESULTS_PER_QUERY` | Maximum search leads retrieved per query | `10` |
| `DISCOVERY_MAX_UNIVERSITIES` | Maximum universities crawled per discovery run | `5` |
| `APP_HOST` | Local server bind address | `127.0.0.1` |
| `APP_PORT` | Local server port | `8001` |
| `DATABASE_PATH` | Path to persistent SQLite database file | `scholarships.db` |
| `CRAWL_MAX_PAGES` | Max pages scanned per university run | `15` |
| `CRAWL_TIMEOUT_SECONDS`| Webpage fetch timeout | `12` |

---

## 🪟 Quickstart Guide

### 1. Install Dependencies
```powershell
python -m pip install -r requirements.txt
playwright install chromium
```

### 2. Configure Environment or Run Dashboard
```powershell
copy .env.example .env
python run.py
```
Open **`http://127.0.0.1:8001`** in your web browser.

### 3. Run Automated Tests
```powershell
python -m pytest
```
All **156 tests** across all 18 test modules will execute and verify the entire system.
```

---

## ⚙️ Environment Variables & Configuration

| Variable | Description | Default |
| :--- | :--- | :--- |
| `LLM_API_KEY` | API Key for NVIDIA NIM or OpenAI-compatible provider | `""` |
| `LLM_BASE_URL` | Base URL of OpenAI-compatible API endpoint | `https://integrate.api.nvidia.com/v1` |
| `LLM_MODEL` | Exact model ID available in your provider account | `nvidia/llama-3.1-nemotron-70b-instruct` |
| `LLM_TIMEOUT_SECONDS` | Maximum timeout per request in seconds | `45.0` |
| `LLM_MAX_CONCURRENCY` | Maximum concurrent requests to provider | `3` |
| `LLM_MAX_RETRIES` | Bounded retries for temporary failures (5xx / 429) | `3` |
| `JOB_MAX_LLM_REQUESTS`| Request budget limit per research run | `25` |
| `JOB_MAX_LLM_TOKENS`  | Token safety budget limit per research run | `60000` |
| `SEARCH_PROVIDER` | Search provider: `tavily`, `serpapi`, `brave`, or empty | `""` |
| `SEARCH_API_KEY` | API key for the configured search provider | `""` |
| `SEARCH_MAX_QUERIES_PER_JOB` | Maximum search queries generated per discovery run | `5` |
| `SEARCH_MAX_RESULTS_PER_QUERY` | Maximum search leads retrieved per query | `10` |
| `DISCOVERY_MAX_UNIVERSITIES` | Maximum universities crawled per discovery run | `5` |
| `APP_HOST` | Local server bind address | `127.0.0.1` |
| `APP_PORT` | Local server port | `8001` |
| `DATABASE_PATH` | Path to persistent SQLite database file | `scholarships.db` |
| `CRAWL_MAX_PAGES` | Max pages scanned per university run | `15` |
| `CRAWL_TIMEOUT_SECONDS`| Webpage fetch timeout | `12` |

---

## 🪟 Quickstart Guide

### 1. Install Dependencies
```powershell
python -m pip install -r requirements.txt
playwright install chromium
```

### 2. Configure Environment or Run Dashboard
```powershell
copy .env.example .env
python run.py
```
Open **`http://127.0.0.1:8001`** in your web browser.

### 3. Run Automated Tests
```powershell
python -m pytest
```
All **145 tests** across all 17 test modules will execute and verify the entire system.
