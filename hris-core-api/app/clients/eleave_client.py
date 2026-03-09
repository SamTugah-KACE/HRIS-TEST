from typing import Any, Dict, Optional

from app.adapters.registry import get_eleave_adapter
from app.core.settings import get_settings
from app.models.tenant_mapping import TenantMapping


def _settings():
    return get_settings()


def get_leave_summary(mapping: TenantMapping, token: Optional[str]) -> Dict[str, Any]:
    settings = _settings()
    if settings.use_stub_data or not settings.eleave_domain_template:
        return {
            "total_leaves_this_year": 320,
            "approved_leaves": 280,
            "pending_leaves": 25,
            "rejected_leaves": 10,
            "cancelled_leaves": 5,
            "leave_utilization_rate": 72.5,
        }

    return get_eleave_adapter().get_leave_summary(mapping, token)


def get_employee_leave_history(mapping: TenantMapping, employee_id: str, token: Optional[str]) -> Dict[str, Any]:
    settings = _settings()
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

    return get_eleave_adapter().get_employee_leave_history(mapping, employee_id, token)
