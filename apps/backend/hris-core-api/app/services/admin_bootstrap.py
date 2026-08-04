import json
import logging
from dataclasses import dataclass
from typing import Optional

from app.core.settings import get_settings
from app.services.keycloak_provisioning import ensure_user_and_temp_password

logger = logging.getLogger("hris_core.access")


@dataclass
class BootstrapAccount:
    role: str
    username: str
    email: str
    password: str
    tenant_id: str


def _normalize_account(
    *,
    role: str,
    username: Optional[str],
    email: Optional[str],
    password: Optional[str],
    tenant_id: Optional[str],
    default_tenant_id: str,
) -> Optional[BootstrapAccount]:
    username_value = str(username or "").strip().lower()
    password_value = str(password or "").strip()
    if not username_value or not password_value:
        return None
    email_value = str(email or "").strip().lower() or username_value
    tenant_value = str(tenant_id or "").strip() or default_tenant_id
    if "@" not in email_value:
        email_value = f"{username_value}@hris.local"
    return BootstrapAccount(
        role=role,
        username=username_value,
        email=email_value,
        password=password_value,
        tenant_id=tenant_value,
    )


def _configured_accounts() -> list[BootstrapAccount]:
    settings = get_settings()
    default_tenant_id = str(settings.dev_default_tenant_id or "11111111-1111-1111-1111-111111111111").strip()
    accounts: list[BootstrapAccount] = []

    super_admin = _normalize_account(
        role="hris:super_admin",
        username=settings.bootstrap_superadmin_username,
        email=settings.bootstrap_superadmin_email,
        password=settings.bootstrap_superadmin_password,
        tenant_id=settings.bootstrap_superadmin_tenant_id,
        default_tenant_id=default_tenant_id,
    )
    if super_admin:
        accounts.append(super_admin)

    tenant_admin = _normalize_account(
        role="hris:tenant_admin",
        username=settings.bootstrap_tenantadmin_username,
        email=settings.bootstrap_tenantadmin_email,
        password=settings.bootstrap_tenantadmin_password,
        tenant_id=settings.bootstrap_tenantadmin_tenant_id,
        default_tenant_id=default_tenant_id,
    )
    if tenant_admin:
        accounts.append(tenant_admin)

    return accounts


def bootstrap_admin_accounts_if_enabled() -> dict:
    settings = get_settings()
    if not settings.bootstrap_admin_enabled:
        return {"enabled": False, "attempted": 0, "completed": 0, "results": []}

    accounts = _configured_accounts()
    if not accounts:
        logger.warning(
            "Admin bootstrap enabled but no credentials were configured via BOOTSTRAP_* environment variables"
        )
        return {"enabled": True, "attempted": 0, "completed": 0, "results": []}

    results: list[dict] = []
    for account in accounts:
        try:
            outcome = ensure_user_and_temp_password(
                email=account.email,
                username=account.username,
                tenant_id=account.tenant_id,
                default_role=account.role,
                roles=[account.role],
                allow_existing_user_password_reset=True,
                send_temp_password=False,
                fixed_password=account.password,
                fixed_password_temporary=False,
            )
            results.append(
                {
                    "username": account.username,
                    "role": account.role,
                    "tenant_id": account.tenant_id,
                    "status": str(outcome.get("status") or "unknown"),
                    "password_configured": bool(account.password),
                }
            )
        except Exception as exc:
            logger.exception(
                "Admin bootstrap failed for account '%s' with role '%s'",
                account.username,
                account.role,
            )
            results.append(
                {
                    "username": account.username,
                    "role": account.role,
                    "tenant_id": account.tenant_id,
                    "status": "failed",
                    "error": str(exc),
                }
            )

    logger.warning(
        "Admin bootstrap completed: %s",
        json.dumps(
            {
                "enabled": True,
                "attempted": len(accounts),
                "completed": len([r for r in results if r.get("status") != "failed"]),
                "failed": len([r for r in results if r.get("status") == "failed"]),
            },
            ensure_ascii=True,
        ),
    )
    return {
        "enabled": True,
        "attempted": len(accounts),
        "completed": len([r for r in results if r.get("status") != "failed"]),
        "results": results,
    }
