"""
Configuration Manager for ScholarScout AI Engine.
Supports standard backend environment variables:
- LLM_API_KEYS / NVIDIA_API_KEYS (Multiple NVIDIA / OpenAI keys, comma or newline separated)
- LLM_API_KEY (with fallback to NEMOTRON_API_KEY)
- LLM_BASE_URL (with fallback to NEMOTRON_API_BASE_URL)
- LLM_MODEL (with fallback to NEMOTRON_MODEL_NAME)
- LLM_FALLBACK_MODELS (Comma-separated fallback model list)
- LLM_TIMEOUT_SECONDS
- LLM_MAX_CONCURRENCY
- LLM_MAX_RETRIES
- JOB_MAX_LLM_REQUESTS
- JOB_MAX_LLM_TOKENS

Search Provider configuration:
- SEARCH_PROVIDER (tavily, serpapi, brave, or empty)
- SEARCH_API_KEY (or TAVILY_API_KEY, SERPAPI_API_KEY, BRAVE_SEARCH_API_KEY)
- SEARCH_MAX_QUERIES_PER_JOB
- SEARCH_MAX_RESULTS_PER_QUERY
- DISCOVERY_MAX_UNIVERSITIES

Keeps confidential API keys safely on the backend only.
"""

import os
import re
from pathlib import Path
from typing import Optional, Dict, Any, List, Union
from dotenv import load_dotenv

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

# Load environment variables
if ENV_FILE.exists():
    load_dotenv(ENV_FILE, override=True)
else:
    load_dotenv()

# Complete NVIDIA NIM Models Catalog
NVIDIA_MODELS_CATALOG = [
    {
        "id": "nvidia/llama-3.1-nemotron-70b-instruct",
        "name": "NVIDIA Llama 3.1 Nemotron 70B Instruct (Flagship)",
        "category": "Flagship Reasoning",
        "context_length": 128000,
        "description": "NVIDIA's customized, top-tier model optimized for complex academic reasoning and structured JSON extraction."
    },
    {
        "id": "meta/llama-3.3-70b-instruct",
        "name": "Meta Llama 3.3 70B Instruct",
        "category": "High Accuracy",
        "context_length": 128000,
        "description": "State-of-the-art 70B parameter model with advanced reasoning and factual accuracy."
    },
    {
        "id": "meta/llama-3.1-70b-instruct",
        "name": "Meta Llama 3.1 70B Instruct",
        "category": "High Accuracy",
        "context_length": 128000,
        "description": "Industry benchmark open-weights model for precision summarization and faculty profile analysis."
    },
    {
        "id": "meta/llama-3.1-8b-instruct",
        "name": "Meta Llama 3.1 8B Instruct (Ultra Fast)",
        "category": "Fast & Efficient",
        "context_length": 128000,
        "description": "Lightning fast and cost effective for high-volume university page scraping."
    },
    {
        "id": "deepseek-ai/deepseek-r1",
        "name": "DeepSeek R1 (Reasoning)",
        "category": "Advanced Reasoning",
        "context_length": 64000,
        "description": "Reinforcement-learning optimized deep reasoning model for intricate scholarship eligibility."
    },
    {
        "id": "qwen/qwen2.5-72b-instruct",
        "name": "Qwen 2.5 72B Instruct",
        "category": "High Accuracy",
        "context_length": 128000,
        "description": "High-capacity multilingual model with exceptional structured extraction capability."
    },
    {
        "id": "mistralai/mistral-large-2-instruct",
        "name": "Mistral Large 2 Instruct",
        "category": "High Accuracy",
        "context_length": 128000,
        "description": "Flagship 123B model by Mistral AI for rigorous text analysis."
    },
    {
        "id": "mistralai/mixtral-8x7b-instruct-v0.1",
        "name": "Mixtral 8x7B Instruct",
        "category": "Mixture of Experts",
        "context_length": 32000,
        "description": "High-throughput Mixture-of-Experts architecture."
    },
    {
        "id": "nvidia/nemotron-4-340b-instruct",
        "name": "NVIDIA Nemotron 4 340B Instruct",
        "category": "Heavyweight Enterprise",
        "context_length": 4096,
        "description": "Massive 340B parameter foundational model."
    }
]

def _parse_keys_string(raw: Optional[str]) -> List[str]:
    """Parses comma, semicolon, newline, or whitespace separated API keys into a clean, unique list."""
    if not raw:
        return []
    # Split on commas, semicolons, or newlines
    tokens = re.split(r'[\r\n,;]+', str(raw))
    cleaned = []
    seen = set()
    for t in tokens:
        item = t.strip()
        if item and item not in seen and item != "********":
            seen.add(item)
            cleaned.append(item)
    return cleaned

class AppConfig:
    def __init__(self):
        self.reload()

    def reload(self):
        """Reload configuration from environment variables."""
        # API base URL: defaults to NVIDIA NIM OpenAI-compatible endpoint
        self.llm_base_url = (
            os.getenv("LLM_BASE_URL")
            or os.getenv("NEMOTRON_API_BASE_URL")
            or "https://integrate.api.nvidia.com/v1"
        ).strip().rstrip("/")

        # Multi-key parsing: checks NVIDIA_API_KEYS, LLM_API_KEYS, LLM_API_KEY, NEMOTRON_API_KEY
        raw_keys = (
            os.getenv("NVIDIA_API_KEYS")
            or os.getenv("LLM_API_KEYS")
            or os.getenv("LLM_API_KEY")
            or os.getenv("NEMOTRON_API_KEY")
            or ""
        )
        self.llm_api_keys: List[str] = _parse_keys_string(raw_keys)

        # Primary key for backward compatibility
        self.llm_api_key: str = self.llm_api_keys[0] if self.llm_api_keys else ""

        # Model ID: exact model available in user's provider account
        self.llm_model = (
            os.getenv("LLM_MODEL")
            or os.getenv("NEMOTRON_MODEL_NAME")
            or "nvidia/llama-3.1-nemotron-70b-instruct"
        ).strip()

        # Fallback model list
        raw_fallbacks = os.getenv("LLM_FALLBACK_MODELS", "meta/llama-3.3-70b-instruct,meta/llama-3.1-70b-instruct,meta/llama-3.1-8b-instruct")
        self.llm_fallback_models: List[str] = [m.strip() for m in raw_fallbacks.split(",") if m.strip()]

        # Request timeout and concurrency
        self.llm_timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "45.0"))
        self.llm_max_concurrency = int(os.getenv("LLM_MAX_CONCURRENCY", "4"))
        self.llm_max_retries = int(os.getenv("LLM_MAX_RETRIES", "3"))

        # Job budgets
        self.job_max_llm_requests = int(os.getenv("JOB_MAX_LLM_REQUESTS", "35"))
        self.job_max_llm_tokens = int(os.getenv("JOB_MAX_LLM_TOKENS", "100000"))

        # Search Provider & Discovery Settings
        self.search_provider = (
            os.getenv("SEARCH_PROVIDER")
            or ("tavily" if os.getenv("TAVILY_API_KEY") else "")
            or ("serpapi" if os.getenv("SERPAPI_API_KEY") else "")
            or ("brave" if os.getenv("BRAVE_SEARCH_API_KEY") else "")
            or ""
        ).strip().lower()

        self.search_api_key = (
            os.getenv("SEARCH_API_KEY")
            or os.getenv("TAVILY_API_KEY")
            or os.getenv("SERPAPI_API_KEY")
            or os.getenv("BRAVE_SEARCH_API_KEY")
            or ""
        ).strip()

        self.search_max_queries = int(os.getenv("SEARCH_MAX_QUERIES_PER_JOB", "5"))
        self.search_max_results = int(os.getenv("SEARCH_MAX_RESULTS_PER_QUERY", "10"))
        self.discovery_max_universities = int(os.getenv("DISCOVERY_MAX_UNIVERSITIES", "5"))

        # App & Crawl settings
        self.app_host = os.getenv("APP_HOST", "127.0.0.1")
        self.app_port = int(os.getenv("APP_PORT", "8001"))
        self.database_path = os.getenv("DATABASE_PATH", str(BASE_DIR / "scholarships.db"))
        self.crawl_max_pages = int(os.getenv("CRAWL_MAX_PAGES", "15"))
        self.crawl_timeout = int(os.getenv("CRAWL_TIMEOUT_SECONDS", "12"))
        self.debug = os.getenv("DEBUG_MODE", "True").lower() in ("true", "1", "yes")

    # Compatibility properties
    @property
    def api_base_url(self) -> str:
        return self.llm_base_url

    @api_base_url.setter
    def api_base_url(self, val: str):
        self.llm_base_url = (val or "").strip().rstrip("/")

    @property
    def api_key(self) -> str:
        return self.llm_api_key

    @api_key.setter
    def api_key(self, val: str):
        self.llm_api_key = (val or "").strip()
        if self.llm_api_key and self.llm_api_key not in self.llm_api_keys:
            self.llm_api_keys.insert(0, self.llm_api_key)

    @property
    def model_name(self) -> str:
        return self.llm_model

    @model_name.setter
    def model_name(self, val: str):
        self.llm_model = (val or "").strip()

    def get_api_keys(self) -> List[str]:
        """Returns the full list of active API keys."""
        if self.llm_api_keys:
            return list(self.llm_api_keys)
        if self.llm_api_key:
            return [self.llm_api_key]
        return []

    def update_settings(
        self,
        api_base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        api_keys: Optional[Union[List[str], str]] = None,
        model_name: Optional[str] = None,
        fallback_models: Optional[Union[List[str], str]] = None,
        crawl_max_pages: Optional[int] = None,
        llm_timeout: Optional[float] = None,
        llm_max_concurrency: Optional[int] = None,
        job_max_llm_requests: Optional[int] = None,
        job_max_llm_tokens: Optional[int] = None,
        search_provider: Optional[str] = None,
        search_api_key: Optional[str] = None,
        search_max_queries: Optional[int] = None,
        search_max_results: Optional[int] = None,
        discovery_max_universities: Optional[int] = None
    ):
        """Update settings dynamically and persist to .env file."""
        if api_base_url is not None:
            self.llm_base_url = api_base_url.strip().rstrip("/")
            os.environ["LLM_BASE_URL"] = self.llm_base_url
            os.environ["NEMOTRON_API_BASE_URL"] = self.llm_base_url

        # Process multiple API keys
        if api_keys is not None:
            if isinstance(api_keys, list):
                parsed = []
                for k in api_keys:
                    parsed.extend(_parse_keys_string(k))
            else:
                parsed = _parse_keys_string(str(api_keys))

            if parsed:
                self.llm_api_keys = parsed
                self.llm_api_key = parsed[0]
                os.environ["NVIDIA_API_KEYS"] = ",".join(self.llm_api_keys)
                os.environ["LLM_API_KEY"] = self.llm_api_key
                os.environ["NEMOTRON_API_KEY"] = self.llm_api_key
        elif api_key is not None and api_key != "********":
            parsed = _parse_keys_string(api_key)
            if parsed:
                self.llm_api_keys = parsed
                self.llm_api_key = parsed[0]
                os.environ["NVIDIA_API_KEYS"] = ",".join(self.llm_api_keys)
                os.environ["LLM_API_KEY"] = self.llm_api_key
                os.environ["NEMOTRON_API_KEY"] = self.llm_api_key

        if model_name is not None and model_name.strip():
            self.llm_model = model_name.strip()
            os.environ["LLM_MODEL"] = self.llm_model
            os.environ["NEMOTRON_MODEL_NAME"] = self.llm_model

        if fallback_models is not None:
            if isinstance(fallback_models, list):
                self.llm_fallback_models = [m.strip() for m in fallback_models if m.strip()]
            else:
                self.llm_fallback_models = [m.strip() for m in str(fallback_models).split(",") if m.strip()]
            os.environ["LLM_FALLBACK_MODELS"] = ",".join(self.llm_fallback_models)

        if crawl_max_pages is not None:
            self.crawl_max_pages = int(crawl_max_pages)
            os.environ["CRAWL_MAX_PAGES"] = str(self.crawl_max_pages)

        if llm_timeout is not None:
            self.llm_timeout = float(llm_timeout)
            os.environ["LLM_TIMEOUT_SECONDS"] = str(self.llm_timeout)

        if llm_max_concurrency is not None:
            self.llm_max_concurrency = int(llm_max_concurrency)
            os.environ["LLM_MAX_CONCURRENCY"] = str(self.llm_max_concurrency)

        if job_max_llm_requests is not None:
            self.job_max_llm_requests = int(job_max_llm_requests)
            os.environ["JOB_MAX_LLM_REQUESTS"] = str(self.job_max_llm_requests)

        if job_max_llm_tokens is not None:
            self.job_max_llm_tokens = int(job_max_llm_tokens)
            os.environ["JOB_MAX_LLM_TOKENS"] = str(self.job_max_llm_tokens)

        if search_provider is not None:
            self.search_provider = search_provider.strip().lower()
            os.environ["SEARCH_PROVIDER"] = self.search_provider

        if search_api_key is not None and search_api_key != "********":
            self.search_api_key = search_api_key.strip()
            os.environ["SEARCH_API_KEY"] = self.search_api_key
            if self.search_provider == "tavily":
                os.environ["TAVILY_API_KEY"] = self.search_api_key
            elif self.search_provider == "serpapi":
                os.environ["SERPAPI_API_KEY"] = self.search_api_key
            elif self.search_provider == "brave":
                os.environ["BRAVE_SEARCH_API_KEY"] = self.search_api_key

        if search_max_queries is not None:
            self.search_max_queries = int(search_max_queries)
            os.environ["SEARCH_MAX_QUERIES_PER_JOB"] = str(self.search_max_queries)

        if search_max_results is not None:
            self.search_max_results = int(search_max_results)
            os.environ["SEARCH_MAX_RESULTS_PER_QUERY"] = str(self.search_max_results)

        if discovery_max_universities is not None:
            self.discovery_max_universities = int(discovery_max_universities)
            os.environ["DISCOVERY_MAX_UNIVERSITIES"] = str(self.discovery_max_universities)

        # Write to .env
        self._save_to_env()

    def _save_to_env(self):
        """Persist current settings to .env file."""
        keys_str = ",".join(self.llm_api_keys) if self.llm_api_keys else self.llm_api_key
        fallbacks_str = ",".join(self.llm_fallback_models)

        env_content = f"""# LLM / NVIDIA NIM Multi-Key & Model Configuration
# Supported providers: NVIDIA NIM (https://integrate.api.nvidia.com/v1), OpenAI, Ollama, vLLM, OpenRouter
LLM_BASE_URL={self.llm_base_url}
NVIDIA_API_KEYS={keys_str}
LLM_API_KEY={self.llm_api_key}
LLM_MODEL={self.llm_model}
LLM_FALLBACK_MODELS={fallbacks_str}
LLM_TIMEOUT_SECONDS={self.llm_timeout}
LLM_MAX_CONCURRENCY={self.llm_max_concurrency}
LLM_MAX_RETRIES={self.llm_max_retries}

# Per-Job AI Budgets
JOB_MAX_LLM_REQUESTS={self.job_max_llm_requests}
JOB_MAX_LLM_TOKENS={self.job_max_llm_tokens}

# Search Provider Configuration (Discovery Mode)
# Supported providers: tavily, serpapi, brave
SEARCH_PROVIDER={self.search_provider}
SEARCH_API_KEY={self.search_api_key}
SEARCH_MAX_QUERIES_PER_JOB={self.search_max_queries}
SEARCH_MAX_RESULTS_PER_QUERY={self.search_max_results}
DISCOVERY_MAX_UNIVERSITIES={self.discovery_max_universities}

# Application Settings
APP_HOST={self.app_host}
APP_PORT={self.app_port}
DATABASE_PATH={self.database_path}
CRAWL_MAX_PAGES={self.crawl_max_pages}
CRAWL_TIMEOUT_SECONDS={self.crawl_timeout}
DEBUG_MODE={self.debug}
"""
        try:
            with open(ENV_FILE, "w", encoding="utf-8") as f:
                f.write(env_content)
        except Exception as e:
            print(f"[Config] Warning: Failed to write .env file: {e}")

    def get_public_settings(self) -> dict:
        """Returns non-sensitive view of settings (masking API keys)."""
        masked_llm_keys = []
        for k in self.llm_api_keys:
            if len(k) > 8:
                masked_llm_keys.append(f"{k[:4]}...{k[-4:]}")
            else:
                masked_llm_keys.append("********")

        masked_llm_key = masked_llm_keys[0] if masked_llm_keys else ""
        has_llm_key = bool(self.llm_api_keys or self.llm_api_key)

        masked_search_key = ""
        has_search_key = bool(self.search_api_key)
        if has_search_key:
            if len(self.search_api_key) > 8:
                masked_search_key = f"{self.search_api_key[:4]}...{self.search_api_key[-4:]}"
            else:
                masked_search_key = "********"

        is_local = "localhost" in self.llm_base_url or "127.0.0.1" in self.llm_base_url
        is_configured = (has_llm_key or is_local) and bool(self.llm_model)
        is_search_configured = has_search_key and bool(self.search_provider) and self.search_provider != "none"

        return {
            "api_base_url": self.llm_base_url,
            "model_name": self.llm_model,
            "llm_base_url": self.llm_base_url,
            "llm_model": self.llm_model,
            "llm_fallback_models": self.llm_fallback_models,
            "has_api_key": has_llm_key,
            "masked_api_key": masked_llm_key,
            "api_key_count": len(self.llm_api_keys),
            "masked_api_keys": masked_llm_keys,
            "is_configured": is_configured,
            "is_local": is_local,
            "llm_timeout": self.llm_timeout,
            "llm_max_concurrency": self.llm_max_concurrency,
            "job_max_llm_requests": self.job_max_llm_requests,
            "job_max_llm_tokens": self.job_max_llm_tokens,
            "search_provider": self.search_provider,
            "has_search_api_key": has_search_key,
            "masked_search_api_key": masked_search_key,
            "is_search_configured": is_search_configured,
            "search_max_queries": self.search_max_queries,
            "search_max_results": self.search_max_results,
            "discovery_max_universities": self.discovery_max_universities,
            "crawl_max_pages": self.crawl_max_pages,
            "crawl_timeout": self.crawl_timeout,
            "database_path": self.database_path,
            "nvidia_models_catalog": NVIDIA_MODELS_CATALOG
        }

config = AppConfig()
