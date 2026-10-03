"""
Abstract Base Classes and Data Structures for Email Providers.
Defines strict contracts for pluggable email backends (Mock Sandbox, Gmail OAuth, Outlook OAuth, SMTP).
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

class ProviderSendResult(BaseModel):
    """Result of an outbound email dispatch attempt."""
    success: bool
    status: str = Field(description="provider-accepted, failed, uncertain")
    provider_message_id: Optional[str] = None
    error_message: Optional[str] = None
    is_ambiguous_timeout: bool = False
    reconciliation_needed: bool = False
    raw_response: Dict[str, Any] = Field(default_factory=dict)
    delivery_note: str = Field(
        default="Provider accepted message for transmission. Note: Provider acceptance does not guarantee delivery to recipient inbox."
    )

class ProviderReconciliationResult(BaseModel):
    """Result of querying provider to resolve ambiguous timeouts."""
    resolved: bool
    actually_sent: bool
    provider_message_id: Optional[str] = None
    sent_timestamp: Optional[str] = None
    details: str = ""

class BaseEmailProvider(ABC):
    """Abstract interface for all ScholarScout email sending providers."""

    def __init__(self, account_config: Dict[str, Any]):
        self.account_config = account_config
        self.account_id = account_config.get("id")
        self.account_name = account_config.get("name", "Unknown Account")
        self.email_address = account_config.get("email_address", "")
        self.credentials = account_config.get("credentials", {})
        if isinstance(self.credentials, str):
            import json
            try:
                self.credentials = json.loads(self.credentials)
            except Exception:
                self.credentials = {}

    @abstractmethod
    def send_email(
        self,
        recipient: str,
        subject: str,
        body_text: str,
        attachments: Optional[List[Dict[str, Any]]] = None,
        custom_headers: Optional[Dict[str, str]] = None
    ) -> ProviderSendResult:
        """
        Transmits an email message through the provider.
        Must handle network timeouts by setting is_ambiguous_timeout=True and status='uncertain'
        without blindly retrying.
        """
        pass

    @abstractmethod
    def reconcile_ambiguous_send(
        self,
        recipient: str,
        subject: str,
        attempted_after_iso: str,
        provider_message_id: Optional[str] = None
    ) -> ProviderReconciliationResult:
        """
        Queries provider sent-mail log/API to check if a timed-out message was actually dispatched.
        Prevents duplicate sends to faculty members.
        """
        pass

    @abstractmethod
    def sync_replies(
        self,
        known_recipients: List[str],
        since_iso: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Queries provider inbox for incoming replies from known professor email addresses.
        Returns list of reply dicts with sender, subject, snippet, timestamp, thread_id.
        """
        pass

    @abstractmethod
    def validate_connection(self) -> Dict[str, Any]:
        """Validates credentials and connection health."""
        pass

    def get_rate_limits(self) -> Dict[str, Any]:
        """Returns hourly limit, daily limit, and minimum inter-send delay in seconds."""
        return {
            "hourly_limit": self.account_config.get("hourly_limit", 20),
            "daily_limit": self.account_config.get("daily_limit", 100),
            "delay_between_sends_sec": self.account_config.get("delay_between_sends_sec", 15)
        }
