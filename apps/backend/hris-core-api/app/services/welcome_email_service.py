from html import escape
import time
from typing import Optional

from app.core.settings import get_settings
from app.services.email_delivery import check_email_readiness, send_email


def _decode_template_line_breaks(value: str) -> str:
    """Turn dotenv-safe escaped newlines into real email line breaks."""
    return value.replace("\\r\\n", "\n").replace("\\n", "\n")


def _welcome_html(*, brand: str, tenant_name: str, portal_url: str, username: str, password_line: str, support: str) -> str:
    safe_brand = escape(brand)
    safe_tenant = escape(tenant_name)
    safe_url = escape(portal_url, quote=True)
    safe_username = escape(username)
    safe_password_line = escape(password_line)
    safe_support = escape(support)
    return f"""<!doctype html>
<html><body style="margin:0;background:#f4f7fb;font-family:Arial,sans-serif;color:#172033">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f4f7fb;padding:32px 12px">
<tr><td align="center"><table role="presentation" width="600" cellspacing="0" cellpadding="0" style="max-width:600px;background:#fff;border:1px solid #dfe5ee;border-radius:10px;overflow:hidden">
<tr><td style="background:#073b6f;padding:24px 32px;color:#fff;font-size:22px;font-weight:700">{safe_brand}</td></tr>
<tr><td style="padding:32px">
<h1 style="margin:0 0 16px;font-size:24px;color:#073b6f">Welcome to your HRIS portal</h1>
<p style="margin:0 0 16px;line-height:1.6">Your account for <strong>{safe_tenant}</strong> is ready.</p>
<p style="margin:0 0 8px;line-height:1.6"><strong>Username:</strong> {safe_username}</p>
<p style="margin:0 0 24px;line-height:1.6">{safe_password_line}</p>
<p style="margin:0 0 28px"><a href="{safe_url}" style="display:inline-block;background:#0b63a9;color:#fff;text-decoration:none;font-weight:700;padding:12px 20px;border-radius:6px">Open HRIS Portal</a></p>
<p style="margin:0 0 8px;line-height:1.6">For your security, use only the portal address shown below and never share your password.</p>
<p style="margin:0 0 24px;word-break:break-all"><a href="{safe_url}" style="color:#0b63a9">{safe_url}</a></p>
<p style="margin:0;color:#5b6575;font-size:13px">Need help? Contact {safe_support}.</p>
</td></tr></table></td></tr></table></body></html>"""


def check_smtp_readiness() -> dict:
    """Backward-compatible readiness entry point for the selected email provider."""
    return check_email_readiness()


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
    portal_url = f"{settings.portal_base_url.rstrip('/')}/"
    body = _decode_template_line_breaks(settings.welcome_email_body_template).format(
        brand_name=brand,
        tenant_name=tenant_name,
        portal_url=portal_url,
        username=username,
        password_line=password_line,
        support_email=support,
    )
    if (logo_primary_uri or "").strip():
        body = f"{body}\nBrand logo: {logo_primary_uri.strip()}\n"

    html_body = _welcome_html(
            brand=brand,
            tenant_name=tenant_name,
            portal_url=portal_url,
            username=username,
            password_line=password_line,
            support=support,
        )
    attempts = max(1, int(settings.enrollment_email_max_attempts))
    for attempt in range(1, attempts + 1):
        try:
            result = send_email(to_email=email, subject=subject, text_body=body, html_body=html_body)
            break
        except Exception:
            if attempt >= attempts:
                raise
            time.sleep(min(30, settings.enrollment_email_retry_base_seconds * (2 ** (attempt - 1))))
    return {**result, "attempts": attempt}
