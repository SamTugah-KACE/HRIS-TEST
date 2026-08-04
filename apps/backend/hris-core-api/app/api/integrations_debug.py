import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.clients import eappraisal_client, eleave_client, srms_client
from app.core.auth import AuthenticatedUser, require_roles
from app.core.settings import get_settings
from app.services.integration_sync import build_sync_snapshot
from app.services.module_readiness import check_module_readiness
from app.services.federated_directory_sync import (
    build_federated_directory_snapshot_for_tenant,
    build_federated_directory_snapshot_global,
    sync_keycloak_from_federated_directory,
)
from app.services import automation_store
from app.services.welcome_email_service import check_smtp_readiness
from app.services.tenant_registry_client import get_tenant_mapping

router = APIRouter(prefix="/debug/integrations", tags=["integration-debug"])
logger = logging.getLogger(__name__)


@router.get("/email-delivery-audit")
def get_email_delivery_audit(
    purpose: Optional[str] = None,
    limit: int = 100,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin")),
):
    """Sanitized delivery outcomes; recipient addresses and secrets are never returned."""
    if not get_settings().enable_integration_debug_endpoints:
        raise HTTPException(status_code=404, detail="Debug integration endpoints are disabled")
    return {"rows": automation_store.list_email_delivery_audit(purpose=purpose, limit=limit)}


@router.get("/email-readiness")
def get_email_readiness(
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin")),
):
    """Validate SMTP connection/TLS/authentication without emailing anyone."""
    if not get_settings().enable_integration_debug_endpoints:
        raise HTTPException(status_code=404, detail="Debug integration endpoints are disabled")
    return check_smtp_readiness()


def _probe(name: str, fetcher, *, tenant_id: str, correlation_id: str) -> Dict[str, Any]:
    try:
        payload = fetcher()
        logger.info(
            "Integration probe succeeded",
            extra={"probe": name, "tenant_id": tenant_id, "correlation_id": correlation_id},
        )
        return {"name": name, "ok": True, "payload": payload}
    except HTTPException as exc:
        logger.warning(
            "Integration probe failed",
            extra={
                "probe": name,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "status_code": exc.status_code,
                "detail": str(exc.detail),
            },
        )
        return {
            "name": name,
            "ok": False,
            "status_code": exc.status_code,
            "detail": str(exc.detail),
        }
    except Exception as exc:
        logger.exception(
            "Integration probe failed (unexpected error)",
            extra={
                "probe": name,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "error": str(exc),
            },
        )
        return {
            "name": name,
            "ok": False,
            "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
            "detail": "Unexpected integration probe error",
        }


@router.get("/eappraisal")
def get_eappraisal_diagnostics(
    request: Request,
    user: AuthenticatedUser = Depends(
        require_roles("hris:super_admin", "hris:tenant_admin", "hris:hr_manager")
    ),
):
    correlation_id = getattr(request.state, "correlation_id", "")
    settings = get_settings()
    if not settings.enable_integration_debug_endpoints:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Debug integration endpoints are disabled",
        )

    mapping = get_tenant_mapping(user.tenant_id)
    employee_id = user.employee_id or user.sub or user.username

    summary_probe = _probe(
        "appraisal_summary",
        lambda: eappraisal_client.get_appraisal_summary(mapping, user.raw_token),
        tenant_id=user.tenant_id,
        correlation_id=correlation_id,
    )
    my_probe = _probe(
        "my_appraisals",
        lambda: eappraisal_client.get_my_appraisals(mapping, user.raw_token),
        tenant_id=user.tenant_id,
        correlation_id=correlation_id,
    )
    past_probe = _probe(
        "employee_appraisals",
        lambda: eappraisal_client.get_employee_appraisals(
            mapping, str(employee_id), user.raw_token
        ),
        tenant_id=user.tenant_id,
        correlation_id=correlation_id,
    )

    # Return only safe high-level metadata and counts.
    safe_result: Dict[str, Any] = {
        "enabled": True,
        "tenant": {
            "tenant_id": user.tenant_id,
            "code": mapping.code,
            "eappraisal_subdomain": mapping.eappraisal_subdomain,
        },
        "config": {
            "domain_template_set": bool(settings.eappraisal_domain_template),
            "adapter_mode": settings.module_adapter_mode,
            "has_service_token": bool(settings.eappraisal_service_token),
            "has_refresh_token": bool(settings.eappraisal_refresh_token),
            "auto_refresh": settings.eappraisal_auto_refresh,
        },
        "probes": {},
    }

    for probe in (summary_probe, my_probe, past_probe):
        if not probe["ok"]:
            safe_result["probes"][probe["name"]] = {
                "ok": False,
                "status_code": probe.get("status_code"),
                "detail": probe.get("detail"),
            }
            continue

        payload = probe.get("payload")
        if probe["name"] == "appraisal_summary" and isinstance(payload, dict):
            safe_result["probes"][probe["name"]] = {
                "ok": True,
                "active_cycles": payload.get("active_cycles"),
                "pending_reviews": payload.get("pending_reviews"),
                "completed_reviews": payload.get("completed_reviews"),
            }
        elif probe["name"] == "my_appraisals" and isinstance(payload, dict):
            safe_result["probes"][probe["name"]] = {
                "ok": True,
                "current_cycle": (payload.get("current_cycle") or {}).get("title"),
                "sections_count": len(payload.get("sections") or []),
            }
        elif probe["name"] == "employee_appraisals" and isinstance(payload, dict):
            safe_result["probes"][probe["name"]] = {
                "ok": True,
                "employee_id": payload.get("employee_id"),
                "past_count": len(payload.get("appraisals") or []),
            }
        else:
            safe_result["probes"][probe["name"]] = {"ok": True}

    probe_states = [
        bool((safe_result["probes"].get(name) or {}).get("ok"))
        for name in ("appraisal_summary", "my_appraisals", "employee_appraisals")
    ]
    safe_result["overall_ok"] = all(probe_states) if probe_states else False
    if not safe_result["overall_ok"]:
        summary_detail = str((safe_result["probes"].get("appraisal_summary") or {}).get("detail", "")).lower()
        if "authentication failed" in summary_detail:
            safe_result["recommended_action"] = "Refresh eAppraisal access token or validate refresh-token configuration."
        else:
            safe_result["recommended_action"] = "Check eAppraisal domain/subdomain configuration and upstream API availability."

    return safe_result


@router.get("/eappraisal/integration-tenants")
def get_eappraisal_integration_tenants_diagnostics(
    request: Request,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin")),
):
    settings = get_settings()
    if not settings.enable_integration_debug_endpoints:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Debug integration endpoints are disabled",
        )
    correlation_id = getattr(request.state, "correlation_id", "")
    probe = _probe(
        "eappraisal_integration_tenants",
        lambda: eappraisal_client.list_integration_tenants(user.raw_token, limit=500),
        tenant_id=user.tenant_id,
        correlation_id=correlation_id,
    )
    if not probe.get("ok"):
        return {"ok": False, "detail": probe.get("detail"), "status_code": probe.get("status_code")}
    payload = probe.get("payload") if isinstance(probe.get("payload"), dict) else {}
    tenants = payload.get("tenants") if isinstance(payload, dict) else None
    return {
        "ok": True,
        "total": payload.get("total"),
        "tenants_count": len(tenants) if isinstance(tenants, list) else 0,
    }


@router.get("/summary")
def get_integrations_summary(
    request: Request,
    user: AuthenticatedUser = Depends(
        require_roles("hris:super_admin", "hris:tenant_admin", "hris:hr_manager")
    ),
):
    correlation_id = getattr(request.state, "correlation_id", "")
    settings = get_settings()
    if not settings.enable_integration_debug_endpoints:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Debug integration endpoints are disabled",
        )

    mapping = get_tenant_mapping(user.tenant_id)
    module_states = mapping.modules.model_dump()
    employee_id = user.employee_id or user.sub or user.username

    srms_probe = _probe(
        "srms",
        lambda: srms_client.get_dashboard_summary(mapping, user.raw_token),
        tenant_id=user.tenant_id,
        correlation_id=correlation_id,
    )
    appraisal_probe = _probe(
        "eappraisal",
        lambda: eappraisal_client.get_appraisal_summary(mapping, user.raw_token),
        tenant_id=user.tenant_id,
        correlation_id=correlation_id,
    )
    leave_probe = _probe(
        "eleave",
        lambda: eleave_client.get_leave_summary(mapping, user.raw_token),
        tenant_id=user.tenant_id,
        correlation_id=correlation_id,
    )

    modules: Dict[str, Any] = {}
    for module_name, probe in (
        ("srms", srms_probe),
        ("eappraisal", appraisal_probe),
        ("eleave", leave_probe),
    ):
        readiness = module_states.get(module_name, {})
        enabled = bool(readiness.get("ready")) and bool(readiness.get("configured"))
        module_payload: Dict[str, Any] = {
            "enabled": enabled,
            "configured": bool(readiness.get("configured")),
            "ready": bool(readiness.get("ready")),
            "status": readiness.get("status"),
            "ok": bool(probe.get("ok")) if enabled else True,
        }
        if probe.get("ok") and enabled:
            module_payload["detail"] = "reachable"
        elif not probe.get("ok") and enabled:
            module_payload["status_code"] = probe.get("status_code")
            module_payload["detail"] = probe.get("detail")
        else:
            module_payload["detail"] = "disabled_for_tenant"
        modules[module_name] = module_payload

    active_modules = [name for name, data in modules.items() if data.get("enabled")]
    overall_ok = all(bool(modules[name].get("ok")) for name in active_modules) if active_modules else True

    recommended_actions = []
    for module_name in active_modules:
        detail = str(modules[module_name].get("detail") or "").lower()
        if "authentication failed" in detail:
            recommended_actions.append(f"Verify {module_name} token/session bridge configuration.")
        elif "not configured" in detail:
            recommended_actions.append(f"Configure {module_name} base URL and tenant mapping.")
        elif "failed to reach" in detail:
            recommended_actions.append(f"Check {module_name} upstream availability/network access.")

    return {
        "enabled": True,
        "overall_ok": overall_ok,
        "tenant": {
            "tenant_id": user.tenant_id,
            "code": mapping.code,
            "name": mapping.name,
            "employee_probe_id": str(employee_id),
        },
        "modules": modules,
        "recommended_actions": recommended_actions[:5],
    }


@router.get("/readiness")
def get_integrations_readiness(
    request: Request,
    user: AuthenticatedUser = Depends(
        require_roles("hris:super_admin", "hris:tenant_admin", "hris:hr_manager")
    ),
):
    settings = get_settings()
    if not settings.enable_integration_debug_endpoints:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Debug integration endpoints are disabled",
        )
    correlation_id = getattr(request.state, "correlation_id", "")
    snapshot = build_sync_snapshot(
        tenant_id=user.tenant_id,
        actor=user,
        include_live_probes=True,
    )
    return {
        "enabled": True,
        "correlation_id": correlation_id,
        "tenant_id": user.tenant_id,
        "readiness": snapshot,
    }


@router.get("/module-readiness")
def get_module_readiness_snapshot(
    request: Request,
    tenant_id: Optional[str] = None,
    email: Optional[str] = None,
    username: Optional[str] = None,
    employee_id: Optional[str] = None,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin")),
):
    settings = get_settings()
    if not settings.enable_integration_debug_endpoints:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Debug integration endpoints are disabled",
        )
    target_tenant = str(tenant_id or user.tenant_id or "").strip()
    if not target_tenant:
        raise HTTPException(status_code=400, detail="tenant_id is required")
    mapping = get_tenant_mapping(target_tenant)
    override = {
        "email": str(email or "").strip().lower() or None,
        "username": str(username or "").strip().lower() or None,
        "employee_id": str(employee_id or "").strip() or None,
    }
    modules = {}
    for module_name in ("srms", "eappraisal", "eleave"):
        modules[module_name] = check_module_readiness(
            module_name=module_name,
            mapping=mapping,
            user=user,
            identity_override=override,
        )
    return {
        "tenant": {"tenant_id": mapping.tenant_id, "code": mapping.code, "name": mapping.name},
        "identity": override,
        "modules": modules,
    }


@router.get("/federated-directory")
def get_federated_directory_snapshot(
    request: Request,
    tenant_id: Optional[str] = None,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin")),
):
    settings = get_settings()
    if not settings.enable_integration_debug_endpoints:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Debug integration endpoints are disabled",
        )
    target_tenant_id = str(tenant_id or user.tenant_id or "").strip()
    if not target_tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="tenant_id is required")
    return build_federated_directory_snapshot_for_tenant(
        tenant_id=target_tenant_id,
        actor=user,
        limit_per_module=2000,
    )


@router.get("/federated-directory/global")
def get_federated_directory_snapshot_global(
    request: Request,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin")),
):
    settings = get_settings()
    if not settings.enable_integration_debug_endpoints:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Debug integration endpoints are disabled",
        )
    return build_federated_directory_snapshot_global(actor=user, max_tenants=50, limit_per_module=2000)


@router.post("/federated-directory/keycloak-sync")
def run_federated_directory_keycloak_sync(
    request: Request,
    tenant_id: Optional[str] = None,
    dry_run: Optional[bool] = None,
    max_users: Optional[int] = None,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin")),
):
    settings = get_settings()
    if not settings.enable_integration_debug_endpoints:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Debug integration endpoints are disabled",
        )
    if not settings.enable_federated_keycloak_sync and not bool(dry_run):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Federated Keycloak sync is disabled. Set ENABLE_FEDERATED_KEYCLOAK_SYNC=true or run dry_run=true.",
        )
    return sync_keycloak_from_federated_directory(
        actor=user,
        tenant_id=tenant_id,
        max_tenants=50,
        limit_per_module=2000,
        max_users=max_users,
        dry_run_override=dry_run,
    )


@router.get("/jit/audit")
def get_jit_audit_history(
    request: Request,
    tenant_id: Optional[str] = None,
    module_name: Optional[str] = None,
    limit: int = 50,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin")),
):
    settings = get_settings()
    if not settings.enable_integration_debug_endpoints:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Debug integration endpoints are disabled",
        )
    target_tenant = str(tenant_id or user.tenant_id or "").strip()
    if not target_tenant:
        raise HTTPException(status_code=400, detail="tenant_id is required")
    rows = automation_store.list_provisioning_audit(
        tenant_id=target_tenant,
        module_name=module_name,
        limit=max(1, min(int(limit or 50), 200)),
    )
    cooldown = automation_store.list_tenant_settings_by_prefix(
        tenant_id=target_tenant,
        setting_key_prefix="jit.cooldown.",
        limit=200,
    )
    return {
        "tenant_id": target_tenant,
        "module_name": str(module_name or "").strip().lower() or None,
        "rows_count": len(rows),
        "rows": rows,
        "cooldown_settings": cooldown,
        "tenant_links": automation_store.list_tenant_links(source_tenant_id=target_tenant, limit=100),
    }
