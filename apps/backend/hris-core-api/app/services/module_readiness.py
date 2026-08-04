from __future__ import annotations

from typing import Any, Dict

from app.clients import eappraisal_client
from app.core.auth import AuthenticatedUser
from app.core.settings import get_settings
from app.models.tenant_mapping import TenantMapping
from app.services import automation_store


def check_module_readiness(
    *,
    module_name: str,
    mapping: TenantMapping,
    user: AuthenticatedUser,
    identity_override: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    module = str(module_name or "").strip().lower()
    settings = get_settings()

    def _result(ready: bool, code: str, detail: str, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        out = {"ready": bool(ready), "code": str(code), "detail": str(detail)}
        try:
            automation_store.record_probe(
                tenant_id=mapping.tenant_id,
                module_name=module,
                ok=bool(ready),
                detail=f"{code}:{detail}",
                payload=payload or out,
            )
        except Exception:
            pass
        return out

    if not mapping.module_enabled(module):
        return _result(False, "module_inactive", f"Module '{module}' is not active for tenant '{mapping.code}'")

    if module == "srms":
        if not str(settings.srms_base_url or "").strip():
            return _result(False, "missing_srms_base_url", "SRMS base URL is not configured")
        return _result(True, "ok", "ready")

    if module == "eappraisal":
        if not str(settings.eappraisal_integration_base_url or "").strip():
            return _result(False, "missing_eappraisal_base_url", "EAPPRAISAL_INTEGRATION_BASE_URL is not configured")
        try:
            payload = eappraisal_client.list_integration_tenant_users(mapping, user.raw_token, limit=2000)
            users = payload.get("users", []) if isinstance(payload, dict) else []
            users = [u for u in users if isinstance(u, dict)]
            identity_override = identity_override or {}
            email = str(identity_override.get("email") or user.email or "").strip().lower()
            employee_id = str(identity_override.get("employee_id") or user.employee_id or "").strip().lower()
            username = str(identity_override.get("username") or user.username or "").strip().lower()
            found = any(
                (
                    email and str(row.get("email") or "").strip().lower() == email
                )
                or (
                    employee_id and str(row.get("employee_id") or "").strip().lower() == employee_id
                )
                or (
                    username and str(row.get("username") or "").strip().lower() == username
                )
                for row in users
            )
            if not found:
                return _result(False, "user_not_in_module_inventory", "User not found in eAppraisal tenant users inventory")
            return _result(True, "ok", "ready")
        except Exception as exc:
            return _result(False, "eappraisal_inventory_check_failed", str(exc))

    if module == "eleave":
        if not str(settings.eleave_domain_template or "").strip():
            return _result(False, "missing_eleave_base_url", "ELEAVE_DOMAIN_TEMPLATE is not configured")
        if not str(settings.eleave_hris_shared_secret or "").strip():
            return _result(False, "missing_eleave_shared_secret", "ELEAVE_HRIS_SHARED_SECRET is not configured")
        return _result(True, "ok", "ready")

    return _result(False, "unsupported_module", f"Unsupported module '{module}'")

