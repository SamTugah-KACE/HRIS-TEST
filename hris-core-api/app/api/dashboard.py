from fastapi import APIRouter, Depends

from app.core.auth import AuthenticatedUser, get_current_user
from app.services.tenant_registry_client import get_tenant_mapping
from app.clients import srms_client, eappraisal_client, eleave_client

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
def get_dashboard_summary(
    user: AuthenticatedUser = Depends(get_current_user),
):
    mapping = get_tenant_mapping(user.tenant_id)

    srms_summary = srms_client.get_dashboard_summary(mapping, user.raw_token)
    appraisal_summary = eappraisal_client.get_appraisal_summary(mapping, user.raw_token)
    leave_summary = eleave_client.get_leave_summary(mapping, user.raw_token)

    role = user.effective_role

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
        },
        "srms": srms_summary,
        "appraisal": appraisal_summary,
        "leave": leave_summary,
        "quick_actions": quick_actions,
    }
