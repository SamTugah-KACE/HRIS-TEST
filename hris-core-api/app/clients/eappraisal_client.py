from typing import Any, Dict, Optional

from app.adapters.registry import get_eappraisal_adapter
from app.core.settings import get_settings
from app.models.tenant_mapping import TenantMapping


def _settings():
    return get_settings()


def _should_use_stub(token: Optional[str]) -> bool:
    settings = _settings()
    has_live_auth = bool(token or settings.eappraisal_service_token or settings.eappraisal_refresh_token)
    if not settings.eappraisal_domain_template:
        return True
    if settings.use_stub_data and not has_live_auth:
        return True
    return False


def get_appraisal_summary(mapping: TenantMapping, token: Optional[str]) -> Dict[str, Any]:
    settings = _settings()
    if settings.eappraisal_fixture_file:
        return get_eappraisal_adapter().get_appraisal_summary(mapping, token)

    if _should_use_stub(token):
        return {
            "active_cycles": 1,
            "pending_reviews": 12,
            "completed_reviews": 88,
            "overdue_reviews": 3,
            "average_score": 3.9,
            "completion_rate": 88.0,
        }

    return get_eappraisal_adapter().get_appraisal_summary(mapping, token)


def get_employee_appraisals(mapping: TenantMapping, employee_id: str, token: Optional[str]) -> Dict[str, Any]:
    settings = _settings()
    if settings.eappraisal_fixture_file:
        return get_eappraisal_adapter().get_employee_appraisals(mapping, employee_id, token)

    if _should_use_stub(token):
        return {
            "employee_id": employee_id,
            "appraisals": [
                {"cycle_name": "2025 Annual Review", "overall_score": 4.2, "rating": "Exceeds Expectations", "status": "completed", "date": "2025-12-15"},
                {"cycle_name": "2024 Annual Review", "overall_score": 3.8, "rating": "Meets Expectations", "status": "completed", "date": "2024-12-10"},
                {"cycle_name": "2026 Mid-Year", "overall_score": None, "rating": None, "status": "in_progress", "date": "2026-06-30"},
            ],
        }

    return get_eappraisal_adapter().get_employee_appraisals(mapping, employee_id, token)


def get_my_appraisals(mapping: TenantMapping, token: Optional[str]) -> Dict[str, Any]:
    settings = _settings()
    if settings.eappraisal_fixture_file:
        return get_eappraisal_adapter().get_my_appraisals(mapping, token)

    if _should_use_stub(token):
        return {
            "current_cycle": {"title": "2025/2026 Appraisal Cycle", "due_date": "Mar 30, 2026", "overall_progress": 40},
            "sections": [
                {"name": "Key Result Areas (KRA)", "weight": 40, "status": "completed", "score": 4.1, "maxScore": 5},
                {"name": "Core Competencies", "weight": 25, "status": "completed", "score": 3.8, "maxScore": 5},
                {"name": "Leadership & Initiative", "weight": 15, "status": "in_progress", "score": None, "maxScore": 5},
            ],
            "goals": [],
        }

    return get_eappraisal_adapter().get_my_appraisals(mapping, token)
