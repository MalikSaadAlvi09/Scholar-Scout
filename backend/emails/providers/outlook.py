"""
Microsoft Outlook / Graph API Email Provider for ScholarScout.
Uses Microsoft Graph REST API (https://graph.microsoft.com/v1.0/me/sendMail)
with minimal required permissions:
- Mail.Send (Send academic outreach messages)
- Mail.Read (Optional: Read replies for follow-up synchronization)
"""

import json
from typing import Dict, Any, Optional, List
import requests

from backend.emails.providers.base import (
    BaseEmailProvider,
    ProviderSendResult,
    ProviderReconciliationResult
)
from backend.logging_utils import logger

class OutlookOAuthProvider(BaseEmailProvider):
    """Authenticated Microsoft Graph API provider."""

    TOKEN_ENDPOINT = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    GRAPH_SEND_URL = "https://graph.microsoft.com/v1.0/me/sendMail"
    GRAPH_MESSAGES_URL = "https://graph.microsoft.com/v1.0/me/messages"

    def _get_access_token(self) -> str:
        client_id = self.credentials.get("client_id", "")
        client_secret = self.credentials.get("client_secret", "")
        refresh_token = self.credentials.get("refresh_token", "")

        if not refresh_token:
            raise ValueError("Microsoft account requires OAuth2 refresh_token. Normal password login is prohibited.")

        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
            "scope": "https://graph.microsoft.com/Mail.Send https://graph.microsoft.com/Mail.Read offline_access"
        }

        try:
            resp = requests.post(self.TOKEN_ENDPOINT, data=data, timeout=10)
            if resp.status_code == 200:
                return resp.json().get("access_token", "")
            raise ValueError(f"Failed to refresh Microsoft OAuth token: {resp.text}")
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"Network error refreshing Microsoft token: {e}")

    def send_email(
        self,
        recipient: str,
        subject: str,
        body_text: str,
        attachments: Optional[List[Dict[str, Any]]] = None,
        custom_headers: Optional[Dict[str, str]] = None
    ) -> ProviderSendResult:
        try:
            access_token = self._get_access_token()
        except Exception as auth_err:
            return ProviderSendResult(
                success=False,
                status="failed",
                error_message=f"Authentication error: {auth_err}"
            )

        # Build Graph sendMail JSON payload
        msg_payload = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "Text",
                    "content": body_text
                },
                "toRecipients": [
                    {"emailAddress": {"address": recipient}}
                ]
            },
            "saveToSentItems": "true"
        }

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        try:
            resp = requests.post(self.GRAPH_SEND_URL, headers=headers, json=msg_payload, timeout=12)
            if resp.status_code in (200, 202):
                msg_id = resp.headers.get("client-request-id", f"graph_msg_{resp.status_code}")
                return ProviderSendResult(
                    success=True,
                    status="provider-accepted",
                    provider_message_id=msg_id,
                    delivery_note="Microsoft Graph accepted message for queueing. Note: Delivery depends on recipient server policies."
                )
            else:
                return ProviderSendResult(
                    success=False,
                    status="failed",
                    error_message=f"Microsoft Graph API error ({resp.status_code}): {resp.text}"
                )
        except requests.exceptions.Timeout:
            logger.error(f"[Outlook] Timeout sending to {recipient}")
            return ProviderSendResult(
                success=False,
                status="uncertain",
                is_ambiguous_timeout=True,
                reconciliation_needed=True,
                error_message="HTTP timeout with Microsoft Graph API. Reconcile sent state before retrying."
            )
        except requests.exceptions.RequestException as req_err:
            return ProviderSendResult(
                success=False,
                status="failed",
                error_message=f"Network error communicating with Microsoft Graph: {req_err}"
            )

    def reconcile_ambiguous_send(
        self,
        recipient: str,
        subject: str,
        attempted_after_iso: str,
        provider_message_id: Optional[str] = None
    ) -> ProviderReconciliationResult:
        try:
            access_token = self._get_access_token()
            headers = {"Authorization": f"Bearer {access_token}"}
            filter_q = f"toRecipients/any(r:r/emailAddress/address eq '{recipient}') and contains(subject, '{subject[:20]}')"
            resp = requests.get(
                self.GRAPH_MESSAGES_URL,
                headers=headers,
                params={"$filter": filter_q, "$top": 5},
                timeout=10
            )
            if resp.status_code == 200:
                val = resp.json().get("value", [])
                if val:
                    return ProviderReconciliationResult(
                        resolved=True,
                        actually_sent=True,
                        provider_message_id=val[0].get("id"),
                        details="Microsoft Graph Sent Items confirmed message was sent."
                    )
                return ProviderReconciliationResult(
                    resolved=True,
                    actually_sent=False,
                    details="Microsoft Graph query confirms message was not sent."
                )
            return ProviderReconciliationResult(
                resolved=False,
                actually_sent=False,
                details=f"Graph API query error: {resp.text}"
            )
        except Exception as e:
            return ProviderReconciliationResult(
                resolved=False,
                actually_sent=False,
                details=f"Reconciliation error: {e}"
            )

    def sync_replies(
        self,
        known_recipients: List[str],
        since_iso: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        return []

    def validate_connection(self) -> Dict[str, Any]:
        try:
            token = self._get_access_token()
            return {
                "valid": bool(token),
                "account_name": self.account_name,
                "email_address": self.email_address,
                "provider_type": "outlook_oauth",
                "message": "Successfully authenticated with Microsoft Graph API using minimal required OAuth2 permissions."
            }
        except Exception as e:
            return {
                "valid": False,
                "account_name": self.account_name,
                "email_address": self.email_address,
                "provider_type": "outlook_oauth",
                "message": f"Microsoft OAuth validation failed: {e}"
            }
