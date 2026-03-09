from typing import Any, Dict, Optional

from app.adapters.registry import get_srms_adapter
from app.core.settings import get_settings
from app.models.tenant_mapping import TenantMapping


def _settings():
    return get_settings()


def get_employee(mapping: TenantMapping, employee_id: str, token: Optional[str]) -> Dict[str, Any]:
    settings = _settings()
    if settings.use_stub_data or settings.srms_base_url is None:
        return {
            "employee_id": employee_id,
            "staff_id": f"STF-{employee_id[:6].upper()}",
            "full_name": "Kwame Asante",
            "first_name": "Kwame",
            "last_name": "Asante",
            "email": "kwame.asante@example.com",
            "organization": mapping.name,
            "branch": "Head Office",
            "department": "Information Technology",
            "unit": "Software Development",
            "rank": "Senior Officer",
            "position": "Senior Software Engineer",
            "employee_type": "Full-Time",
            "status": "Active",
            "hire_date": "2021-03-15",
            "phone": "+233 24 123 4567",
            "gender": "Male",
        }

    return get_srms_adapter().get_employee(mapping, employee_id, token)


def get_self_employee_comprehensive(mapping: TenantMapping, token: Optional[str]) -> Dict[str, Any]:
    settings = _settings()
    if settings.use_stub_data or settings.srms_base_url is None:
        return {}
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
    settings = _settings()
    if settings.use_stub_data or settings.srms_base_url is None:
        all_employees = [
            {"employee_id": "e001", "staff_id": "STF-001", "full_name": "Kwame Asante", "email": "kwame.asante@example.com", "department": "Information Technology", "branch": "Head Office", "rank": "Senior Officer", "status": "Active", "hire_date": "2021-03-15"},
            {"employee_id": "e002", "staff_id": "STF-002", "full_name": "Ama Mensah", "email": "ama.mensah@example.com", "department": "Human Resources", "branch": "Head Office", "rank": "Principal Officer", "status": "Active", "hire_date": "2019-06-01"},
            {"employee_id": "e003", "staff_id": "STF-003", "full_name": "Kofi Osei", "email": "kofi.osei@example.com", "department": "Finance", "branch": "Head Office", "rank": "Senior Officer", "status": "Active", "hire_date": "2020-01-10"},
            {"employee_id": "e004", "staff_id": "STF-004", "full_name": "Abena Boateng", "email": "abena.boateng@example.com", "department": "Information Technology", "branch": "Kumasi Branch", "rank": "Officer", "status": "Active", "hire_date": "2022-08-20"},
            {"employee_id": "e005", "staff_id": "STF-005", "full_name": "Yaw Adjei", "email": "yaw.adjei@example.com", "department": "Administration", "branch": "Head Office", "rank": "Chief Officer", "status": "Active", "hire_date": "2015-04-12"},
            {"employee_id": "e006", "staff_id": "STF-006", "full_name": "Akua Darko", "email": "akua.darko@example.com", "department": "Finance", "branch": "Tamale Branch", "rank": "Officer", "status": "Active", "hire_date": "2023-02-01"},
            {"employee_id": "e007", "staff_id": "STF-007", "full_name": "Nana Appiah", "email": "nana.appiah@example.com", "department": "Human Resources", "branch": "Head Office", "rank": "Deputy Director", "status": "Active", "hire_date": "2014-09-05"},
            {"employee_id": "e008", "staff_id": "STF-008", "full_name": "Efua Owusu", "email": "efua.owusu@example.com", "department": "Legal", "branch": "Head Office", "rank": "Senior Officer", "status": "Active", "hire_date": "2021-11-30"},
            {"employee_id": "e009", "staff_id": "STF-009", "full_name": "Kojo Frimpong", "email": "kojo.frimpong@example.com", "department": "Information Technology", "branch": "Head Office", "rank": "Director", "status": "Active", "hire_date": "2012-07-18"},
            {"employee_id": "e010", "staff_id": "STF-010", "full_name": "Adwoa Poku", "email": "adwoa.poku@example.com", "department": "Administration", "branch": "Kumasi Branch", "rank": "Officer", "status": "Inactive", "hire_date": "2020-05-22"},
        ]

        filtered = all_employees
        if search:
            q = search.lower()
            filtered = [e for e in filtered if q in e["full_name"].lower() or q in e["staff_id"].lower() or q in e["email"].lower()]
        if department:
            filtered = [e for e in filtered if department.lower() in e["department"].lower()]
        if emp_status and emp_status != "all":
            filtered = [e for e in filtered if e["status"].lower() == emp_status.lower()]

        total = len(filtered)
        start = (page - 1) * page_size
        paged = filtered[start : start + page_size]

        return {
            "employees": paged,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        }

    return get_srms_adapter().list_employees(mapping, token, search, department, emp_status, page, page_size)


def get_dashboard_summary(mapping: TenantMapping, token: Optional[str]) -> Dict[str, Any]:
    settings = _settings()
    if settings.use_stub_data or settings.srms_base_url is None:
        return {
            "total_employees": 125,
            "active_employees": 120,
            "inactive_employees": 5,
            "branches": 3,
            "departments": 8,
            "new_hires_this_month": 4,
            "pending_enlistments": 7,
        }

    return get_srms_adapter().get_dashboard_summary(mapping, token)


def list_organizations(token: Optional[str]) -> Dict[str, Any]:
    settings = _settings()
    if settings.use_stub_data or settings.srms_base_url is None:
        organizations = [
            {
                "tenant_id": "11111111-1111-1111-1111-111111111111",
                "name": "GI-KACE",
                "code": "GI-KACE",
                "slug": "gi-kace",
                "status": "active",
                "modules": {"srms": True, "eappraisal": True, "eleave": True},
            },
            {
                "tenant_id": "22222222-2222-2222-2222-222222222222",
                "name": "Ministry of Finance",
                "code": "MOF",
                "slug": "mof",
                "status": "active",
                "modules": {"srms": True, "eappraisal": False, "eleave": True},
            },
            {
                "tenant_id": "33333333-3333-3333-3333-333333333333",
                "name": "Test Organization",
                "code": "TEST-ORG",
                "slug": "test-org",
                "status": "inactive",
                "modules": {"srms": True, "eappraisal": True, "eleave": False},
            },
        ]
        return {
            "organizations": organizations,
            "summary": {
                "total": len(organizations),
                "active": 2,
                "inactive": 1,
            },
        }

    return get_srms_adapter().list_organizations(token)


def list_integration_tenants(token: Optional[str]) -> Dict[str, Any]:
    settings = _settings()
    if settings.use_stub_data or settings.srms_base_url is None:
        return list_organizations(token)
    adapter = get_srms_adapter()
    # Guard for adapter implementations that may not have this method yet.
    if hasattr(adapter, "list_integration_tenants"):
        return adapter.list_integration_tenants(token)  # type: ignore[attr-defined]
    return adapter.list_organizations(token)


def list_tenant_users(
    tenant_id: str,
    token: Optional[str],
    limit: int = 2000,
    *,
    tenant_slug: Optional[str] = None,
    tenant_code: Optional[str] = None,
) -> Dict[str, Any]:
    settings = _settings()
    if settings.use_stub_data or settings.srms_base_url is None:
        users = [
            {"user_id": "u001", "username": "employee", "email": "employee@example.com", "is_active": True},
            {"user_id": "u002", "username": "manager", "email": "manager@example.com", "is_active": True},
        ]
        return {"tenant_id": tenant_id, "users": users[: max(1, min(limit, len(users)))], "total": len(users)}

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
