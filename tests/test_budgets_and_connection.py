"""
Tests for AI Job Budgets, Token Tracking, and Connection Testing with Setup Instructions.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from backend.config import config
from backend.llm.client import AIClient
from backend.llm.budget import JobBudgetTracker
from backend.llm.schemas import UsageMetrics
from backend.llm.exceptions import BudgetExceededError, MissingCredentialsError

def test_job_budget_tracker_request_limit():
    """Verify JobBudgetTracker raises BudgetExceededError when request count exceeds budget."""
    tracker = JobBudgetTracker()
    config.job_max_llm_requests = 3
    config.job_max_llm_tokens = 50000

    job_id = 99

    # Record 3 requests
    tracker.record_usage(job_id, UsageMetrics(prompt_tokens=100, completion_tokens=50, total_tokens=150))
    tracker.record_usage(job_id, UsageMetrics(prompt_tokens=100, completion_tokens=50, total_tokens=150))
    tracker.record_usage(job_id, UsageMetrics(prompt_tokens=100, completion_tokens=50, total_tokens=150))

    usage = tracker.get_job_usage(job_id)
    assert usage["requests"] == 3
    assert usage["total_tokens"] == 450

    # 4th request check should raise BudgetExceededError
    with pytest.raises(BudgetExceededError) as exc:
        tracker.check_budget(job_id)
    assert "exceeded request budget" in exc.value.message

    # Reset
    tracker.reset_job(job_id)
    assert tracker.get_job_usage(job_id)["requests"] == 0

def test_job_budget_tracker_token_limit():
    """Verify JobBudgetTracker raises BudgetExceededError when tokens exceed limit."""
    tracker = JobBudgetTracker()
    config.job_max_llm_requests = 100
    config.job_max_llm_tokens = 1000

    job_id = 101

    # Record 900 tokens
    tracker.record_usage(job_id, UsageMetrics(prompt_tokens=600, completion_tokens=300, total_tokens=900))

    # Next call estimating 200 tokens -> 900 + 200 = 1100 > 1000 -> raises
    with pytest.raises(BudgetExceededError) as exc:
        tracker.check_budget(job_id, estimated_tokens=200)
    assert "exceeded token budget" in exc.value.message

def test_connection_test_missing_credentials_shows_setup_instructions():
    """Verify that unconfigured credentials return setup instructions without fake success."""
    async def run_test():
        client = AIClient()
        config.llm_api_key = ""
        config.llm_base_url = "https://integrate.api.nvidia.com/v1"
        config.llm_model = ""

        result = await client.test_connection()
        assert result["success"] is False
        assert result["error_type"] == "missing_credentials"
        assert "setup_instructions" in result
        assert "nvidia_nim" in result["setup_instructions"]
        assert "build.nvidia.com" in result["setup_instructions"]["nvidia_nim"]["step1"]

    asyncio.run(run_test())

def test_connection_test_successful_ping():
    """Verify that valid connection test returns latency, token usage, and verified status."""
    async def run_test():
        client = AIClient()
        config.llm_api_key = "nvapi-test-key-12345"
        config.llm_base_url = "https://integrate.api.nvidia.com/v1"
        config.llm_model = "nvidia/llama-3.1-nemotron-70b-instruct"

        choice = MagicMock()
        choice.message.content = "Connection verified."
        usage = MagicMock()
        usage.prompt_tokens = 12
        usage.completion_tokens = 3
        usage.total_tokens = 15

        mock_resp = MagicMock()
        mock_resp.choices = [choice]
        mock_resp.usage = usage

        with patch.object(client, "get_client") as mock_get:
            mock_openai = MagicMock()
            mock_openai.chat.completions.create = AsyncMock(return_value=mock_resp)
            mock_get.return_value = mock_openai

            result = await client.test_connection()
            assert result["success"] is True
            assert "Successfully verified connection" in result["message"]
            assert result["latency_ms"] >= 0
            assert result["model"] == "nvidia/llama-3.1-nemotron-70b-instruct"
            assert result["sample_reply"] == "Connection verified."
            assert result["token_usage"]["total_tokens"] == 15

    asyncio.run(run_test())
