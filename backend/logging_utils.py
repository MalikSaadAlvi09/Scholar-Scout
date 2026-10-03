"""
Structured Logging Utility with Secrets Redaction.
Ensures API keys, tokens, and sensitive credentials never leak into stdout, log files, or database logs.
"""

import logging
import re
import sys
from typing import Optional

# Common secret regex patterns (OpenAI, NVIDIA NIM, generic Bearer tokens, passwords, keys)
SECRET_PATTERNS = [
    re.compile(r'(?i)(nvapi-[a-zA-Z0-9_-]{20,})'),
    re.compile(r'(?i)(sk-[a-zA-Z0-9_-]{20,})'),
    re.compile(r'(?i)(bearer\s+)([a-zA-Z0-9_\-\.]{15,})'),
    re.compile(r'(?i)(api[_-]?key["\']?\s*[:=]\s*["\']?)([^"\'\s,;]+)'),
    re.compile(r'(?i)(password["\']?\s*[:=]\s*["\']?)([^"\'\s,;]+)'),
    re.compile(r'(?i)(secret["\']?\s*[:=]\s*["\']?)([^"\'\s,;]+)'),
    re.compile(r'(?i)(authorization["\']?\s*[:=]\s*["\']?Bearer\s+)([^"\'\s,;]+)'),
]

def redact_secrets(text: str) -> str:
    """Redacts known token/key formats and patterns from a string."""
    if not text or not isinstance(text, str):
        return text

    sanitized = text
    for pattern in SECRET_PATTERNS:
        # Check if regex has capture groups
        if pattern.groups == 1:
            sanitized = pattern.sub(r'***REDACTED_SECRET***', sanitized)
        elif pattern.groups == 2:
            sanitized = pattern.sub(r'\1***REDACTED***', sanitized)
        else:
            sanitized = pattern.sub(r'***REDACTED***', sanitized)

    return sanitized

class RedactingFormatter(logging.Formatter):
    """Custom logging formatter that strips sensitive credentials."""
    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        return redact_secrets(original)

def setup_logger(name: str = "ScholarScout", level: int = logging.INFO) -> logging.Logger:
    """Creates and configures a redacting logger."""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        formatter = RedactingFormatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.propagate = False

    return logger

logger = setup_logger()
