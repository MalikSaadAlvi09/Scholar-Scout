"""
Logging and Secrets Redaction Tests for ScholarScout.
Ensures API keys, tokens, and authorization credentials are scrubbed from logs.
"""

from backend.logging_utils import redact_secrets

def test_redact_nvidia_nim_key():
    """Verify NVIDIA NIM API keys are redacted."""
    raw_log = "Sending request with key: nvapi-abcdef1234567890abcdef123456"
    sanitized = redact_secrets(raw_log)
    assert "nvapi-" not in sanitized
    assert "***REDACTED" in sanitized

def test_redact_openai_key():
    """Verify OpenAI keys are redacted."""
    raw_log = "Error connecting with auth: sk-abcdef1234567890abcdef123456"
    sanitized = redact_secrets(raw_log)
    assert "sk-" not in sanitized
    assert "***REDACTED" in sanitized

def test_redact_bearer_token():
    """Verify Bearer tokens are scrubbed."""
    raw_log = "Authorization header: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    sanitized = redact_secrets(raw_log)
    assert "eyJhbG" not in sanitized
    assert "***REDACTED" in sanitized
