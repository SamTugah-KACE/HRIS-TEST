import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.clients import eappraisal_client, eleave_client, srms_client
from app.core.auth import AuthenticatedUser, require_roles
from app.core.settings import get_settings
from app.services.integration_sync import build_sync_snapshot
from app.services.tenant_registry_client import get_tenant_mapping

router = APIRouter(prefix="/debug/integrations", tags=["integration-debug"])
logger = logging.getLogger(__name__)


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
            "fixture_mode": bool(settings.eappraisal_fixture_file),
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
