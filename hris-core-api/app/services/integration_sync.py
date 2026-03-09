import logging
from typing import Any, Dict, Optional

from app.clients import eappraisal_client, eleave_client, srms_client
from app.core.auth import AuthenticatedUser
from app.services import automation_store
from app.services.identity_resolution import resolve_canonical_identity
from app.services.tenant_registry_client import get_tenant_mapping

logger = logging.getLogger(__name__)


def _record_probe_safe(*, tenant_id: str, module_name: str, probe_payload: Dict[str, Any]) -> None:
    try:
        automation_store.record_probe(
            tenant_id=tenant_id,
            module_name=module_name,
            ok=bool(probe_payload.get("ok")),
            detail=str(probe_payload.get("detail", "")),
            payload=probe_payload.get("payload") if isinstance(probe_payload, dict) else {},
        )
    except Exception as exc:
        logger.warning("Probe persistence skipped for %s: %s", module_name, exc)


def _safe_probe(name: str, fetcher) -> Dict[str, Any]:
    try:
        payload = fetcher()
        return {"ok": True, "detail": "reachable", "payload": payload}
    except Exception as exc:  # Keep robust scaffold behavior for sync views.
        logger.warning("Integration sync probe failed", extra={"probe": name, "error": str(exc)})
        return {"ok": False, "detail": str(exc)}


def build_sync_snapshot(
    *,
    tenant_id: str,
    actor: AuthenticatedUser,
    include_live_probes: bool = True,
) -> Dict[str, Any]:
    mapping = get_tenant_mapping(tenant_id)
    identity = resolve_canonical_identity(actor)
    modules_state = mapping.modules.model_dump()

    modules: Dict[str, Dict[str, Any]] = {}
    for module_name in ("srms", "eappraisal", "eleave"):
        module_meta = modules_state.get(module_name, {})
        enabled = (
            bool(module_meta.get("configured"))
            and bool(module_meta.get("ready"))
            and str(module_meta.get("status", "")).lower() == "active"
        )
        modules[module_name] = {
            "enabled": enabled,
            "configured": bool(module_meta.get("configured")),
            "ready": bool(module_meta.get("ready")),
            "status": module_meta.get("status", "inactive"),
            "probe": {"ok": True, "detail": "skipped"},
        }

    if include_live_probes:
        if modules["srms"]["enabled"]:
            modules["srms"]["probe"] = _safe_probe(
                "srms",
                lambda: srms_client.get_dashboard_summary(mapping, actor.raw_token),
            )
            _record_probe_safe(tenant_id=tenant_id, module_name="srms", probe_payload=modules["srms"]["probe"])
        if modules["eappraisal"]["enabled"]:
            modules["eappraisal"]["probe"] = _safe_probe(
                "eappraisal",
                lambda: eappraisal_client.get_appraisal_summary(mapping, actor.raw_token),
            )
            _record_probe_safe(tenant_id=tenant_id, module_name="eappraisal", probe_payload=modules["eappraisal"]["probe"])
        if modules["eleave"]["enabled"]:
            modules["eleave"]["probe"] = _safe_probe(
                "eleave",
                lambda: eleave_client.get_leave_summary(mapping, actor.raw_token),
            )
            _record_probe_safe(tenant_id=tenant_id, module_name="eleave", probe_payload=modules["eleave"]["probe"])

    active_modules = [name for name, data in modules.items() if data["enabled"]]
    overall_ok = all(modules[name]["probe"].get("ok", False) for name in active_modules) if active_modules else True

    recommended_actions = []
    for module_name in active_modules:
        if not modules[module_name]["probe"].get("ok", False):
            recommended_actions.append(f"Investigate {module_name} auth/connectivity and tenant mapping.")

    return {
        "overall_ok": overall_ok,
        "tenant": {
            "tenant_id": tenant_id,
            "code": mapping.code,
            "name": mapping.name,
            "lifecycle_status": mapping.lifecycle_status,
            "is_active": mapping.is_active,
        },
        "identity_context": {
            "actor_sub": actor.sub,
            "actor_role": actor.effective_role,
            "canonical_person_id": identity.person_id,
            "srms_employee_id": identity.srms.employee_id,
            "eappraisal_employee_id": identity.eappraisal.employee_id,
            "eleave_employee_id": identity.eleave.employee_id,
        },
        "modules": modules,
        "recommended_actions": recommended_actions[:5],
    }
