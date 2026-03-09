import logging

from fastapi import APIRouter, Depends, Request
from fastapi import HTTPException

from app.core.auth import AuthenticatedUser, get_current_user
from app.services.tenant_registry_client import get_tenant_mapping
from app.clients import srms_client, eappraisal_client, eleave_client

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
logger = logging.getLogger(__name__)


def _safe_get(fetcher, fallback, *, module_name: str, tenant_id: str, correlation_id: str):
    try:
        return fetcher()
    except Exception as exc:
        logger.warning(
            "Dashboard module fallback applied",
            extra={
                "module_name": module_name,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "error": str(exc),
            },
        )
        return fallback


def _to_int_safe(value, default: int) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


@router.get("/summary")
def get_dashboard_summary(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    correlation_id = getattr(request.state, "correlation_id", "")
    mapping = get_tenant_mapping(user.tenant_id)

    srms_summary = {
        "total_employees": 0,
        "active_employees": 0,
        "inactive_employees": 0,
        "branches": 0,
        "departments": 0,
        "new_hires_this_month": 0,
        "pending_enlistments": 0,
    }
    if mapping.module_enabled("srms"):
        srms_summary = _safe_get(
            lambda: srms_client.get_dashboard_summary(mapping, user.raw_token),
            srms_summary,
            module_name="srms",
            tenant_id=user.tenant_id,
            correlation_id=correlation_id,
        )

    appraisal_summary = {
        "active_cycles": 0,
        "pending_reviews": 0,
        "completed_reviews": 0,
        "overdue_reviews": 0,
        "average_score": 0,
        "completion_rate": 0,
    }
    if mapping.module_enabled("eappraisal"):
        appraisal_summary = _safe_get(
            lambda: eappraisal_client.get_appraisal_summary(mapping, user.raw_token),
            appraisal_summary,
            module_name="eappraisal",
            tenant_id=user.tenant_id,
            correlation_id=correlation_id,
        )

    leave_summary = {
        "total_leaves_this_year": 0,
        "approved_leaves": 0,
        "pending_leaves": 0,
        "rejected_leaves": 0,
        "cancelled_leaves": 0,
        "leave_utilization_rate": 0,
    }
    if mapping.module_enabled("eleave"):
        leave_summary = _safe_get(
            lambda: eleave_client.get_leave_summary(mapping, user.raw_token),
            leave_summary,
            module_name="eleave",
            tenant_id=user.tenant_id,
            correlation_id=correlation_id,
        )

    role = user.effective_role
    superadmin = None
    if role == "hris:super_admin":
        organizations_payload = _safe_get(
            lambda: srms_client.list_organizations(user.raw_token),
            {"organizations": [], "summary": {"total": 0, "active": 0, "inactive": 0}},
            module_name="srms.organizations",
            tenant_id=user.tenant_id,
            correlation_id=correlation_id,
        )
        organizations = organizations_payload.get("organizations", [])
        summary = organizations_payload.get("summary", {})
        superadmin = {
            "tenants": organizations[:50],
            "tenant_summary": {
                "total": _to_int_safe(summary.get("total"), len(organizations)),
                "active": _to_int_safe(summary.get("active"), 0),
                "inactive": _to_int_safe(summary.get("inactive"), 0),
            },
        }

    quick_actions = []
    if role in ("hris:super_admin", "hris:tenant_admin", "hris:hr_manager"):
        quick_actions.extend([
            {"id": "add_employee", "label": "Add Employee", "icon": "user-plus", "href": "/employees/new"},
            {"id": "manage_roles", "label": "Manage Roles", "icon": "shield", "href": "/admin/roles"},
            {"id": "view_reports", "label": "View Reports", "icon": "bar-chart-2", "href": "/reports"},
        ])
    if role in ("hris:super_admin", "hris:tenant_admin", "hris:hr_manager", "hris:line_manager"):
        quick_actions.extend([
            {"id": "pending_leaves", "label": "Pending Leave Approvals", "icon": "calendar-clock", "href": "/modules/leave"},
            {"id": "pending_appraisals", "label": "Pending Appraisals", "icon": "clipboard-check", "href": "/modules/appraisal"},
        ])
    if role == "hris:employee":
        quick_actions.extend([
            {"id": "apply_leave", "label": "Apply for Leave", "icon": "calendar-plus", "href": "/modules/leave"},
            {"id": "my_appraisal", "label": "My Appraisal", "icon": "clipboard-list", "href": "/modules/appraisal"},
            {"id": "my_profile", "label": "My Profile", "icon": "user", "href": "/profile"},
        ])

    return {
        "user": {
            "username": user.username,
            "effective_role": user.effective_role,
            "roles": user.roles,
        },
        "tenant": {
            "code": mapping.code,
            "name": mapping.name,
            "status": mapping.lifecycle_status,
            "modules": mapping.modules.model_dump(),
        },
        "srms": srms_summary,
        "appraisal": appraisal_summary,
        "leave": leave_summary,
        "superadmin": superadmin,
        "quick_actions": quick_actions,
    }
