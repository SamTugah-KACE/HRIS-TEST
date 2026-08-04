import logging

import httpx

from app.core.settings import get_settings
from app.services.keycloak_provisioning import _admin_access_token, _admin_base_url, _target_realm_from_issuer

logger = logging.getLogger(__name__)


def configure_keycloak_realm_email_if_enabled() -> dict:
    """Idempotently configure Keycloak action-email SMTP from the HRIS SMTP secret set."""
    settings = get_settings()
    if not settings.keycloak_manage_realm_email_settings:
        return {"configured": False, "reason": "disabled"}
    if not (settings.smtp_host or "").strip():
        return {"configured": False, "reason": "smtp_not_configured"}
    base = _admin_base_url()
    realm = _target_realm_from_issuer()
    if not base or not realm:
        return {"configured": False, "reason": "keycloak_not_configured"}

    with httpx.Client(timeout=settings.http_client_timeout_seconds) as client:
        token = _admin_access_token(client)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        realm_url = f"{base}/admin/realms/{realm}"
        response = client.get(realm_url, headers=headers)
        response.raise_for_status()
        payload = response.json()
        payload.update(
            {
                "resetPasswordAllowed": True,
                "verifyEmail": True,
                "bruteForceProtected": True,
                "smtpServer": {
                    "host": settings.smtp_host,
                    "port": str(settings.smtp_port),
                    "from": settings.smtp_from_email,
                    "fromDisplayName": settings.tenant_brand_name_default,
                    "auth": str(bool(settings.smtp_use_credentials)).lower(),
                    "user": settings.smtp_username or "",
                    "password": settings.smtp_password or "",
                    "starttls": str(bool(settings.smtp_use_tls)).lower(),
                    "ssl": str(bool(settings.smtp_use_ssl)).lower(),
                },
            }
        )
        if (settings.keycloak_email_theme or "").strip():
            payload["emailTheme"] = settings.keycloak_email_theme.strip()
        updated = client.put(realm_url, headers=headers, json=payload)
        updated.raise_for_status()
    logger.warning("Keycloak realm email and password-reset settings configured")
    return {"configured": True, "realm": realm}
