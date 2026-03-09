from email.message import EmailMessage
import smtplib
from typing import Optional

from app.core.settings import get_settings


def send_welcome_email(
    *,
    to_email: str,
    tenant_name: str,
    username: str,
    temporary_password: Optional[str],
    brand_name: Optional[str] = None,
    support_email: Optional[str] = None,
    logo_primary_uri: Optional[str] = None,
) -> dict:
    settings = get_settings()
    email = str(to_email or "").strip().lower()
    if not email:
        return {"sent": False, "reason": "missing_email"}

    brand = (brand_name or settings.tenant_brand_name_default).strip()
    support = (support_email or settings.tenant_support_email_default).strip()
    password_line = (
        f"Temporary password: {temporary_password} (change required on first login)"
        if temporary_password
        else "Use your organization-issued identity flow to complete first-time sign-in."
    )
    subject = settings.welcome_email_subject_template.format(
        brand_name=brand,
        tenant_name=tenant_name,
    )
    body = settings.welcome_email_body_template.format(
        brand_name=brand,
        tenant_name=tenant_name,
        portal_url=f"{settings.portal_base_url.rstrip('/')}/",
        username=username,
        password_line=password_line,
        support_email=support,
    )
    if (logo_primary_uri or "").strip():
        body = f"{body}\nBrand logo: {logo_primary_uri.strip()}\n"

    if not settings.smtp_host:
        return {"sent": False, "reason": "smtp_not_configured", "subject": subject, "preview": body[:500]}

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from_email
    msg["To"] = email
    msg.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
        if settings.smtp_use_tls:
            server.starttls()
        if (settings.smtp_username or "").strip():
            server.login(settings.smtp_username, settings.smtp_password or "")
        server.send_message(msg)

    return {"sent": True}
