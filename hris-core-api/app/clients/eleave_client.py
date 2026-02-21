from typing import Any, Dict, Optional

import httpx
from fastapi import HTTPException

from app.core.settings import get_settings
from app.models.tenant_mapping import TenantMapping

settings = get_settings()


def _get_http_client() -> httpx.Client:
    return httpx.Client(timeout=settings.http_client_timeout_seconds)


def _build_base_url(mapping: TenantMapping) -> str:
    if not settings.eleave_domain_template or not mapping.eleave_subdomain:
        raise HTTPException(status_code=404, detail="eLeave not configured for this tenant")
    return settings.eleave_domain_template.format(subdomain=mapping.eleave_subdomain)


def get_leave_summary(mapping: TenantMapping, token: Optional[str]) -> Dict[str, Any]:
    if settings.use_stub_data or not settings.eleave_domain_template:
        return {
            "total_leaves_this_year": 320,
            "approved_leaves": 280,
            "pending_leaves": 25,
            "rejected_leaves": 10,
            "cancelled_leaves": 5,
            "leave_utilization_rate": 72.5,
        }

    base_url = _build_base_url(mapping)
    url = f"{base_url}/hris/leaves/summary"
    headers: Dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    with _get_http_client() as client:
        response = client.get(url, headers=headers)

    try:
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Error calling eLeave: {exc}") from exc

    return response.json()


def get_employee_leave_history(mapping: TenantMapping, employee_id: str, token: Optional[str]) -> Dict[str, Any]:
    if settings.use_stub_data or not settings.eleave_domain_template:
        return {
            "employee_id": employee_id,
            "balance": {"annual": 15, "sick": 10, "casual": 5, "maternity": 90},
            "used": {"annual": 8, "sick": 2, "casual": 3, "maternity": 0},
            "leaves": [
                {"type": "Annual", "days": 5, "status": "approved", "start_date": "2026-01-06", "end_date": "2026-01-10"},
                {"type": "Sick", "days": 2, "status": "approved", "start_date": "2025-11-18", "end_date": "2025-11-19"},
                {"type": "Annual", "days": 3, "status": "approved", "start_date": "2025-08-11", "end_date": "2025-08-13"},
                {"type": "Casual", "days": 1, "status": "pending", "start_date": "2026-02-20", "end_date": "2026-02-20"},
            ],
        }

    base_url = _build_base_url(mapping)
    url = f"{base_url}/hris/employees/{employee_id}/leaves"
    headers: Dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    with _get_http_client() as client:
        response = client.get(url, headers=headers)

    if response.status_code == 404:
        return {"employee_id": employee_id, "leaves": []}

    try:
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Error calling eLeave: {exc}") from exc

    return response.json()
