from typing import Any, Dict, List, Optional, Tuple

from app.clients import srms_client
from app.core.auth import AuthenticatedUser
from app.services.tenant_registry_client import get_tenant_mapping, list_tenant_mappings


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _registry_keys(item: Dict[str, Any]) -> Tuple[str, str, str]:
    return (
        _norm(item.get("tenant_id")),
        _norm(item.get("code")),
        _norm(item.get("name")),
    )


def _srms_keys(item: Dict[str, Any]) -> Tuple[str, str, str]:
    return (
        _norm(item.get("tenant_id")),
        _norm(item.get("code")),
        _norm(item.get("name")),
    )


def _match_srms_org(registry_tenant: Dict[str, Any], srms_orgs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    tenant_id, code, name = _registry_keys(registry_tenant)
    for org in srms_orgs:
        org_tid, org_code, org_name = _srms_keys(org)
        if tenant_id and org_tid and tenant_id == org_tid:
            return org
    for org in srms_orgs:
        _, org_code, org_name = _srms_keys(org)
        if code and org_code and code == org_code:
            return org
        if name and org_name and name == org_name:
            return org
    return None


def build_drift_snapshot(actor: AuthenticatedUser, *, max_registry_tenants: int = 500) -> Dict[str, Any]:
    registry_rows = list_tenant_mappings(limit=max_registry_tenants)
    registry = [
        {
            "tenant_id": row.tenant_id,
            "code": row.code,
            "name": row.name,
            "lifecycle_status": row.lifecycle_status,
            "is_active": row.is_active,
        }
        for row in registry_rows
    ]
    srms_payload = srms_client.list_organizations(actor.raw_token)
    srms_orgs = srms_payload.get("organizations", []) if isinstance(srms_payload, dict) else []
    srms_orgs = [row for row in srms_orgs if isinstance(row, dict)]

    matched: List[Dict[str, Any]] = []
    registry_only: List[Dict[str, Any]] = []
    consumed_srms_ids = set()

    for tenant in registry:
        match = _match_srms_org(tenant, srms_orgs)
        if not match:
            registry_only.append(tenant)
            continue
        org_id = _norm(match.get("tenant_id") or match.get("code") or match.get("name"))
        if org_id:
            consumed_srms_ids.add(org_id)
        matched.append(
            {
                "registry": tenant,
                "srms": {
                    "tenant_id": match.get("tenant_id"),
                    "code": match.get("code"),
                    "name": match.get("name"),
                    "status": match.get("status"),
                },
            }
        )

    srms_only: List[Dict[str, Any]] = []
    for org in srms_orgs:
        org_id = _norm(org.get("tenant_id") or org.get("code") or org.get("name"))
        if org_id and org_id in consumed_srms_ids:
            continue
        if _match_srms_org(org, registry):  # type: ignore[arg-type]
            continue
        srms_only.append(
            {
                "tenant_id": org.get("tenant_id"),
                "code": org.get("code"),
                "name": org.get("name"),
                "status": org.get("status"),
            }
        )

    recommended_actions: List[str] = []
    if registry_only:
        recommended_actions.append("Provision missing SRMS tenant records for registry-only tenants.")
    if srms_only:
        recommended_actions.append("Import SRMS-only tenants into Tenant Registry after validation.")

    return {
        "overall_in_sync": not registry_only and not srms_only,
        "summary": {
            "registry_total": len(registry),
            "srms_total": len(srms_orgs),
            "matched": len(matched),
            "registry_only": len(registry_only),
            "srms_only": len(srms_only),
        },
        "matched": matched[:200],
        "registry_only": registry_only[:200],
        "srms_only": srms_only[:200],
        "recommended_actions": recommended_actions,
    }


def build_tenant_reconcile_plan(tenant_id: str, actor: AuthenticatedUser) -> Dict[str, Any]:
    mapping = get_tenant_mapping(tenant_id)
    srms_payload = srms_client.list_organizations(actor.raw_token)
    srms_orgs = srms_payload.get("organizations", []) if isinstance(srms_payload, dict) else []
    srms_orgs = [row for row in srms_orgs if isinstance(row, dict)]
    registry_tenant = {
        "tenant_id": mapping.tenant_id,
        "code": mapping.code,
        "name": mapping.name,
        "lifecycle_status": mapping.lifecycle_status,
        "is_active": mapping.is_active,
    }
    match = _match_srms_org(registry_tenant, srms_orgs)
    if not match:
        return {
            "tenant_id": tenant_id,
            "in_sync": False,
            "registry": registry_tenant,
            "srms": None,
            "actions": [
                "Create SRMS tenant record or configure tenant mapping so this tenant is discoverable from SRMS.",
            ],
        }
    drift_fields: List[str] = []
    if _norm(match.get("code")) != _norm(registry_tenant.get("code")):
        drift_fields.append("code")
    if _norm(match.get("name")) != _norm(registry_tenant.get("name")):
        drift_fields.append("name")
    in_sync = len(drift_fields) == 0
    actions = []
    if not in_sync:
        actions.append(f"Resolve tenant metadata drift fields: {', '.join(drift_fields)}.")
    return {
        "tenant_id": tenant_id,
        "in_sync": in_sync,
        "registry": registry_tenant,
        "srms": {
            "tenant_id": match.get("tenant_id"),
            "code": match.get("code"),
            "name": match.get("name"),
            "status": match.get("status"),
        },
        "drift_fields": drift_fields,
        "actions": actions,
    }
