from typing import Any, Dict, Optional

from fastapi import HTTPException, status

from app.adapters.registry import get_eleave_adapter
from app.core.settings import get_settings
from app.models.tenant_mapping import TenantMapping


def _settings():
    return get_settings()


def _require_eleave_config() -> None:
    settings = _settings()
    if not settings.eleave_domain_template:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ELEAVE_DOMAIN_TEMPLATE is required; runtime stub data is not supported.",
        )


def get_leave_summary(mapping: TenantMapping, token: Optional[str]) -> Dict[str, Any]:
    _require_eleave_config()
    return get_eleave_adapter().get_leave_summary(mapping, token)


def get_employee_leave_history(mapping: TenantMapping, employee_id: str, token: Optional[str]) -> Dict[str, Any]:
    _require_eleave_config()
    return get_eleave_adapter().get_employee_leave_history(mapping, employee_id, token)
