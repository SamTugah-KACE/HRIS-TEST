import logging

from fastapi import APIRouter, Depends, Request

from app.core.auth import AuthenticatedUser, get_current_user
from app.services.tenant_registry_client import get_tenant_mapping, list_tenant_mappings
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


def _build_superadmin_dashboard_summary(
    user: AuthenticatedUser,
    *,
    correlation_id: str,
):
    # The Tenant Registry is the platform authority. A super-admin dashboard
    # must not block on an optional native module or treat SRMS as canonical.
    mappings = list_tenant_mappings(limit=1000)
    organizations = [
        {
            "tenant_id": mapping.tenant_id,
            "code": mapping.code,
            "name": mapping.name,
            "status": mapping.lifecycle_status,
            "modules": mapping.modules.model_dump(),
        }
        for mapping in mappings
    ]
    active = sum(1 for row in organizations if str(row.get("status") or "").lower() == "active")
    summary = {"total": len(organizations), "active": active, "inactive": len(organizations) - active}

    # Platform superadmin intentionally uses a global dashboard context.
    return {
        "user": {
            "username": user.username,
            "effective_role": user.effective_role,
            "roles": user.roles,
        },
        "tenant": {
            "code": "PLATFORM",
            "name": "HRIS Platform",
            "status": "active",
            "modules": {"srms": {}, "eappraisal": {}, "eleave": {}},
        },
        "srms": {
            "total_employees": 0,
            "active_employees": 0,
            "inactive_employees": 0,
            "branches": 0,
            "departments": 0,
            "new_hires_this_month": 0,
            "pending_enlistments": 0,
        },
        "appraisal": {
            "active_cycles": 0,
            "pending_reviews": 0,
            "completed_reviews": 0,
            "overdue_reviews": 0,
            "average_score": 0,
            "completion_rate": 0,
        },
        "leave": {
            "total_leaves_this_year": 0,
            "approved_leaves": 0,
            "pending_leaves": 0,
            "rejected_leaves": 0,
            "cancelled_leaves": 0,
            "leave_utilization_rate": 0,
        },
        "superadmin": {
            "tenants": organizations[:50] if isinstance(organizations, list) else [],
            "tenant_summary": {
                "total": _to_int_safe(summary.get("total"), len(organizations) if isinstance(organizations, list) else 0),
                "active": _to_int_safe(summary.get("active"), 0),
                "inactive": _to_int_safe(summary.get("inactive"), 0),
            },
        },
        "quick_actions": [
            {"id": "manage_tenants", "label": "Manage Tenants", "icon": "building-2", "href": "/admin/tenants"},
            {"id": "manage_roles", "label": "Manage Roles", "icon": "shield", "href": "/admin/roles"},
            {"id": "view_reports", "label": "View Reports", "icon": "bar-chart-2", "href": "/reports"},
        ],
    }


@router.get("/summary")
def get_dashboard_summary(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    correlation_id = getattr(request.state, "correlation_id", "")

    if user.effective_role == "hris:super_admin":
        return _build_superadmin_dashboard_summary(user, correlation_id=correlation_id)

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
        if _to_int_safe(srms_summary.get("total_employees"), 0) <= 0:
            # SRMS dashboard summary may be unavailable for some tenants while roster is healthy.
            # Derive stable counts from the roster to avoid misleading zero cards.
            roster_payload = _safe_get(
                lambda: srms_client.list_employees(
                    mapping,
                    user.raw_token,
                    search="",
                    department="",
                    emp_status="all",
                    page=1,
                    page_size=1000,
                ),
                {"employees": [], "total": 0},
                module_name="srms.roster_fallback",
                tenant_id=user.tenant_id,
                correlation_id=correlation_id,
            )
            rows = roster_payload.get("employees", []) if isinstance(roster_payload, dict) else []
            rows = rows if isinstance(rows, list) else []
            active = sum(
                1
                for row in rows
                if str((row or {}).get("status") or "").strip().lower() == "active"
            )
            inactive = max(len(rows) - active, 0)
            departments = {
                str((row or {}).get("department") or "").strip().lower()
                for row in rows
                if str((row or {}).get("department") or "").strip()
            }
            branches = {
                str((row or {}).get("branch") or "").strip().lower()
                for row in rows
                if str((row or {}).get("branch") or "").strip()
            }
            srms_summary["total_employees"] = max(
                _to_int_safe(roster_payload.get("total") if isinstance(roster_payload, dict) else 0, len(rows)),
                len(rows),
            )
            srms_summary["active_employees"] = active
            srms_summary["inactive_employees"] = inactive
            srms_summary["departments"] = len(departments)
            srms_summary["branches"] = len(branches)

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
    appraisal_launchable = mapping.module_enabled("eappraisal") and bool(str(mapping.eappraisal_subdomain or "").strip())
    leave_launchable = mapping.module_enabled("eleave") and bool(str(mapping.eleave_subdomain or "").strip())

    quick_actions = []
    if role in ("hris:super_admin", "hris:tenant_admin", "hris:hr_manager"):
        quick_actions.extend([
            {"id": "add_employee", "label": "Add Employee", "icon": "user-plus", "href": "/employees/new"},
            {"id": "manage_roles", "label": "Manage Roles", "icon": "shield", "href": "/admin/roles"},
            {"id": "view_reports", "label": "View Reports", "icon": "bar-chart-2", "href": "/reports"},
        ])
    if role in ("hris:super_admin", "hris:tenant_admin", "hris:hr_manager", "hris:line_manager"):
        if leave_launchable:
            quick_actions.append(
                {"id": "pending_leaves", "label": "Pending Leave Approvals", "icon": "calendar-clock", "href": "/modules/leave"}
            )
        if appraisal_launchable:
            quick_actions.append(
                {"id": "pending_appraisals", "label": "Pending Appraisals", "icon": "clipboard-check", "href": "/modules/appraisal"}
            )
    if role == "hris:employee":
        if leave_launchable:
            quick_actions.append(
                {"id": "apply_leave", "label": "Apply for Leave", "icon": "calendar-plus", "href": "/modules/leave"}
            )
        if appraisal_launchable:
            quick_actions.append(
                {"id": "my_appraisal", "label": "My Appraisal", "icon": "clipboard-list", "href": "/modules/appraisal"}
            )
        quick_actions.append(
            {"id": "my_profile", "label": "My Profile", "icon": "user", "href": "/profile"}
        )

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
