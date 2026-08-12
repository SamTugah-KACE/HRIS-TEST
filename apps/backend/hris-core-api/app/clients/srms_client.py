from typing import Any, Dict, Optional

from fastapi import HTTPException, status

from app.adapters.registry import get_srms_adapter
from app.core.settings import get_settings
from app.models.tenant_mapping import TenantMapping


def _settings():
    return get_settings()


def _require_srms_config() -> None:
    settings = _settings()
    if not settings.srms_base_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SRMS_BASE_URL is required; runtime stub data is not supported.",
        )


def get_employee(mapping: TenantMapping, employee_id: str, token: Optional[str]) -> Dict[str, Any]:
    _require_srms_config()
    return get_srms_adapter().get_employee(mapping, employee_id, token)


def get_self_employee_comprehensive(mapping: TenantMapping, token: Optional[str]) -> Dict[str, Any]:
    _require_srms_config()
    adapter = get_srms_adapter()
    if hasattr(adapter, "get_self_employee_comprehensive"):
        return adapter.get_self_employee_comprehensive(mapping, token)  # type: ignore[attr-defined]
    return {}


def list_employees(
    mapping: TenantMapping,
    token: Optional[str],
    search: str = "",
    department: str = "",
    emp_status: str = "active",
    page: int = 1,
    page_size: int = 20,
) -> Dict[str, Any]:
    _require_srms_config()
    return get_srms_adapter().list_employees(mapping, token, search, department, emp_status, page, page_size)


def list_team_employees(
    mapping: TenantMapping,
    token: Optional[str],
    *,
    manager_employee_id: Optional[str],
    search: str = "",
    department: str = "",
    emp_status: str = "active",
    page: int = 1,
    page_size: int = 20,
) -> Dict[str, Any]:
    _require_srms_config()
    adapter = get_srms_adapter()
    if hasattr(adapter, "list_team_employees"):
        return adapter.list_team_employees(  # type: ignore[attr-defined]
            mapping,
            token,
            manager_employee_id=manager_employee_id,
            search=search,
            department=department,
            emp_status=emp_status,
            page=page,
            page_size=page_size,
        )
    return {
        "employees": [],
        "total": 0,
        "page": page,
        "page_size": page_size,
        "total_pages": 1,
        "scope": "team",
        "source": "not_configured",
        "message": "Team reporting structure is not available for this tenant.",
    }


def get_dashboard_summary(mapping: TenantMapping, token: Optional[str]) -> Dict[str, Any]:
    _require_srms_config()
    return get_srms_adapter().get_dashboard_summary(mapping, token)


def list_organizations(token: Optional[str]) -> Dict[str, Any]:
    _require_srms_config()
    return get_srms_adapter().list_organizations(token)


def list_integration_tenants(token: Optional[str]) -> Dict[str, Any]:
    _require_srms_config()
    adapter = get_srms_adapter()
    # Guard for adapter implementations that may not have this method yet.
    if hasattr(adapter, "list_integration_tenants"):
        return adapter.list_integration_tenants(token)  # type: ignore[attr-defined]
    return adapter.list_organizations(token)


def provision_tenant(payload: Dict[str, Any]) -> Dict[str, Any]:
    _require_srms_config()
    adapter = get_srms_adapter()
    if not hasattr(adapter, "provision_tenant"):
        raise RuntimeError("Configured SRMS adapter does not support tenant provisioning")
    return adapter.provision_tenant(payload)  # type: ignore[attr-defined]


def list_tenant_users(
    tenant_id: str,
    token: Optional[str],
    limit: int = 2000,
    *,
    tenant_slug: Optional[str] = None,
    tenant_code: Optional[str] = None,
) -> Dict[str, Any]:
    _require_srms_config()
    adapter = get_srms_adapter()
    if hasattr(adapter, "list_tenant_users"):
        return adapter.list_tenant_users(  # type: ignore[attr-defined]
            tenant_id,
            token,
            limit=limit,
            tenant_slug=tenant_slug,
            tenant_code=tenant_code,
        )
    return {"tenant_id": tenant_id, "users": [], "total": 0}


def provision_tenant_user(
    tenant_id: str,
    token: Optional[str],
    *,
    email: str,
    username: str,
    first_name: str = "",
    last_name: str = "",
    user_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    tenant_slug: Optional[str] = None,
    tenant_code: Optional[str] = None,
) -> Dict[str, Any]:
    _require_srms_config()
    adapter = get_srms_adapter()
    if hasattr(adapter, "provision_tenant_user"):
        return adapter.provision_tenant_user(  # type: ignore[attr-defined]
            tenant_id,
            token,
            email=email,
            username=username,
            first_name=first_name,
            last_name=last_name,
            user_id=user_id,
            idempotency_key=idempotency_key,
            tenant_slug=tenant_slug,
            tenant_code=tenant_code,
        )
    return {
        "tenant_id": tenant_id,
        "provisioned": False,
        "user_id": user_id or "",
        "email": str(email or "").strip().lower(),
        "username": str(username or "").strip().lower(),
        "message": "SRMS adapter does not support provision_tenant_user",
        "raw": {},
    }
