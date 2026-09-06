from __future__ import annotations

from email.message import EmailMessage
import smtplib
import ssl
from typing import Optional

import httpx

from app.core.settings import get_settings


class EmailDeliveryError(RuntimeError):
    def __init__(self, message: str, *, provider: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code


def _smtp_context(settings) -> ssl.SSLContext:
    context = ssl.create_default_context()
    if not settings.smtp_validate_certs:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context


def check_email_readiness() -> dict:
    settings = get_settings()
    provider = settings.mail_provider.strip().lower()
    if provider == "https":
        if not (settings.email_http_api_key or "").strip():
            return {"ok": False, "provider": "https", "stage": "configuration", "reason": "api_key_missing"}
        return {"ok": True, "provider": settings.email_http_provider, "stage": "configured", "transport": "https"}
    if not settings.smtp_host:
        return {"ok": False, "provider": "smtp", "stage": "configuration", "reason": "smtp_not_configured"}
    context = _smtp_context(settings)
    smtp_class = smtplib.SMTP_SSL if settings.smtp_use_ssl else smtplib.SMTP
    kwargs = {"timeout": settings.email_http_timeout_seconds}
    if settings.smtp_use_ssl:
        kwargs["context"] = context
    stage = "connect"
    try:
        with smtp_class(settings.smtp_host, settings.smtp_port, **kwargs) as server:
            server.ehlo()
            if settings.smtp_use_tls:
                stage = "starttls"
                server.starttls(context=context)
                server.ehlo()
            if settings.smtp_use_credentials:
                stage = "authentication"
                server.login(settings.smtp_username or "", settings.smtp_password or "")
        return {"ok": True, "provider": "smtp", "stage": "authenticated", "transport": "smtp"}
    except smtplib.SMTPAuthenticationError:
        return {"ok": False, "provider": "smtp", "stage": stage, "reason": "smtp_authentication_failed"}
    except (OSError, smtplib.SMTPException) as exc:
        return {"ok": False, "provider": "smtp", "stage": stage, "reason": type(exc).__name__}


def send_email(*, to_email: str, subject: str, text_body: str, html_body: Optional[str] = None) -> dict:
    settings = get_settings()
    provider = settings.mail_provider.strip().lower()
    recipient = str(to_email or "").strip().lower()
    if not recipient:
        raise EmailDeliveryError("Recipient email is required", provider=provider)
    if provider == "https":
        return _send_resend(settings, recipient, subject, text_body, html_body)
    return _send_smtp(settings, recipient, subject, text_body, html_body)


def _send_resend(settings, recipient: str, subject: str, text_body: str, html_body: Optional[str]) -> dict:
    payload = {"from": settings.smtp_from_email, "to": [recipient], "subject": subject, "text": text_body}
    if html_body:
        payload["html"] = html_body
    try:
        response = httpx.post(
            settings.email_http_api_url,
            headers={
                "Authorization": f"Bearer {settings.email_http_api_key}",
                "Content-Type": "application/json",
                "User-Agent": "GI-KACE-HRIS/1.0",
            },
            json=payload,
            timeout=settings.email_http_timeout_seconds,
        )
    except httpx.RequestError as exc:
        raise EmailDeliveryError("HTTPS email provider is unavailable", provider="resend") from exc
    if response.status_code not in {200, 201, 202}:
        raise EmailDeliveryError(
            f"HTTPS email provider rejected the request ({response.status_code})",
            provider="resend", status_code=response.status_code,
        )
    response_payload = response.json() if response.content else {}
    return {"sent": True, "provider": "resend", "transport": "https", "provider_id": response_payload.get("id")}


def _send_smtp(settings, recipient: str, subject: str, text_body: str, html_body: Optional[str]) -> dict:
    if not settings.smtp_host:
        raise EmailDeliveryError("SMTP is not configured", provider="smtp")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from_email
    message["To"] = recipient
    message.set_content(text_body)
    if html_body:
        message.add_alternative(html_body, subtype="html")
    context = _smtp_context(settings)
    smtp_class = smtplib.SMTP_SSL if settings.smtp_use_ssl else smtplib.SMTP
    kwargs = {"timeout": settings.email_http_timeout_seconds}
    if settings.smtp_use_ssl:
        kwargs["context"] = context
    try:
        with smtp_class(settings.smtp_host, settings.smtp_port, **kwargs) as server:
            server.ehlo()
            if settings.smtp_use_tls:
                server.starttls(context=context)
                server.ehlo()
            if settings.smtp_use_credentials:
                server.login(settings.smtp_username or "", settings.smtp_password or "")
            refused = server.send_message(message)
            if refused:
                raise smtplib.SMTPRecipientsRefused(refused)
    except (OSError, smtplib.SMTPException) as exc:
        raise EmailDeliveryError("SMTP delivery failed", provider="smtp") from exc
    return {"sent": True, "provider": "smtp", "transport": "smtp"}
