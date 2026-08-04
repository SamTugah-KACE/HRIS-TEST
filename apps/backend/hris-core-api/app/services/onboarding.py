from typing import Dict, List

from app.core.settings import get_settings
from app.models.tenant_mapping import TenantMapping


def _module_probe_target(module_name: str, mapping: TenantMapping) -> str:
    settings = get_settings()
    if module_name == "srms":
        return settings.srms_base_url or ""
    if module_name == "eappraisal":
        if not settings.eappraisal_domain_template:
            return ""
        return settings.eappraisal_domain_template.format(subdomain=mapping.eappraisal_subdomain or "")
    if module_name == "eleave":
        if not settings.eleave_domain_template:
            return ""
        return settings.eleave_domain_template.format(subdomain=mapping.eleave_subdomain or "")
    return ""


def build_onboarding_readiness(tenant: TenantMapping) -> Dict[str, object]:
    checks: List[Dict[str, object]] = []
    checks.append(
        {
            "name": "tenant_active",
            "ok": tenant.is_tenant_active(),
            "detail": f"Tenant lifecycle is '{tenant.lifecycle_status}'",
        }
    )

    for module_name in ("srms", "eappraisal", "eleave"):
        module = getattr(tenant.modules, module_name)
        endpoint = _module_probe_target(module_name, tenant)
        checks.append(
            {
                "name": f"{module_name}_configured",
                "ok": module.configured and bool(endpoint),
                "detail": f"status={module.status}, ready={module.ready}, endpoint={'set' if endpoint else 'missing'}",
            }
        )
        checks.append(
            {
                "name": f"{module_name}_ready",
                "ok": module.ready and module.status.lower() == "active",
                "detail": f"status={module.status}, ready={module.ready}",
            }
        )

    all_ok = all(bool(check["ok"]) for check in checks)
    return {
        "tenant_id": tenant.tenant_id,
        "lifecycle_status": tenant.lifecycle_status,
        "ready_for_activation": all_ok,
        "checks": checks,
    }
