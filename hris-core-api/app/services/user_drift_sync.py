from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from app.clients import eappraisal_client, eleave_client, srms_client
from app.core.auth import AuthenticatedUser
from app.models.tenant_mapping import TenantMapping
from app.services.tenant_registry_client import get_tenant_mapping, list_tenant_mappings


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _canonical_user_key(employee: Dict[str, Any]) -> str:
    return (
        _norm(employee.get("employee_id"))
        or _norm(employee.get("staff_id"))
        or _norm(employee.get("email"))
    )


def _module_user_presence(
    module_name: str,
    mapping: TenantMapping,
    employee_key: str,
    token: Optional[str],
) -> Dict[str, Any]:
    try:
        if module_name == "eappraisal":
            payload = eappraisal_client.get_employee_appraisals(mapping, employee_key, token)
            appraisals = payload.get("appraisals", []) if isinstance(payload, dict) else []
            return {"ok": True, "present": True, "evidence_count": len(appraisals)}
        if module_name == "eleave":
            payload = eleave_client.get_employee_leave_history(mapping, employee_key, token)
            history = payload.get("leaves", []) if isinstance(payload, dict) else []
            return {"ok": True, "present": True, "evidence_count": len(history)}
        return {"ok": False, "present": False, "error": f"Unsupported module '{module_name}'"}
    except HTTPException as exc:
        if int(exc.status_code) == 404:
            return {
                "ok": True,
                "present": False,
                "reason": "not_found",
                "error": str(exc.detail),
            }
        return {"ok": False, "present": False, "reason": "upstream_error", "error": str(exc.detail)}
    except Exception as exc:
        return {"ok": False, "present": False, "reason": "upstream_error", "error": str(exc)}


def build_tenant_user_drift(
    *,
    mapping: TenantMapping,
    token: Optional[str],
    max_users: int = 200,
) -> Dict[str, Any]:
    roster = srms_client.list_employees(
        mapping,
        token,
        search="",
        department="",
        emp_status="all",
        page=1,
        page_size=max(1, min(max_users, 500)),
    )
    employees = roster.get("employees", []) if isinstance(roster, dict) else []
    employees = [row for row in employees if isinstance(row, dict)]

    module_stats = {
        "eappraisal": {"ok": 0, "missing": 0, "errors": 0},
        "eleave": {"ok": 0, "missing": 0, "errors": 0},
    }
    per_user: List[Dict[str, Any]] = []

    for row in employees[: max(1, max_users)]:
        key = _canonical_user_key(row)
        if not key:
            continue
        eapp = _module_user_presence("eappraisal", mapping, key, token)
        elea = _module_user_presence("eleave", mapping, key, token)
        for module_name, result in (("eappraisal", eapp), ("eleave", elea)):
            if result.get("ok") and result.get("present"):
                module_stats[module_name]["ok"] += 1
            elif result.get("ok"):
                module_stats[module_name]["missing"] += 1
            else:
                module_stats[module_name]["errors"] += 1
        per_user.append(
            {
                "employee_id": row.get("employee_id"),
                "staff_id": row.get("staff_id"),
                "email": row.get("email"),
                "eappraisal": eapp,
                "eleave": elea,
            }
        )

    return {
        "tenant_id": mapping.tenant_id,
        "tenant_code": mapping.code,
        "tenant_name": mapping.name,
        "users_scanned": len(per_user),
        "module_stats": module_stats,
        "users": per_user[:200],
    }


def build_global_user_drift(
    *,
    actor: AuthenticatedUser,
    max_tenants: int = 200,
    max_users_per_tenant: int = 200,
) -> Dict[str, Any]:
    tenants = list_tenant_mappings(limit=max(1, min(max_tenants, 2000)))
    active = [tenant for tenant in tenants if tenant.is_tenant_active()]
    snapshots: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []

    for tenant in active[: max(1, max_tenants)]:
        try:
            snapshots.append(
                build_tenant_user_drift(
                    mapping=tenant,
                    token=actor.raw_token,
                    max_users=max_users_per_tenant,
                )
            )
        except Exception as exc:
            errors.append({"tenant_id": tenant.tenant_id, "error": str(exc)})

    return {
        "summary": {
            "tenants_scanned": len(snapshots),
            "tenants_failed": len(errors),
        },
        "tenants": snapshots,
        "errors": errors[:200],
    }


def build_tenant_user_reconcile_plan(
    *,
    tenant_id: str,
    actor: AuthenticatedUser,
    max_users: int = 200,
) -> Dict[str, Any]:
    mapping = get_tenant_mapping(tenant_id)
    drift = build_tenant_user_drift(
        mapping=mapping,
        token=actor.raw_token,
        max_users=max_users,
    )
    module_stats = drift.get("module_stats", {})
    actions: List[str] = []
    for module_name in ("eappraisal", "eleave"):
        stats = module_stats.get(module_name, {})
        if int(stats.get("errors", 0)) > 0:
            actions.append(f"Fix {module_name} connectivity/auth for tenant {mapping.code}.")
        if int(stats.get("missing", 0)) > 0:
            actions.append(f"Provision or map missing {module_name} user accounts from SRMS roster.")

    return {
        "tenant_id": tenant_id,
        "in_sync": len(actions) == 0,
        "drift": drift,
        "actions": actions,
    }
