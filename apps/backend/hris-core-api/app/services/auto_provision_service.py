import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import httpx

from app.clients.adapter_utils import build_auth_headers, build_hris_metadata_headers
from app.core.auth import AuthenticatedUser
from app.core.settings import get_settings
from app.models.tenant_mapping import TenantMapping
from app.services import automation_store
from app.services.tenant_registry_client import get_tenant_mapping, list_tenant_mappings
from app.services.user_drift_sync import build_tenant_user_drift

logger = logging.getLogger(__name__)

def _allowed_modules() -> Set[str]:
    settings = get_settings()
    return {
        module.strip().lower()
        for module in str(settings.auto_provision_allowed_modules or "").split(",")
        if module.strip()
    }


def _module_endpoint(module_name: str, mapping: TenantMapping) -> Optional[str]:
    settings = get_settings()
    if module_name == "eappraisal":
        template = (settings.eappraisal_domain_template or "").strip()
        integration_base = (settings.eappraisal_integration_base_url or "").strip()
        base_url = ""
        if template and mapping.eappraisal_subdomain:
            base_url = template.format(subdomain=mapping.eappraisal_subdomain or "").rstrip("/")
        elif integration_base:
            base_url = integration_base.rstrip("/")
        if not base_url:
            return None
        path = settings.eappraisal_provision_user_path.format(tenant_id=mapping.tenant_id).lstrip("/")
        return f"{base_url}/{path}"
    if module_name == "eleave":
        template = (settings.eleave_domain_template or "").strip()
        if not template:
            return None
        base_url = template.format(subdomain=mapping.eleave_subdomain or "").rstrip("/")
        path = settings.eleave_provision_user_path.format(tenant_id=mapping.tenant_id).lstrip("/")
        return f"{base_url}/{path}"
    return None


def _module_auth_headers(module_name: str, mapping: TenantMapping, actor: AuthenticatedUser) -> Dict[str, str]:
    settings = get_settings()
    if module_name == "eappraisal":
        token = actor.raw_token or settings.eappraisal_service_token
        headers = build_auth_headers(token, settings.eappraisal_service_token)
        if (settings.eappraisal_hris_shared_secret or "").strip():
            headers["X-HRIS-Shared-Secret"] = settings.eappraisal_hris_shared_secret.strip()
        if (settings.eappraisal_hris_service_token or "").strip():
            headers["X-HRIS-Service-Token"] = settings.eappraisal_hris_service_token.strip()
    elif module_name == "eleave":
        token = actor.raw_token or settings.eleave_service_token
        headers = build_auth_headers(token, settings.eleave_service_token)
    else:
        token = actor.raw_token
        headers = build_auth_headers(token, None)

    headers.update(
        build_hris_metadata_headers(
            module_name=module_name,
            user_token=token,
            tenant_id=mapping.tenant_id,
            tenant_code=mapping.code,
        )
    )
    headers["Content-Type"] = "application/json"
    return headers


def _idempotency_key(*, module_name: str, tenant_id: str, employee_id: str, email: str) -> str:
    raw = f"{module_name}|{tenant_id}|{employee_id}|{email}".lower().strip()
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"hris-autoprov-{digest[:48]}"


def _audit_write(entry: Dict[str, Any]) -> None:
    settings = get_settings()
    path = Path(settings.auto_provision_audit_log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=True) + "\n")
    try:
        automation_store.record_provisioning_audit(entry)
    except Exception as exc:
        logger.warning("Provisioning audit persistence skipped: %s", exc)


def _build_actions_from_drift(drift: Dict[str, Any], allowed_modules: Set[str], max_actions: int) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    for user in drift.get("users", []):
        if not isinstance(user, dict):
            continue
        for module_name in ("eappraisal", "eleave"):
            if module_name not in allowed_modules:
                continue
            module_state = user.get(module_name)
            if not isinstance(module_state, dict):
                continue
            if module_state.get("present", True):
                continue
            if module_state.get("reason") not in {"not_found", "upstream_error"}:
                continue
            actions.append(
                {
                    "module": module_name,
                    "employee_id": str(user.get("employee_id") or ""),
                    "staff_id": str(user.get("staff_id") or ""),
                    "email": str(user.get("email") or ""),
                    "reason": module_state.get("reason", "unknown"),
                }
            )
            if len(actions) >= max_actions:
                return actions
    return actions


def provision_missing_users_for_tenant(
    *,
    tenant_id: str,
    actor: AuthenticatedUser,
    dry_run_override: Optional[bool] = None,
    max_users: int = 200,
) -> Dict[str, Any]:
    settings = get_settings()
    mapping = get_tenant_mapping(tenant_id)
    effective_dry_run = settings.auto_provision_dry_run if dry_run_override is None else bool(dry_run_override)
    allowed = _allowed_modules()
    max_actions = max(1, settings.auto_provision_max_actions_per_run)
    try:
        drift = build_tenant_user_drift(mapping=mapping, token=actor.raw_token, max_users=max_users)
    except Exception as exc:
        return {
            "run_id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ"),
            "tenant_id": tenant_id,
            "dry_run": effective_dry_run,
            "auto_provision_enabled": settings.enable_auto_provision,
            "actions_planned": 0,
            "actions_executed": 0,
            "success_count": 0,
            "failed_count": 1,
            "results": [{"status": "failed", "tenant_id": tenant_id, "error": str(exc)}],
            "rollback_plan": [],
        }
    actions = _build_actions_from_drift(drift, allowed, max_actions=max_actions)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    results: List[Dict[str, Any]] = []
    rollback_plan: List[Dict[str, Any]] = []

    with httpx.Client(timeout=settings.http_client_timeout_seconds) as client:
        for action in actions:
            module_name = action["module"]
            endpoint = _module_endpoint(module_name, mapping)
            employee_id = action.get("employee_id", "")
            email = action.get("email", "")
            idem_key = _idempotency_key(
                module_name=module_name,
                tenant_id=mapping.tenant_id,
                employee_id=employee_id,
                email=email,
            )
            audit_base = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "run_id": run_id,
                "tenant_id": mapping.tenant_id,
                "tenant_code": mapping.code,
                "module": module_name,
                "employee_id": employee_id,
                "staff_id": action.get("staff_id", ""),
                "email": email,
                "idempotency_key": idem_key,
                "dry_run": effective_dry_run,
            }
            if not endpoint:
                entry = {**audit_base, "status": "skipped_no_endpoint"}
                _audit_write(entry)
                results.append(entry)
                continue

            if effective_dry_run:
                entry = {**audit_base, "status": "dry_run"}
                _audit_write(entry)
                results.append(entry)
                continue

            headers = _module_auth_headers(module_name, mapping, actor)
            headers["X-Idempotency-Key"] = idem_key
            payload = {
                "tenant_id": mapping.tenant_id,
                "employee_id": employee_id,
                "staff_id": action.get("staff_id", ""),
                "email": email,
                "requested_by": actor.sub,
                "source": "hris-auto-provision",
            }
            try:
                response = client.post(endpoint, headers=headers, json=payload)
                status_code = int(response.status_code)
                if status_code in (200, 201, 202, 409):
                    entry = {**audit_base, "status": "provisioned", "response_status": status_code}
                    _audit_write(entry)
                    results.append(entry)
                    rollback_plan.append(
                        {
                            "module": module_name,
                            "tenant_id": mapping.tenant_id,
                            "employee_id": employee_id,
                            "note": "Use module-specific deprovision/deactivate endpoint if compensation is required.",
                        }
                    )
                    continue

                entry = {
                    **audit_base,
                    "status": "failed",
                    "response_status": status_code,
                    "response_body": response.text[:1000],
                }
                _audit_write(entry)
                results.append(entry)
                if settings.auto_provision_stop_on_error:
                    break
            except Exception as exc:
                entry = {**audit_base, "status": "failed", "error": str(exc)}
                _audit_write(entry)
                results.append(entry)
                if settings.auto_provision_stop_on_error:
                    break

    success_count = len([row for row in results if row.get("status") == "provisioned"])
    failed_count = len([row for row in results if row.get("status") == "failed"])
    return {
        "run_id": run_id,
        "tenant_id": tenant_id,
        "dry_run": effective_dry_run,
        "auto_provision_enabled": settings.enable_auto_provision,
        "actions_planned": len(actions),
        "actions_executed": len(results),
        "success_count": success_count,
        "failed_count": failed_count,
        "results": results,
        "rollback_plan": rollback_plan,
    }


def provision_missing_users_globally(actor: AuthenticatedUser) -> Dict[str, Any]:
    settings = get_settings()
    if not settings.enable_auto_provision:
        return {
            "enabled": False,
            "message": "Automatic provisioning is disabled",
            "tenants": [],
        }

    tenants = list_tenant_mappings(limit=settings.auto_sync_max_tenants)
    active_tenants = [tenant for tenant in tenants if tenant.is_tenant_active()]
    outputs: List[Dict[str, Any]] = []
    for tenant in active_tenants[: settings.auto_sync_max_tenants]:
        outputs.append(
            provision_missing_users_for_tenant(
                tenant_id=tenant.tenant_id,
                actor=actor,
                dry_run_override=None,
                max_users=settings.auto_sync_max_users_per_tenant,
            )
        )
    return {
        "enabled": True,
        "dry_run_default": settings.auto_provision_dry_run,
        "tenants_processed": len(outputs),
        "tenants": outputs,
    }
