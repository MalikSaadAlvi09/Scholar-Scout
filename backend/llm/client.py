"""
Reusable, Resilient AI Client for ScholarScout.
Supports NVIDIA NIM (Nemotron, Llama 3.3, DeepSeek R1, Mistral, Qwen), OpenAI, Ollama, vLLM, and any OpenAI-compatible provider.

Features:
- Multi-API-Key Pool with round-robin rotation, usage tracking, and automatic failover on 429/quota limits.
- Multi-Model fallback across NVIDIA NIM and OpenAI-compatible models.
- Configurable base URL, exact model ID, timeout, and concurrency.
- Exponential backoff with jitter and Retry-After header support.
- Classified exceptions (missing credentials, invalid keys, unavailable models, rate limits, quotas, network).
- Structured output validation with Pydantic typed schemas.
- Bounded repair attempt for malformed JSON before visible failure.
- Model capability auto-detection with validated fallback.
- Per-job request and token budget enforcement with usage tracking.
- Prompt injection defense and security boundary framing.
- Connection testing with diagnostic metrics across all keys and models.
"""

import asyncio
import email.utils
import json
import random
import re
import time
from typing import Dict, Any, List, Optional, Tuple, Type, TypeVar
import httpx
from openai import AsyncOpenAI, APIStatusError, APIConnectionError, APITimeoutError
from pydantic import BaseModel, ValidationError

from backend.config import config
from backend.logging_utils import logger, redact_secrets
from backend.llm.exceptions import (
    AIClientError,
    MissingCredentialsError,
    InvalidCredentialsError,
    ModelUnavailableError,
    RateLimitError,
    QuotaExhaustedError,
    NetworkFailureError,
    BudgetExceededError,
    SchemaValidationError,
    MalformedOutputError,
)
from backend.llm.schemas import UsageMetrics, LLMResult
from backend.llm.security import SECURITY_INSTRUCTIONS, frame_untrusted_content
from backend.llm.budget import job_budget_tracker

T = TypeVar("T", bound=BaseModel)

class AIClient:
    def __init__(self):
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._semaphore_limit: int = 0
        self._supports_json_mode: Optional[bool] = None
        self._key_index: int = 0
        self._key_throttled_until: Dict[str, float] = {}

    def _get_semaphore(self) -> asyncio.Semaphore:
        """Lazily initializes or updates concurrency semaphore."""
        limit = max(1, config.llm_max_concurrency)
        if self._semaphore is None or self._semaphore_limit != limit:
            self._semaphore = asyncio.Semaphore(limit)
            self._semaphore_limit = limit
        return self._semaphore

    def is_configured(self) -> bool:
        """Returns True if local endpoint or valid remote credentials exist."""
        base_url = config.llm_base_url
        has_key = bool(config.get_api_keys() or config.llm_api_key)
        has_model = bool(config.llm_model)
        is_local = "localhost" in base_url or "127.0.0.1" in base_url
        return (has_key or is_local) and has_model

    def _get_next_api_key(self) -> str:
        """
        Returns the next available healthy API key from the pool in round-robin fashion.
        Skips temporarily throttled keys if other healthy keys are available.
        """
        keys = config.get_api_keys()
        if not keys:
            return "dummy-key-for-local-endpoint"

        now = time.time()
        # Find healthy keys
        healthy_keys = [k for k in keys if self._key_throttled_until.get(k, 0) <= now]
        if not healthy_keys:
            # If all are throttled, find the key that expires earliest
            healthy_keys = [min(keys, key=lambda k: self._key_throttled_until.get(k, 0))]

        self._key_index = (self._key_index + 1) % len(healthy_keys)
        return healthy_keys[self._key_index]

    def _mark_key_throttled(self, key: str, duration_sec: float = 60.0):
        """Temporarily marks an API key as throttled so other keys in the pool take precedence."""
        self._key_throttled_until[key] = time.time() + duration_sec
        logger.warning(f"[AI Client] API key {key[:4]}...{key[-4:] if len(key)>8 else '***'} throttled for {duration_sec}s. Switching to alternative key.")

    def get_client(self, api_key: Optional[str] = None) -> AsyncOpenAI:
        """
        Instantiates AsyncOpenAI client with specified or next pooled API key.
        """
        base_url = config.llm_base_url
        key_to_use = api_key or self._get_next_api_key()
        self._last_used_key = key_to_use
        timeout_seconds = max(5.0, config.llm_timeout)

        # Configure custom httpx client with connection limits and timeout
        http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=10.0),
            limits=httpx.Limits(max_keepalive_connections=15, max_connections=30)
        )

        client = AsyncOpenAI(
            base_url=base_url,
            api_key=key_to_use,
            http_client=http_client
        )
        return client

    def _parse_retry_after(self, error: Exception) -> Optional[float]:
        """Extracts Retry-After header seconds from response if available."""
        try:
            if hasattr(error, "response") and error.response is not None:
                headers = error.response.headers
                retry_header = headers.get("retry-after") or headers.get("Retry-After")
                if retry_header:
                    if retry_header.isdigit():
                        return float(retry_header)
                    date_tuple = email.utils.parsedate(retry_header)
                    if date_tuple:
                        target_time = time.mktime(date_tuple)
                        diff = target_time - time.time()
                        return max(1.0, diff)
        except Exception:
            pass
        return None

    def _classify_error(self, error: Exception) -> AIClientError:
        """Maps HTTP/OpenAI exceptions to classified domain errors."""
        err_text = str(error).lower()

        if isinstance(error, APIStatusError):
            status = error.status_code
            if status in (401, 403):
                return InvalidCredentialsError(
                    f"Authentication failed ({status}): Invalid API key or unauthorized access to {config.llm_base_url}."
                )
            if status == 404:
                return ModelUnavailableError(
                    model_name=config.llm_model,
                    message=f"Model '{config.llm_model}' not found in provider catalog (HTTP 404). Please verify exact model ID in your provider account."
                )
            if status == 429:
                if any(q in err_text for q in ["quota", "insufficient", "billing", "credit", "exceeded your current quota"]):
                    return QuotaExhaustedError(
                        f"AI provider quota or billing credits exhausted: {redact_secrets(str(error))}"
                    )
                retry_after = self._parse_retry_after(error)
                return RateLimitError(
                    f"AI provider rate limit reached: {redact_secrets(str(error))}",
                    retry_after=retry_after
                )
            if status in (500, 502, 503, 504):
                return NetworkFailureError(
                    f"AI provider service temporarily unavailable (HTTP {status}): {redact_secrets(str(error))}"
                )

        if isinstance(error, (APIConnectionError, APITimeoutError, httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout)):
            return NetworkFailureError(
                f"Network connection failure or timeout communicating with AI endpoint ({config.llm_base_url}): {redact_secrets(str(error))}"
            )

        if isinstance(error, AIClientError):
            return error

        return AIClientError(redact_secrets(str(error)))

    async def _execute_with_retry(
        self,
        api_call_coroutine_factory,
        job_id: Optional[int] = None
    ) -> Tuple[Any, float]:
        """
        Executes an AI API call with:
        - Multi-key rotation and failover
        - Job budget verification
        - Concurrency semaphore throttling
        - Bounded exponential backoff and jitter
        - Retry-After header respect
        """
        if not self.is_configured():
            raise MissingCredentialsError(
                "AI provider is not configured. Please supply a valid LLM_API_KEY and LLM_MODEL in settings."
            )

        # Check budget before executing
        job_budget_tracker.check_budget(job_id)

        all_keys = config.get_api_keys()
        max_retries = max(len(all_keys), config.llm_max_retries)
        base_delay = 1.0
        max_delay = 15.0

        last_error: Optional[AIClientError] = None
        semaphore = self._get_semaphore()
        async with semaphore:
            for attempt in range(max_retries + 1):
                start_time = time.time()
                client_res = self.get_client()
                if isinstance(client_res, tuple):
                    client, active_key = client_res
                else:
                    client = client_res
                    active_key = getattr(self, "_last_used_key", getattr(client, "api_key", config.llm_api_key))

                try:
                    result = await api_call_coroutine_factory(client)
                    elapsed_ms = round((time.time() - start_time) * 1000, 2)
                    return result, elapsed_ms

                except Exception as raw_err:
                    elapsed_ms = round((time.time() - start_time) * 1000, 2)
                    classified_err = self._classify_error(raw_err)
                    last_error = classified_err

                    # If rate limited (429) or quota exhausted, mark this key and failover to next key in pool
                    if isinstance(classified_err, (RateLimitError, QuotaExhaustedError, InvalidCredentialsError)) and len(all_keys) > 1 and attempt < len(all_keys) - 1:
                        self._mark_key_throttled(active_key, duration_sec=60.0 if isinstance(classified_err, RateLimitError) else 300.0)
                        logger.info(f"[AI Client] Retrying immediately with alternative key from pool of {len(all_keys)} keys...")
                        continue

                    # Non-retryable errors (or all keys exhausted)
                    if isinstance(classified_err, (InvalidCredentialsError, ModelUnavailableError, QuotaExhaustedError, MissingCredentialsError, BudgetExceededError)):
                        logger.error(f"[AI Client] Non-retryable error: {classified_err.message}")
                        raise classified_err

                    # Check if last attempt
                    if attempt >= max_retries:
                        logger.error(f"[AI Client] All {max_retries} retry attempts exhausted: {classified_err.message}")
                        raise classified_err

                    # Compute backoff delay
                    if isinstance(classified_err, RateLimitError) and classified_err.retry_after:
                        backoff = min(classified_err.retry_after, max_delay)
                    else:
                        jitter = random.uniform(0.1, 0.5)
                        backoff = min(base_delay * (2 ** attempt) + jitter, max_delay)

                    logger.warning(
                        f"[AI Client] Attempt {attempt + 1}/{max_retries} failed ({classified_err.error_type}). "
                        f"Retrying in {backoff:.2f}s... Error: {classified_err.message}"
                    )
                    await asyncio.sleep(backoff)

        if last_error:
            raise last_error
        raise NetworkFailureError("Unexpected termination of retry loop.")

    def _extract_json_string(self, raw_text: str) -> str:
        """Strips markdown fences and extracts JSON content safely."""
        cleaned = raw_text.strip()

        # Handle ```json ... ``` or ``` ... ```
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]

        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]

        cleaned = cleaned.strip()

        # Regex fallback to find outermost JSON object or array
        match = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', cleaned)
        if match:
            cleaned = match.group(1)

        return cleaned.strip()

    async def generate_structured(
        self,
        schema: Type[T],
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 3500,
        job_id: Optional[int] = None
    ) -> LLMResult[T]:
        """
        Generates validated structured output matching the provided Pydantic schema.
        Handles provider capability check (JSON mode vs validated prompt extraction),
        token tracking, and a bounded repair attempt for malformed outputs.
        """
        full_system = f"{SECURITY_INSTRUCTIONS}\n\n{system_prompt}\n\nCRITICAL: Respond ONLY with a valid JSON object conforming to the required schema. Do not output text outside the JSON."

        async def call_provider(client: AsyncOpenAI):
            models_to_try = [config.llm_model] + [m for m in config.llm_fallback_models if m != config.llm_model]

            for idx, model_id in enumerate(models_to_try):
                kwargs: Dict[str, Any] = {
                    "model": model_id,
                    "messages": [
                        {"role": "system", "content": full_system},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": temperature,
                    "max_tokens": max_tokens
                }

                if self._supports_json_mode is not False:
                    try:
                        kwargs["response_format"] = {"type": "json_object"}
                        resp = await client.chat.completions.create(**kwargs)
                        self._supports_json_mode = True
                        return resp
                    except Exception as e:
                        err_msg = str(e).lower()
                        if "response_format" in err_msg or "json_object" in err_msg or "unsupported" in err_msg:
                            self._supports_json_mode = False
                            kwargs.pop("response_format", None)
                            return await client.chat.completions.create(**kwargs)
                        elif "not found" in err_msg or "404" in err_msg:
                            if idx < len(models_to_try) - 1:
                                logger.warning(f"[AI Client] Model {model_id} not available. Falling back to {models_to_try[idx+1]}...")
                                continue
                        raise e
                else:
                    try:
                        return await client.chat.completions.create(**kwargs)
                    except Exception as e:
                        err_msg = str(e).lower()
                        if ("not found" in err_msg or "404" in err_msg) and idx < len(models_to_try) - 1:
                            logger.warning(f"[AI Client] Model {model_id} not available. Falling back to {models_to_try[idx+1]}...")
                            continue
                        raise e

        response, latency_ms = await self._execute_with_retry(call_provider, job_id=job_id)
        raw_text = response.choices[0].message.content or ""
        usage = UsageMetrics.from_provider_response(getattr(response, "usage", None))
        job_budget_tracker.record_usage(job_id, usage)

        # First pass parse & validation
        json_str = self._extract_json_string(raw_text)
        try:
            parsed_dict = json.loads(json_str)
            validated_data = schema.model_validate(parsed_dict)
            return LLMResult[T](
                data=validated_data,
                raw_text=raw_text,
                usage=usage,
                model=config.llm_model,
                latency_ms=latency_ms,
                repaired=False,
                finish_reason=response.choices[0].finish_reason
            )
        except (json.JSONDecodeError, ValidationError) as parse_err:
            logger.warning(f"[AI Client] Structured output validation failed: {parse_err}. Attempting bounded repair...")

            # --- BOUNDED REPAIR ATTEMPT (1 Pass) ---
            repaired_result = await self._attempt_repair(
                schema=schema,
                invalid_output=raw_text,
                error_details=str(parse_err),
                job_id=job_id
            )

            if repaired_result is not None:
                total_prompt = usage.prompt_tokens + repaired_result.usage.prompt_tokens
                total_comp = usage.completion_tokens + repaired_result.usage.completion_tokens
                combined_usage = UsageMetrics(
                    prompt_tokens=total_prompt,
                    completion_tokens=total_comp,
                    total_tokens=total_prompt + total_comp
                )
                return LLMResult[T](
                    data=repaired_result.data,
                    raw_text=repaired_result.raw_text,
                    usage=combined_usage,
                    model=config.llm_model,
                    latency_ms=latency_ms + repaired_result.latency_ms,
                    repaired=True
                )

            logger.error(f"[AI Client] Structured output repair failed for model {config.llm_model}.")
            raise SchemaValidationError(
                message=f"Model output failed schema validation for {schema.__name__} after repair attempt: {str(parse_err)}",
                raw_output=raw_text,
                validation_errors=str(parse_err)
            )

    async def _attempt_repair(
        self,
        schema: Type[T],
        invalid_output: str,
        error_details: str,
        job_id: Optional[int] = None
    ) -> Optional[LLMResult[T]]:
        """Executes a single bounded repair attempt to fix syntax/schema mismatches."""
        schema_json = json.dumps(schema.model_json_schema(), indent=2)
        repair_system = f"""You are a precise JSON repair agent.
The previous output failed validation against the required JSON schema.
Repair the syntax or field formatting so it strictly satisfies the schema.
Do NOT fabricate new information or alter facts from the original output.
Respond ONLY with the corrected, valid JSON object."""

        repair_user = f"""Target Schema:
```json
{schema_json}
```

Validation Error:
{error_details}

Original Invalid Output:
```
{invalid_output[:4000]}
```

Provide the corrected JSON:"""

        async def call_repair(client: AsyncOpenAI):
            return await client.chat.completions.create(
                model=config.llm_model,
                messages=[
                    {"role": "system", "content": repair_system},
                    {"role": "user", "content": repair_user}
                ],
                temperature=0.0,
                max_tokens=3000
            )

        try:
            resp, elapsed_ms = await self._execute_with_retry(call_repair, job_id=job_id)
            repair_raw = resp.choices[0].message.content or ""
            repair_usage = UsageMetrics.from_provider_response(getattr(resp, "usage", None))
            job_budget_tracker.record_usage(job_id, repair_usage)

            repaired_str = self._extract_json_string(repair_raw)
            repaired_dict = json.loads(repaired_str)
            validated = schema.model_validate(repaired_dict)

            logger.info(f"[AI Client] Bounded repair successful for schema {schema.__name__}!")
            return LLMResult[T](
                data=validated,
                raw_text=repair_raw,
                usage=repair_usage,
                model=config.llm_model,
                latency_ms=elapsed_ms,
                repaired=True
            )
        except Exception as repair_err:
            logger.warning(f"[AI Client] Bounded repair attempt failed: {redact_secrets(str(repair_err))}")
            return None

    async def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 1500,
        job_id: Optional[int] = None
    ) -> LLMResult[str]:
        """Generates unstructured or formatted text."""
        full_system = f"{SECURITY_INSTRUCTIONS}\n\n{system_prompt}"

        async def call_provider(client: AsyncOpenAI):
            return await client.chat.completions.create(
                model=config.llm_model,
                messages=[
                    {"role": "system", "content": full_system},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens
            )

        response, latency_ms = await self._execute_with_retry(call_provider, job_id=job_id)
        raw_text = response.choices[0].message.content or ""
        usage = UsageMetrics.from_provider_response(getattr(response, "usage", None))
        job_budget_tracker.record_usage(job_id, usage)

        return LLMResult[str](
            data=raw_text.strip(),
            raw_text=raw_text,
            usage=usage,
            model=config.llm_model,
            latency_ms=latency_ms,
            repaired=False,
            finish_reason=response.choices[0].finish_reason
        )

    async def test_connection(self) -> Dict[str, Any]:
        """Tests connection to the configured AI provider endpoint with primary key."""
        if not self.is_configured():
            missing_err = MissingCredentialsError()
            return {
                "success": False,
                "error_type": "missing_credentials",
                "message": "AI credentials are not configured. Please configure NVIDIA_API_KEYS, LLM_BASE_URL, and LLM_MODEL.",
                "endpoint": config.llm_base_url,
                "model": config.llm_model or "(Not set)",
                "setup_instructions": missing_err.details["setup_instructions"]
            }

        start_time = time.time()
        try:
            client_res = self.get_client()
            if isinstance(client_res, tuple):
                client, key_used = client_res
            else:
                client = client_res
                key_used = getattr(self, "_last_used_key", getattr(client, "api_key", config.llm_api_key))
            response = await client.chat.completions.create(
                model=config.llm_model,
                messages=[
                    {"role": "system", "content": "You are a test assistant. Respond strictly with 'Connection verified.'"},
                    {"role": "user", "content": "Ping"}
                ],
                max_tokens=25,
                temperature=0.0
            )
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            reply = (response.choices[0].message.content or "").strip()
            usage = UsageMetrics.from_provider_response(getattr(response, "usage", None))

            masked_key = f"{key_used[:4]}...{key_used[-4:]}" if len(key_used) > 8 else "********"

            return {
                "success": True,
                "message": f"Successfully verified connection to {config.llm_model} at {config.llm_base_url} (Key: {masked_key})",
                "latency_ms": elapsed_ms,
                "endpoint": config.llm_base_url,
                "model": config.llm_model,
                "active_key_masked": masked_key,
                "total_keys_in_pool": len(config.get_api_keys()),
                "sample_reply": reply,
                "token_usage": usage.model_dump(),
                "capabilities": {
                    "supports_json_mode": self._supports_json_mode if self._supports_json_mode is not None else "Supported / Dynamic Fallback",
                    "max_concurrency": config.llm_max_concurrency,
                    "timeout_seconds": config.llm_timeout
                }
            }

        except Exception as e:
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            classified = self._classify_error(e)
            logger.warning(f"[AI Client] Connection test failed: {classified.message}")

            result = classified.to_dict()
            result.update({
                "latency_ms": elapsed_ms,
                "endpoint": config.llm_base_url,
                "model": config.llm_model or "(Not set)",
                "total_keys_in_pool": len(config.get_api_keys())
            })
            return result

    async def test_all_keys(self) -> Dict[str, Any]:
        """Tests every configured API key individually against the endpoint and returns per-key diagnostics."""
        keys = config.get_api_keys()
        if not keys:
            return {
                "total_keys": 0,
                "healthy_keys": 0,
                "results": []
            }

        results = []
        for idx, key in enumerate(keys):
            masked = f"{key[:4]}...{key[-4:]}" if len(key) > 8 else f"Key #{idx+1}"
            start_t = time.time()
            try:
                client_res = self.get_client(api_key=key)
                client = client_res[0] if isinstance(client_res, tuple) else client_res
                response = await client.chat.completions.create(
                    model=config.llm_model,
                    messages=[
                        {"role": "system", "content": "Respond strictly with 'OK'"},
                        {"role": "user", "content": "ping"}
                    ],
                    max_tokens=10,
                    temperature=0.0
                )
                lat = round((time.time() - start_t) * 1000, 2)
                results.append({
                    "key_index": idx + 1,
                    "masked_key": masked,
                    "success": True,
                    "latency_ms": lat,
                    "status": "Active & Healthy",
                    "model": config.llm_model
                })
            except Exception as err:
                lat = round((time.time() - start_t) * 1000, 2)
                classified = self._classify_error(err)
                results.append({
                    "key_index": idx + 1,
                    "masked_key": masked,
                    "success": False,
                    "latency_ms": lat,
                    "status": f"Failed: {classified.error_type}",
                    "error_message": classified.message
                })

        healthy_cnt = sum(1 for r in results if r["success"])
        return {
            "total_keys": len(keys),
            "healthy_keys": healthy_cnt,
            "results": results
        }

ai_client = AIClient()
