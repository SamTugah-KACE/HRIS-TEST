from fastapi import APIRouter, Depends, Query
from fastapi import HTTPException, status

from app.core.auth import AuthenticatedUser, get_current_user
from app.services.tenant_registry_client import get_tenant_mapping
from app.clients import srms_client, eappraisal_client, eleave_client
from app.services.persona_policy import can_view_tenant_employee_roster, enforce_self_or_privileged

router = APIRouter(prefix="/employees", tags=["employees"])


@router.get("")
def list_employees(
    search: str = Query("", description="Search by name or staff ID"),
    department: str = Query("", description="Filter by department"),
    employee_status: str = Query(
        "active",
        alias="status",
        description="Filter by status: active, inactive, all",
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: AuthenticatedUser = Depends(get_current_user),
):
    if not can_view_tenant_employee_roster(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Employee roster access requires HR manager/tenant admin privileges.",
        )
    mapping = get_tenant_mapping(user.tenant_id)
    employees = srms_client.list_employees(
        mapping,
        user.raw_token,
        search,
        department,
        employee_status,
        page,
        page_size,
    )
    return employees


@router.get("/{employee_id}/summary")
def get_employee_summary(
    employee_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    enforce_self_or_privileged(user, employee_id, context="Employee summary")
    mapping = get_tenant_mapping(user.tenant_id)

    employee = srms_client.get_employee(mapping, employee_id, user.raw_token)
    appraisals = eappraisal_client.get_employee_appraisals(mapping, employee_id, user.raw_token)
    leaves = eleave_client.get_employee_leave_history(mapping, employee_id, user.raw_token)

    return {
        "employee": employee,
        "appraisals": appraisals.get("appraisals", []),
        "leaves": leaves.get("leaves", []),
    }
