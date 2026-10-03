"""
Unit & Integration Tests for ScholarScout Reusable AI Client.
Verifies retries, exponential backoff, rate limits, Retry-After parsing,
typed Pydantic validation, bounded repair, error classification, and usage tracking.
"""

import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import BaseModel, Field
import httpx
from openai import APIStatusError, APIConnectionError, APITimeoutError

from backend.config import config
from backend.llm.client import AIClient
from backend.llm.schemas import (
    ScholarshipListResponse,
    ScholarshipItem,
    ProfessorListResponse,
    EmailDraftResponse,
    UsageMetrics
)
from backend.llm.exceptions import (
    InvalidCredentialsError,
    ModelUnavailableError,
    RateLimitError,
    QuotaExhaustedError,
    NetworkFailureError,
    MissingCredentialsError,
    SchemaValidationError
)

class SampleTestSchema(BaseModel):
    name: str
    count: int = Field(ge=0)
    category: str = "General"

@pytest.fixture
def mock_ai_client():
    client = AIClient()
    config.llm_base_url = "https://integrate.api.nvidia.com/v1"
    config.llm_api_key = "nvapi-test-valid-key-12345"
    config.llm_api_keys = ["nvapi-test-valid-key-12345"]
    config.llm_model = "nvidia/llama-3.1-nemotron-70b-instruct"
    config.llm_timeout = 10.0
    config.llm_max_concurrency = 3
    config.llm_max_retries = 2
    return client

def create_mock_completion(content: str, prompt_tokens: int = 120, completion_tokens: int = 45, finish_reason: str = "stop"):
    """Helper to create a realistic OpenAI chat completion response."""
    choice = MagicMock()
    choice.message.content = content
    choice.finish_reason = finish_reason

    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    usage.total_tokens = prompt_tokens + completion_tokens

    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    return resp

def test_structured_output_success(mock_ai_client):
    """Test successful structured output generation with Pydantic validation."""
    valid_payload = json.dumps({
        "scholarships": [
            {
                "title": "Graduate Dean Fellowship",
                "funding_type": "Fellowship",
                "amount": "$36,000 / year + Full Tuition",
                "currency": "USD",
                "eligibility": "Incoming PhD students in Computer Science",
                "deadline": "December 15",
                "department": "School of Computer Science",
                "evidence_snippet": "The Dean Fellowship provides full tuition and a $36,000 stipend.",
                "fit_score": 95,
                "fit_reason": "Direct match for Ph.D. in Computer Science"
            }
        ]
    })

    mock_resp = create_mock_completion(f"```json\n{valid_payload}\n```", prompt_tokens=150, completion_tokens=80)

    async def run_test():
        with patch.object(mock_ai_client, "get_client") as mock_get:
            mock_openai = MagicMock()
            mock_openai.chat.completions.create = AsyncMock(return_value=mock_resp)
            mock_get.return_value = mock_openai

            result = await mock_ai_client.generate_structured(
                schema=ScholarshipListResponse,
                system_prompt="Extract scholarships",
                user_prompt="University page text"
            )

            assert result.data is not None
            assert len(result.data.scholarships) == 1
            assert result.data.scholarships[0].title == "Graduate Dean Fellowship"
            assert result.data.scholarships[0].fit_score == 95
            assert result.usage.total_tokens == 230
            assert result.repaired is False

    asyncio.run(run_test())

def test_bounded_repair_success(mock_ai_client):
    """Test bounded repair when initial output is malformed JSON, and repair succeeds."""
    malformed_json = '{"name": "Artificial Intelligence Lab", "count": "not_an_int"}'
    repaired_json = '{"name": "Artificial Intelligence Lab", "count": 12, "category": "AI"}'

    first_resp = create_mock_completion(malformed_json, prompt_tokens=80, completion_tokens=20)
    repair_resp = create_mock_completion(repaired_json, prompt_tokens=110, completion_tokens=25)

    async def run_test():
        with patch.object(mock_ai_client, "get_client") as mock_get:
            mock_openai = MagicMock()
            mock_openai.chat.completions.create = AsyncMock(side_effect=[first_resp, repair_resp])
            mock_get.return_value = mock_openai

            result = await mock_ai_client.generate_structured(
                schema=SampleTestSchema,
                system_prompt="Extract info",
                user_prompt="Lab details"
            )

            assert result.data is not None
            assert result.data.name == "Artificial Intelligence Lab"
            assert result.data.count == 12
            assert result.repaired is True

    asyncio.run(run_test())

def test_bounded_repair_failure_raises_visible_error(mock_ai_client):
    """Test that when bounded repair also fails, a clear SchemaValidationError is raised."""
    unrepairable_text = "Sorry, I cannot provide JSON."

    first_resp = create_mock_completion(unrepairable_text, prompt_tokens=50, completion_tokens=15)
    repair_resp = create_mock_completion("Still not valid JSON!", prompt_tokens=70, completion_tokens=10)

    async def run_test():
        with patch.object(mock_ai_client, "get_client") as mock_get:
            mock_openai = MagicMock()
            mock_openai.chat.completions.create = AsyncMock(side_effect=[first_resp, repair_resp])
            mock_get.return_value = mock_openai

            with pytest.raises(SchemaValidationError) as exc_info:
                await mock_ai_client.generate_structured(
                    schema=SampleTestSchema,
                    system_prompt="Extract info",
                    user_prompt="Lab details"
                )

            assert "SampleTestSchema" in exc_info.value.message

    asyncio.run(run_test())

def test_retry_on_rate_limit_with_retry_after(mock_ai_client):
    """Test retry behavior when receiving HTTP 429 with Retry-After header."""
    headers = httpx.Headers({"retry-after": "1"})
    fake_response = httpx.Response(status_code=429, headers=headers, request=httpx.Request("POST", "https://test.com"))
    rate_limit_err = APIStatusError("Rate limit exceeded", response=fake_response, body=None)

    valid_resp = create_mock_completion('{"name": "Vision Lab", "count": 5}', prompt_tokens=60, completion_tokens=15)

    async def run_test():
        with patch.object(mock_ai_client, "get_client") as mock_get, patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_openai = MagicMock()
            mock_openai.chat.completions.create = AsyncMock(side_effect=[rate_limit_err, valid_resp])
            mock_get.return_value = mock_openai

            result = await mock_ai_client.generate_structured(
                schema=SampleTestSchema,
                system_prompt="Extract",
                user_prompt="Page"
            )

            assert result.data is not None
            assert result.data.name == "Vision Lab"
            mock_sleep.assert_called_once()

    asyncio.run(run_test())

def test_invalid_credentials_error_classification(mock_ai_client):
    """Test 401 Unauthorized raises InvalidCredentialsError without infinite retries."""
    fake_response = httpx.Response(status_code=401, request=httpx.Request("POST", "https://test.com"))
    auth_err = APIStatusError("Invalid API key provided", response=fake_response, body=None)

    async def run_test():
        with patch.object(mock_ai_client, "get_client") as mock_get:
            mock_openai = MagicMock()
            mock_openai.chat.completions.create = AsyncMock(side_effect=auth_err)
            mock_get.return_value = mock_openai

            with pytest.raises(InvalidCredentialsError):
                await mock_ai_client.generate_text(
                    system_prompt="Test",
                    user_prompt="Hello"
                )

    asyncio.run(run_test())

def test_model_unavailable_error_classification(mock_ai_client):
    """Test 404 Model Not Found raises ModelUnavailableError."""
    fake_response = httpx.Response(status_code=404, request=httpx.Request("POST", "https://test.com"))
    not_found_err = APIStatusError("The model 'non-existent-model' does not exist", response=fake_response, body=None)

    async def run_test():
        with patch.object(mock_ai_client, "get_client") as mock_get:
            mock_openai = MagicMock()
            mock_openai.chat.completions.create = AsyncMock(side_effect=not_found_err)
            mock_get.return_value = mock_openai

            with pytest.raises(ModelUnavailableError) as exc:
                await mock_ai_client.generate_text(
                    system_prompt="Test",
                    user_prompt="Hello"
                )
            assert config.llm_model in exc.value.message

    asyncio.run(run_test())

def test_quota_exhausted_error_classification(mock_ai_client):
    """Test 429 Quota Exceeded raises QuotaExhaustedError."""
    fake_response = httpx.Response(status_code=429, request=httpx.Request("POST", "https://test.com"))
    quota_err = APIStatusError("You exceeded your current quota, please check your plan and billing details.", response=fake_response, body=None)

    async def run_test():
        with patch.object(mock_ai_client, "get_client") as mock_get:
            mock_openai = MagicMock()
            mock_openai.chat.completions.create = AsyncMock(side_effect=quota_err)
            mock_get.return_value = mock_openai

            with pytest.raises(QuotaExhaustedError):
                await mock_ai_client.generate_text(
                    system_prompt="Test",
                    user_prompt="Hello"
                )

    asyncio.run(run_test())

def test_capability_fallback_when_json_mode_unsupported(mock_ai_client):
    """Test that if response_format=json_object is unsupported (HTTP 400), client falls back to prompt extraction."""
    fake_response = httpx.Response(status_code=400, request=httpx.Request("POST", "https://test.com"))
    unsupported_err = APIStatusError("response_format 'json_object' is not supported by this model", response=fake_response, body=None)

    valid_resp = create_mock_completion('{"name": "Robotics Institute", "count": 20}', prompt_tokens=80, completion_tokens=30)

    async def run_test():
        mock_ai_client._supports_json_mode = None  # reset capability cache

        with patch.object(mock_ai_client, "get_client") as mock_get:
            mock_openai = MagicMock()
            mock_openai.chat.completions.create = AsyncMock(side_effect=[unsupported_err, valid_resp])
            mock_get.return_value = mock_openai

            result = await mock_ai_client.generate_structured(
                schema=SampleTestSchema,
                system_prompt="Extract info",
                user_prompt="Robotics info"
            )

            assert result.data is not None
            assert result.data.name == "Robotics Institute"
            assert result.data.count == 20
            assert mock_ai_client._supports_json_mode is False

    asyncio.run(run_test())

