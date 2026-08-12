from typing import Any, Dict, Optional

from app.adapters.registry import get_eappraisal_adapter
from app.core.settings import get_settings
from app.models.tenant_mapping import TenantMapping


def _settings():
    return get_settings()


def get_appraisal_summary(mapping: TenantMapping, token: Optional[str]) -> Dict[str, Any]:
    return get_eappraisal_adapter().get_appraisal_summary(mapping, token)


def get_employee_appraisals(mapping: TenantMapping, employee_id: str, token: Optional[str]) -> Dict[str, Any]:
    return get_eappraisal_adapter().get_employee_appraisals(mapping, employee_id, token)


def get_my_appraisals(mapping: TenantMapping, token: Optional[str]) -> Dict[str, Any]:
    return get_eappraisal_adapter().get_my_appraisals(mapping, token)


def list_integration_tenants(token: Optional[str], *, limit: int = 500) -> Dict[str, Any]:
    """
    Inventory endpoint exposed by the Performance-Appraisal team:
    GET /api/hris/v1/integration/tenants
    """
    adapter = get_eappraisal_adapter()
    if hasattr(adapter, "list_integration_tenants"):
        return adapter.list_integration_tenants(token, limit=limit)  # type: ignore[attr-defined]
    return {"tenants": [], "total": 0}


def list_integration_tenant_users(
    mapping: TenantMapping,
    token: Optional[str],
    *,
    limit: int = 2000,
) -> Dict[str, Any]:
    adapter = get_eappraisal_adapter()
    if hasattr(adapter, "list_integration_tenant_users"):
        return adapter.list_integration_tenant_users(mapping, token, limit=limit)  # type: ignore[attr-defined]
    return {"tenant_id": mapping.tenant_id, "users": [], "total": 0}


def provision_tenant(payload: Dict[str, Any]) -> Dict[str, Any]:
    adapter = get_eappraisal_adapter()
    if not hasattr(adapter, "provision_tenant"):
        raise RuntimeError("Configured eAppraisal adapter does not support tenant provisioning")
    return adapter.provision_tenant(payload)  # type: ignore[attr-defined]
