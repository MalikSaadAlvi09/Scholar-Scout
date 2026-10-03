"""
Factory for Email Providers.
Instantiates the correct provider instance based on account configuration.
"""

from typing import Dict, Any
from backend.emails.providers.base import BaseEmailProvider
from backend.emails.providers.mock_sandbox import MockSandboxEmailProvider
from backend.emails.providers.gmail import GmailOAuthProvider
from backend.emails.providers.outlook import OutlookOAuthProvider
from backend.emails.providers.smtp import CustomSMTPProvider

def get_email_provider(account_config: Dict[str, Any]) -> BaseEmailProvider:
    """Instantiates the appropriate email provider based on provider_type."""
    provider_type = (account_config.get("provider_type") or "mock_sandbox").lower().strip()

    if provider_type == "gmail_oauth":
        return GmailOAuthProvider(account_config)
    elif provider_type == "outlook_oauth":
        return OutlookOAuthProvider(account_config)
    elif provider_type == "custom_smtp":
        return CustomSMTPProvider(account_config)
    else:
        # Default is safe offline Mock Sandbox
        return MockSandboxEmailProvider(account_config)
