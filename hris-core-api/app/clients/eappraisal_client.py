from typing import Any, Dict, Optional

import httpx
from fastapi import HTTPException, status

from app.core.settings import get_settings
from app.models.tenant_mapping import TenantMapping

settings = get_settings()


def _get_http_client() -> httpx.Client:
    return httpx.Client(timeout=settings.http_client_timeout_seconds)


def _build_base_url(mapping: TenantMapping) -> str:
    if not mapping.eappraisal_subdomain:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="eAppraisal not configured for this tenant",
        )
    return settings.eappraisal_domain_template.format(subdomain=mapping.eappraisal_subdomain)


def get_appraisal_summary(mapping: TenantMapping, token: Optional[str]) -> Dict[str, Any]:
    if settings.use_stub_data or not settings.eappraisal_domain_template:
        return {
            "active_cycles": 1,
            "pending_reviews": 12,
            "completed_reviews": 88,
            "overdue_reviews": 3,
            "average_score": 3.9,
            "completion_rate": 88.0,
        }

    base_url = _build_base_url(mapping)
    url = f"{base_url}/api/hris/appraisals/summary"
    headers: Dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    with _get_http_client() as client:
        response = client.get(url, headers=headers)

    try:
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Error calling eAppraisal: {exc}") from exc

    return response.json()


def get_employee_appraisals(mapping: TenantMapping, employee_id: str, token: Optional[str]) -> Dict[str, Any]:
    if settings.use_stub_data or not settings.eappraisal_domain_template:
        return {
            "employee_id": employee_id,
            "appraisals": [
                {"cycle_name": "2025 Annual Review", "overall_score": 4.2, "rating": "Exceeds Expectations", "status": "completed", "date": "2025-12-15"},
                {"cycle_name": "2024 Annual Review", "overall_score": 3.8, "rating": "Meets Expectations", "status": "completed", "date": "2024-12-10"},
                {"cycle_name": "2026 Mid-Year", "overall_score": None, "rating": None, "status": "in_progress", "date": "2026-06-30"},
            ],
        }

    base_url = _build_base_url(mapping)
    url = f"{base_url}/api/hris/employees/{employee_id}/appraisals"
    headers: Dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    with _get_http_client() as client:
        response = client.get(url, headers=headers)

    if response.status_code == 404:
        return {"employee_id": employee_id, "appraisals": []}

    try:
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Error calling eAppraisal: {exc}") from exc

    return response.json()
