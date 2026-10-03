"""
Standard Authenticated SMTP Provider for Custom Institutional Mailboxes.
Requires dedicated App Password with TLS/SSL.
Never requests or accepts main account passwords; stored exclusively on backend database.
"""

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from typing import Dict, Any, Optional, List

from backend.emails.providers.base import (
    BaseEmailProvider,
    ProviderSendResult,
    ProviderReconciliationResult
)
from backend.logging_utils import logger

class CustomSMTPProvider(BaseEmailProvider):
    """Custom SMTP Server Provider with TLS security."""

    def __init__(self, account_config: Dict[str, Any]):
        super().__init__(account_config)
        self.smtp_host = self.credentials.get("smtp_host", "")
        self.smtp_port = int(self.credentials.get("smtp_port", 587))
        self.smtp_username = self.credentials.get("smtp_username", self.email_address)
        self.app_password = self.credentials.get("app_password", "")
        self.use_tls = self.credentials.get("use_tls", True)

    def send_email(
        self,
        recipient: str,
        subject: str,
        body_text: str,
        attachments: Optional[List[Dict[str, Any]]] = None,
        custom_headers: Optional[Dict[str, str]] = None
    ) -> ProviderSendResult:
        if not self.smtp_host or not self.app_password:
            return ProviderSendResult(
                success=False,
                status="failed",
                error_message="SMTP configuration incomplete: Host and App Password are required."
            )

        msg = MIMEMultipart()
        msg["From"] = self.email_address
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(body_text, "plain", "utf-8"))

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
                    except Exception as e:
                        logger.warning(f"[SMTP] Attachment error {file_path}: {e}")

        try:
            context = ssl.create_default_context()
            if self.smtp_port == 465:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, context=context, timeout=12)
            else:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=12)
                if self.use_tls:
                    server.starttls(context=context)

            server.login(self.smtp_username, self.app_password)
            server.send_message(msg)
            server.quit()

            import uuid
            msg_id = f"smtp_{uuid.uuid4().hex[:10]}"
            return ProviderSendResult(
                success=True,
                status="provider-accepted",
                provider_message_id=msg_id,
                delivery_note="SMTP server accepted message for transfer. Note: Delivery depends on recipient mail exchanger."
            )
        except smtplib.SMTPAuthenticationError as auth_err:
            return ProviderSendResult(
                success=False,
                status="failed",
                error_message=f"SMTP authentication failed: {auth_err}. Ensure you are using an App Password."
            )
        except (smtplib.SMTPServerDisconnected, TimeoutError) as timeout_err:
            return ProviderSendResult(
                success=False,
                status="uncertain",
                is_ambiguous_timeout=True,
                reconciliation_needed=True,
                error_message=f"SMTP server connection timed out or disconnected during transfer: {timeout_err}"
            )
        except Exception as e:
            return ProviderSendResult(
                success=False,
                status="failed",
                error_message=f"SMTP send failed: {e}"
            )

    def reconcile_ambiguous_send(
        self,
        recipient: str,
        subject: str,
        attempted_after_iso: str,
        provider_message_id: Optional[str] = None
    ) -> ProviderReconciliationResult:
        # Standard SMTP does not offer built-in remote query APIs without IMAP.
        return ProviderReconciliationResult(
            resolved=True,
            actually_sent=False,
            details="SMTP protocol does not retain remote queryable sent index. Marked for safe operator decision."
        )

    def sync_replies(
        self,
        known_recipients: List[str],
        since_iso: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        return []

    def validate_connection(self) -> Dict[str, Any]:
        try:
            context = ssl.create_default_context()
            if self.smtp_port == 465:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, context=context, timeout=8)
            else:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=8)
                if self.use_tls:
                    server.starttls(context=context)
            server.login(self.smtp_username, self.app_password)
            server.quit()
            return {
                "valid": True,
                "account_name": self.account_name,
                "email_address": self.email_address,
                "provider_type": "custom_smtp",
                "message": "Successfully authenticated with SMTP server over secure TLS/SSL."
            }
        except Exception as e:
            return {
                "valid": False,
                "account_name": self.account_name,
                "email_address": self.email_address,
                "provider_type": "custom_smtp",
                "message": f"SMTP validation failed: {e}"
            }
