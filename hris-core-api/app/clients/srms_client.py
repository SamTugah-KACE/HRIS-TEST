from typing import Any, Dict, Optional

import httpx
from fastapi import HTTPException, status

from app.core.settings import get_settings
from app.models.tenant_mapping import TenantMapping

settings = get_settings()


def _get_http_client() -> httpx.Client:
    return httpx.Client(timeout=settings.http_client_timeout_seconds)


def get_employee(mapping: TenantMapping, employee_id: str, token: Optional[str]) -> Dict[str, Any]:
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

    url = f"{settings.srms_base_url}/api/hris/employees/{employee_id}"
    headers: Dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    with _get_http_client() as client:
        response = client.get(url, headers=headers)

    if response.status_code == 404:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found in SRMS")
    try:
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Error calling SRMS: {exc}") from exc

    return response.json()


def list_employees(
    mapping: TenantMapping,
    token: Optional[str],
    search: str = "",
    department: str = "",
    emp_status: str = "active",
    page: int = 1,
    page_size: int = 20,
) -> Dict[str, Any]:
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

    url = f"{settings.srms_base_url}/api/hris/employees"
    params = {"search": search, "department": department, "status": emp_status, "page": page, "page_size": page_size}
    headers: Dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    with _get_http_client() as client:
        response = client.get(url, headers=headers, params=params)

    try:
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Error calling SRMS: {exc}") from exc

    return response.json()


def get_dashboard_summary(mapping: TenantMapping, token: Optional[str]) -> Dict[str, Any]:
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

    url = f"{settings.srms_base_url}/api/hris/dashboard/summary"
    headers: Dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    with _get_http_client() as client:
        response = client.get(url, headers=headers)

    try:
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Error calling SRMS: {exc}") from exc

    return response.json()
