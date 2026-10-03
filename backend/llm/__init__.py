"""
LLM Package for ScholarScout.
Exports AIClient, NemotronClient, Pydantic schemas, exceptions, security, and budget tracker.
"""

from backend.llm.client import ai_client, AIClient
from backend.llm.nemotron_client import nemotron_client, NemotronClient
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
    MalformedOutputError
)
from backend.llm.schemas import (
    UsageMetrics,
    LLMResult,
    ScholarshipItem,
    ScholarshipListResponse,
    ProfessorItem,
    ProfessorListResponse,
    EmailDraftResponse
)
from backend.llm.security import SECURITY_INSTRUCTIONS, sanitize_untrusted_text, frame_untrusted_content
from backend.llm.budget import job_budget_tracker, JobBudgetTracker

__all__ = [
    "ai_client",
    "AIClient",
    "nemotron_client",
    "NemotronClient",
    "AIClientError",
    "MissingCredentialsError",
    "InvalidCredentialsError",
    "ModelUnavailableError",
    "RateLimitError",
    "QuotaExhaustedError",
    "NetworkFailureError",
    "BudgetExceededError",
    "SchemaValidationError",
    "MalformedOutputError",
    "UsageMetrics",
    "LLMResult",
    "ScholarshipItem",
    "ScholarshipListResponse",
    "ProfessorItem",
    "ProfessorListResponse",
    "EmailDraftResponse",
    "SECURITY_INSTRUCTIONS",
    "sanitize_untrusted_text",
    "frame_untrusted_content",
    "job_budget_tracker",
    "JobBudgetTracker"
]
