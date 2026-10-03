"""
Gmail OAuth2 Authenticated Email Provider for ScholarScout.
Uses Google's official Gmail REST API with minimal required scopes:
- https://www.googleapis.com/auth/gmail.send (Send outreach messages)
- https://www.googleapis.com/auth/gmail.readonly (Optional: Read replies for follow-up synchronization)

Never asks for normal email passwords. Tokens are stored securely on the backend.
"""

import base64
import json
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from typing import Dict, Any, Optional, List
import requests

from backend.emails.providers.base import (
    BaseEmailProvider,
    ProviderSendResult,
    ProviderReconciliationResult
)
from backend.logging_utils import logger

class GmailOAuthProvider(BaseEmailProvider):
    """Authenticated Gmail REST API provider."""

    TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
    GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
    GMAIL_MESSAGES_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"

    def _get_access_token(self) -> str:
        """Retrieves a fresh OAuth2 access token using stored refresh token."""
        client_id = self.credentials.get("client_id", "")
        client_secret = self.credentials.get("client_secret", "")
        refresh_token = self.credentials.get("refresh_token", "")

        if not refresh_token:
            raise ValueError("Gmail account requires OAuth2 refresh_token. No password or unauthenticated access allowed.")

        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }

        try:
            resp = requests.post(self.TOKEN_ENDPOINT, data=data, timeout=10)
            if resp.status_code == 200:
                return resp.json().get("access_token", "")
            raise ValueError(f"Failed to refresh Gmail OAuth token: {resp.text}")
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"Network error refreshing Gmail OAuth token: {e}")

    def send_email(
        self,
        recipient: str,
        subject: str,
        body_text: str,
        attachments: Optional[List[Dict[str, Any]]] = None,
        custom_headers: Optional[Dict[str, str]] = None
    ) -> ProviderSendResult:
        """Sends an email via Google Gmail REST API."""
        try:
            access_token = self._get_access_token()
        except Exception as auth_err:
            return ProviderSendResult(
                success=False,
                status="failed",
                error_message=f"Authentication error: {auth_err}",
                raw_response={"error": "auth_failure"}
            )

        # Build RFC 2822 MIME message
        msg = MIMEMultipart()
        msg["To"] = recipient
        msg["From"] = self.email_address
        msg["Subject"] = subject
        msg.attach(MIMEText(body_text, "plain", "utf-8"))

        # Attach validated files if present
        if attachments:
            for att in attachments:
                file_path = att.get("path")
                file_name = att.get("name", "attachment")
                if file_path:
                    try:
                        with open(file_path, "rb") as f:
                            part = MIMEApplication(f.read(), Name=file_name)
                            part["Content-Disposition"] = f'attachment; filename="{file_name}"'
                            msg.attach(part)
                    except Exception as att_err:
                        logger.warning(f"[Gmail] Could not attach file {file_path}: {att_err}")

        # Base64url encode the raw message
        raw_msg = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        payload = {"raw": raw_msg}

        try:
            response = requests.post(
                self.GMAIL_SEND_URL,
                headers=headers,
                json=payload,
                timeout=12
            )

            if response.status_code in (200, 201):
                res_data = response.json()
                msg_id = res_data.get("id", "")
                return ProviderSendResult(
                    success=True,
                    status="provider-accepted",
                    provider_message_id=msg_id,
                    raw_response=res_data,
                    delivery_note="Gmail accepted message for delivery. Note: Delivery depends on recipient server and spam policies."
                )
            else:
                return ProviderSendResult(
                    success=False,
                    status="failed",
                    error_message=f"Gmail API error ({response.status_code}): {response.text}",
                    raw_response={"status_code": response.status_code, "text": response.text}
                )

        except requests.exceptions.Timeout:
            # Ambiguous timeout! Do NOT blindly retry to avoid duplicate emails to professors.
            logger.error(f"[Gmail] Ambiguous timeout sending to {recipient}")
            return ProviderSendResult(
                success=False,
                status="uncertain",
                is_ambiguous_timeout=True,
                reconciliation_needed=True,
                error_message="HTTP timeout awaiting Gmail response. State is uncertain; run reconciliation before retrying.",
                raw_response={"timeout": True}
            )
        except requests.exceptions.RequestException as req_err:
            return ProviderSendResult(
                success=False,
                status="failed",
                error_message=f"Network error communicating with Gmail API: {req_err}",
                raw_response={"network_error": str(req_err)}
            )

    def reconcile_ambiguous_send(
        self,
        recipient: str,
        subject: str,
        attempted_after_iso: str,
        provider_message_id: Optional[str] = None
    ) -> ProviderReconciliationResult:
        """Queries Gmail messages list to check if message was sent."""
        try:
            access_token = self._get_access_token()
            headers = {"Authorization": f"Bearer {access_token}"}
            
            # Search query: to:recipient subject:"subject"
            clean_sub = subject.replace('"', '')
            q = f'to:{recipient} subject:"{clean_sub}"'
            
            resp = requests.get(
                self.GMAIL_MESSAGES_URL,
                headers=headers,
                params={"q": q, "maxResults": 5},
                timeout=10
            )

            if resp.status_code == 200:
                data = resp.json()
                messages = data.get("messages", [])
                if messages:
                    found_id = messages[0]["id"]
                    return ProviderReconciliationResult(
                        resolved=True,
                        actually_sent=True,
                        provider_message_id=found_id,
                        details="Gmail sent message index confirmed message was transmitted."
                    )
                return ProviderReconciliationResult(
                    resolved=True,
                    actually_sent=False,
                    details="Gmail query did not find sent message. Safe to re-dispatch."
                )
            return ProviderReconciliationResult(
                resolved=False,
                actually_sent=False,
                details=f"Could not query Gmail index: {resp.text}"
            )
        except Exception as e:
            return ProviderReconciliationResult(
                resolved=False,
                actually_sent=False,
                details=f"Reconciliation query error: {e}"
            )

    def sync_replies(
        self,
        known_recipients: List[str],
        since_iso: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Queries Gmail inbox for messages from known professor contacts."""
        try:
            access_token = self._get_access_token()
            headers = {"Authorization": f"Bearer {access_token}"}
            replies = []

            for recipient in known_recipients:
                q = f"from:{recipient}"
                resp = requests.get(
                    self.GMAIL_MESSAGES_URL,
                    headers=headers,
                    params={"q": q, "maxResults": 3},
                    timeout=8
                )
                if resp.status_code == 200:
                    msgs = resp.json().get("messages", [])
                    for m in msgs:
                        # Fetch snippet
                        m_id = m["id"]
                        detail_resp = requests.get(
                            f"{self.GMAIL_MESSAGES_URL}/{m_id}",
                            headers=headers,
                            params={"format": "metadata"},
                            timeout=5
                        )
                        if detail_resp.status_code == 200:
                            m_data = detail_resp.json()
                            snippet = m_data.get("snippet", "")
                            is_opt_out = any(phrase in snippet.lower() for phrase in [
                                "unsubscribe", "not taking students", "no positions", "remove from list"
                            ])
                            replies.append({
                                "sender_email": recipient,
                                "subject": "Re: Inquiry",
                                "snippet": snippet,
                                "provider_message_id": m_id,
                                "provider_thread_id": m_data.get("threadId", ""),
                                "is_opt_out": is_opt_out,
                                "received_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(m_data.get("internalDate", time.time()*1000))/1000))
                            })
            return replies
        except Exception as e:
            logger.warning(f"[Gmail] Reply sync failed: {e}")
            return []

    def validate_connection(self) -> Dict[str, Any]:
        """Validates OAuth credentials with Google."""
        try:
            token = self._get_access_token()
            return {
                "valid": bool(token),
                "account_name": self.account_name,
                "email_address": self.email_address,
                "provider_type": "gmail_oauth",
                "message": "Successfully authenticated with Google Gmail API using minimal required OAuth2 scopes."
            }
        except Exception as e:
            return {
                "valid": False,
                "account_name": self.account_name,
                "email_address": self.email_address,
                "provider_type": "gmail_oauth",
                "message": f"Gmail OAuth validation failed: {e}"
            }
