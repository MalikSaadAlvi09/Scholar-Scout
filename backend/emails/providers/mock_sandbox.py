"""
Mock Sandbox Email Provider for ScholarScout.
Ensures 100% safe, offline development and automated testing.
Never sends real emails to professors while supporting full simulation of
provider acceptance, ambiguous network timeouts, reconciliation, and reply synchronization.
"""

import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from backend.emails.providers.base import (
    BaseEmailProvider,
    ProviderSendResult,
    ProviderReconciliationResult
)
from backend.logging_utils import logger

class MockSandboxEmailProvider(BaseEmailProvider):
    """
    Mock Email Provider for local development, UI testing, and pytest test suites.
    Simulates real provider behaviors including provider-accepted states, timeouts, and replies.
    """

    # In-memory sent log for reconciliation tests
    _SENT_STORE: Dict[str, Dict[str, Any]] = {}
    _SIMULATED_REPLIES: List[Dict[str, Any]] = []

    def __init__(self, account_config: Dict[str, Any]):
        super().__init__(account_config)
        self.simulation_mode = self.credentials.get("simulation_mode", "normal") # normal, simulate_timeout, simulate_failure

    def send_email(
        self,
        recipient: str,
        subject: str,
        body_text: str,
        attachments: Optional[List[Dict[str, Any]]] = None,
        custom_headers: Optional[Dict[str, str]] = None
    ) -> ProviderSendResult:
        """Simulates sending an email via sandbox."""
        logger.info(f"[MockSandbox] Intercepted send to '{recipient}' with subject '{subject}'")

        # 1. Simulate Ambiguous Timeout scenario
        if self.simulation_mode == "simulate_timeout" or "SIMULATE_TIMEOUT" in subject:
            # Note: Do not record in sent store immediately to simulate uncertain flight
            return ProviderSendResult(
                success=False,
                status="uncertain",
                is_ambiguous_timeout=True,
                reconciliation_needed=True,
                error_message="HTTP connection timed out while awaiting provider gateway response. Message dispatch state is uncertain.",
                raw_response={"simulation": "ambiguous_timeout"}
            )

        # 2. Simulate Provider Failure scenario
        if self.simulation_mode == "simulate_failure" or "SIMULATE_FAIL" in subject:
            return ProviderSendResult(
                success=False,
                status="failed",
                error_message="Simulated provider rejection: Recipient mailbox quota exceeded or policy restriction.",
                raw_response={"simulation": "provider_rejection"}
            )

        # 3. Standard Normal Success
        msg_id = f"sandbox_msg_{uuid.uuid4().hex[:12]}"
        now_iso = datetime.now(timezone.utc).isoformat()
        
        # Record in sent store for reconciliation checks
        record_key = f"{recipient.lower()}:{subject.strip().lower()}"
        MockSandboxEmailProvider._SENT_STORE[record_key] = {
            "provider_message_id": msg_id,
            "recipient": recipient,
            "subject": subject,
            "body_text": body_text,
            "sent_at": now_iso
        }

        return ProviderSendResult(
            success=True,
            status="provider-accepted",
            provider_message_id=msg_id,
            raw_response={
                "provider": "MockSandbox",
                "simulated": True,
                "queued_at": now_iso,
                "provider_message_id": msg_id
            },
            delivery_note="[SANDBOX MODE] Mock provider accepted message. No real email was transmitted over external networks."
        )

    def reconcile_ambiguous_send(
        self,
        recipient: str,
        subject: str,
        attempted_after_iso: str,
        provider_message_id: Optional[str] = None
    ) -> ProviderReconciliationResult:
        """Queries the sandbox sent store to determine if a message was dispatched."""
        record_key = f"{recipient.lower()}:{subject.strip().lower()}"
        
        # Check if record exists
        if record_key in MockSandboxEmailProvider._SENT_STORE:
            rec = MockSandboxEmailProvider._SENT_STORE[record_key]
            return ProviderReconciliationResult(
                resolved=True,
                actually_sent=True,
                provider_message_id=rec["provider_message_id"],
                sent_timestamp=rec["sent_at"],
                details="Reconciliation query confirmed message was successfully accepted by provider gateway."
            )

        # In timeout simulation, user or test can trigger reconciliation resolution
        if "RECONCILED_SUCCESS" in subject:
            msg_id = f"sandbox_reconciled_{uuid.uuid4().hex[:8]}"
            now_iso = datetime.now(timezone.utc).isoformat()
            MockSandboxEmailProvider._SENT_STORE[record_key] = {
                "provider_message_id": msg_id,
                "recipient": recipient,
                "subject": subject,
                "sent_at": now_iso
            }
            return ProviderReconciliationResult(
                resolved=True,
                actually_sent=True,
                provider_message_id=msg_id,
                sent_timestamp=now_iso,
                details="Provider sent-log confirmed message was transmitted during initial request."
            )

        return ProviderReconciliationResult(
            resolved=True,
            actually_sent=False,
            details="Provider sent-log confirms message was NOT recorded or transmitted. Safe to re-enqueue."
        )

    def sync_replies(
        self,
        known_recipients: List[str],
        since_iso: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Returns simulated incoming replies matching known recipient email addresses."""
        matching_replies = []
        recipients_lower = {r.lower() for r in known_recipients}

        for reply in MockSandboxEmailProvider._SIMULATED_REPLIES:
            if reply.get("sender_email", "").lower() in recipients_lower:
                matching_replies.append(reply)

        return matching_replies

    @classmethod
    def add_simulated_reply(cls, sender_email: str, subject: str, snippet: str, is_opt_out: bool = False):
        """Helper to inject a simulated reply for testing follow-up halting."""
        cls._SIMULATED_REPLIES.append({
            "sender_email": sender_email,
            "subject": subject,
            "snippet": snippet,
            "provider_message_id": f"sandbox_reply_{uuid.uuid4().hex[:8]}",
            "provider_thread_id": f"sandbox_thread_{uuid.uuid4().hex[:8]}",
            "is_opt_out": is_opt_out,
            "received_at": datetime.now(timezone.utc).isoformat()
        })

    def validate_connection(self) -> Dict[str, Any]:
        """Sandbox is always healthy and offline."""
        return {
            "valid": True,
            "account_name": self.account_name,
            "email_address": self.email_address or "sandbox@scholarscout.local",
            "provider_type": "mock_sandbox",
            "message": "Mock Sandbox provider is active and ready for safe offline testing."
        }
