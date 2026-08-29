"""
SMTP Email Notifier.
Sends email alerts via SMTP (e.g. Gmail, Mailgun, custom server).
"""

import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

from ..checkers.base import DomainResult, DomainStatus
from .base import BaseNotifier

logger = logging.getLogger(__name__)


class EmailNotifier(BaseNotifier):
    """
    Notifier for SMTP Email.
    """

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        smtp_user: str,
        smtp_password: str,
        from_email: str,
        to_emails: List[str],
        use_tls: bool = True,
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.from_email = from_email
        self.to_emails = to_emails
        self.use_tls = use_tls

    def _send_email(self, subject: str, body_html: str) -> bool:
        if not self.smtp_host or not self.to_emails:
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.from_email
        msg["To"] = ", ".join(self.to_emails)

        msg.attach(MIMEText(body_html, "html"))

        try:
            context = ssl.create_default_context()
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls(context=context)
                if self.smtp_user and self.smtp_password:
                    server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.from_email, self.to_emails, msg.as_string())
            return True
        except Exception as e:
            logger.error(f"Email notification error: {e}")
            return False

    def send_alert(self, result: DomainResult, alert_type: str, custom_message: Optional[str] = None) -> bool:
        subject = f"[Domain Monitor Alert] {result.domain} is {result.status.value}"
        html = f"""
        <html>
        <body style="font-family: sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #2b7; ">Domain Alert: {result.domain}</h2>
            <p><strong>Status:</strong> {result.status.value}</p>
            <p><strong>Engine:</strong> {result.engine}</p>
            <p><strong>Expiration:</strong> {result.expiration_date or 'N/A'}</p>
            {f'<p><strong>Note:</strong> {custom_message}</p>' if custom_message else ''}
            <hr>
            <p><a href="https://dash.cloudflare.com/" style="background: #f60; color: #fff; padding: 8px 12px; text-decoration: none; border-radius: 4px;">Open Cloudflare</a></p>
        </body>
        </html>
        """
        return self._send_email(subject, html)

    def send_summary(self, stats: Dict[str, Any], available_domains: List[str]) -> bool:
        subject = f"[Domain Monitor Summary] {stats.get('available', 0)} Available Domains Detected"
        domain_items = "".join([f"<li><code>{d}</code></li>" for d in available_domains])
        html = f"""
        <html>
        <body style="font-family: sans-serif; line-height: 1.6;">
            <h2>Domain Monitor Summary</h2>
            <p>Total: {stats.get('total', 0)} | Available: {stats.get('available', 0)} | Expiring: {stats.get('expiring', 0)}</p>
            <h3>Available Domains:</h3>
            <ul>{domain_items}</ul>
        </body>
        </html>
        """
        return self._send_email(subject, html)
