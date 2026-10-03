"""
Classified Exceptions for ScholarScout AI Engine.
Provides distinct error categories for missing credentials, invalid keys,
unavailable models, rate limits, quota exhaustion, network issues, and schema validation.
"""

from typing import Optional, Dict, Any

class AIClientError(Exception):
    """Base class for all AI client exceptions."""
    def __init__(self, message: str, error_type: str = "ai_error", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.error_type = error_type
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": False,
            "error_type": self.error_type,
            "message": self.message,
            "details": self.details
        }

class MissingCredentialsError(AIClientError):
    """Raised when required API key or credentials are not configured."""
    def __init__(self, message: str = "LLM credentials are not configured.", setup_instructions: Optional[Dict[str, Any]] = None):
        instructions = setup_instructions or {
            "title": "LLM Provider Setup Instructions",
            "nvidia_nim": {
                "step1": "Visit https://build.nvidia.com and create a free account or sign in.",
                "step2": "Navigate to the API catalog, select your desired model (e.g. nvidia/llama-3.1-nemotron-70b-instruct or meta/llama-3.1-8b-instruct), and copy the exact Model ID.",
                "step3": "Generate a personal API key from your NVIDIA account.",
                "step4": "Configure LLM_API_KEY, LLM_BASE_URL (https://integrate.api.nvidia.com/v1), and LLM_MODEL in Settings or .env file."
            },
            "openai_compatible": {
                "step1": "Set LLM_BASE_URL to your OpenAI-compatible endpoint (e.g., https://api.openai.com/v1 or http://localhost:11434/v1 for Ollama).",
                "step2": "Set LLM_API_KEY and LLM_MODEL matching your provider's available model catalog."
            }
        }
        super().__init__(message, error_type="missing_credentials", details={"setup_instructions": instructions})

class InvalidCredentialsError(AIClientError):
    """Raised when API key is invalid, rejected (401/403), or unauthorized."""
    def __init__(self, message: str = "Invalid API key or unauthorized access to AI provider endpoint."):
        super().__init__(message, error_type="invalid_credentials")

class ModelUnavailableError(AIClientError):
    """Raised when the specified model ID does not exist in provider catalog (404/model_not_found)."""
    def __init__(self, model_name: str, message: Optional[str] = None):
        msg = message or f"The requested model '{model_name}' was not found in your provider account catalog. Please ensure you supply the exact model ID available in your account."
        super().__init__(msg, error_type="model_unavailable", details={"model": model_name})

class RateLimitError(AIClientError):
    """Raised when provider rate limit (RPM/TPM) is reached."""
    def __init__(self, message: str = "Provider rate limit reached.", retry_after: Optional[float] = None):
        super().__init__(message, error_type="rate_limit_exceeded", details={"retry_after_seconds": retry_after})
        self.retry_after = retry_after

class QuotaExhaustedError(AIClientError):
    """Raised when account billing quota, credits, or monthly token allowances are exhausted."""
    def __init__(self, message: str = "Provider account quota or credits exhausted."):
        super().__init__(message, error_type="quota_exhausted")

class NetworkFailureError(AIClientError):
    """Raised when network connection fails, times out, or DNS resolution fails."""
    def __init__(self, message: str = "Network connection to AI provider failed or timed out."):
        super().__init__(message, error_type="network_failure")

class BudgetExceededError(AIClientError):
    """Raised when a research job exceeds its configured request or token budget."""
    def __init__(self, message: str = "Job AI budget exceeded.", job_id: Optional[int] = None, current_usage: Optional[Dict[str, Any]] = None):
        super().__init__(message, error_type="budget_exceeded", details={"job_id": job_id, "usage": current_usage})

class SchemaValidationError(AIClientError):
    """Raised when structured LLM output does not match the required typed schema after bounded repair."""
    def __init__(self, message: str = "Structured output validation failed after repair attempts.", raw_output: Optional[str] = None, validation_errors: Optional[str] = None):
        super().__init__(message, error_type="schema_validation_error", details={"raw_output": raw_output, "validation_errors": validation_errors})

class MalformedOutputError(AIClientError):
    """Raised when LLM returns unparseable or completely malformed text."""
    def __init__(self, message: str = "Model returned malformed or unparseable output.", raw_output: Optional[str] = None):
        super().__init__(message, error_type="malformed_output", details={"raw_output": raw_output})
