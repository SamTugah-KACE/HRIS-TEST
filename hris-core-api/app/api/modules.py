from datetime import date
import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi import HTTPException

from app.clients import eappraisal_client, eleave_client, srms_client
from app.core.auth import AuthenticatedUser, get_current_user
from app.core.settings import get_settings
from app.services.identity_resolution import resolve_canonical_identity
from app.services.persona_policy import (
    can_view_manager_sections,
    enforce_self_or_privileged,
)
from app.services.tenant_registry_client import get_tenant_mapping

router = APIRouter(prefix="/modules", tags=["modules"])
profile_router = APIRouter(prefix="/profile", tags=["profile"])
logger = logging.getLogger(__name__)

MODULE_UI_METADATA: Dict[str, Dict[str, str]] = {
    "srms": {
        "label": "Staff Records",
        "description": "Employee records, organizational structure, and workforce governance.",
        "icon": "Users",
        "manager_path": "/employees",
        "self_path": "/profile",
    },
    "eappraisal": {
        "label": "Performance Appraisal",
        "description": "Performance cycles, assessments, ratings, and feedback.",
        "icon": "ClipboardList",
        "manager_path": "/modules/appraisal",
        "self_path": "/modules/appraisal",
    },
    "eleave": {
        "label": "Leave Management",
        "description": "Leave balances, requests, approvals, and leave calendar records.",
        "icon": "CalendarDays",
        "manager_path": "/modules/leave",
        "self_path": "/modules/leave",
    },
}


def _normalize_module_id(module_id: str) -> str:
    normalized = str(module_id or "").strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9_-]*", normalized):
        return ""
    return normalized


def _default_module_label(module_id: str) -> str:
    cleaned = module_id.replace("_", " ").replace("-", " ").strip()
    return cleaned.title() if cleaned else "Module"


def _module_ui_info(module_id: str, manager_view: bool) -> Dict[str, str]:
    normalized = _normalize_module_id(module_id)
    if not normalized:
        normalized = "module"
    metadata = MODULE_UI_METADATA.get(normalized, {})
    manager_path = metadata.get("manager_path", f"/modules/{normalized}")
    self_path = metadata.get("self_path", manager_path)
    return {
        "label": metadata.get("label", _default_module_label(normalized)),
        "description": metadata.get("description", "Integrated module exposed through the HRIS unified contract."),
        "icon": metadata.get("icon", "Layers"),
        "path": manager_path if manager_view else self_path,
        "manager_path": manager_path,
        "self_path": self_path,
    }


def _safe_get(fetcher, fallback, *, module_name: str, tenant_id: str, correlation_id: str):
    try:
        return fetcher()
    except HTTPException as exc:
        logger.warning(
            "Modules API fallback applied",
            extra={
                "module_name": module_name,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "status_code": exc.status_code,
                "detail": str(exc.detail),
            },
        )
        return fallback
    except Exception as exc:
        logger.exception(
            "Modules API fallback applied (unexpected error)",
            extra={
                "module_name": module_name,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "error": str(exc),
            },
        )
        return fallback


def _ensure_module_ready(mapping, module_name: str) -> None:
    if not mapping.module_enabled(module_name):
        raise HTTPException(
            status_code=403,
            detail=f"Module '{module_name}' is not active for tenant '{mapping.code}'",
        )


def _years_of_service(hire_date_value: Any) -> str:
    if not isinstance(hire_date_value, str) or len(hire_date_value) < 10:
        return "N/A"
    try:
        y, m, d = hire_date_value.split("-")
        hire_date = date(int(y), int(m), int(d))
        years = max(0, (date.today() - hire_date).days // 365)
        return f"{years} years"
    except Exception:
        return "N/A"


def _extract_first(value: Any, keys: List[str]) -> str:
    if not isinstance(value, dict):
        return ""
    for key in keys:
        raw = value.get(key)
        if raw is None:
            continue
        text = str(raw).strip()
        if text:
            return text
    return ""


def _flatten_self_profile(self_payload: Dict[str, Any], fallback_email: str) -> Dict[str, Any]:
    profile = self_payload.get("profile") if isinstance(self_payload.get("profile"), dict) else {}
    employment = self_payload.get("employment") if isinstance(self_payload.get("employment"), dict) else {}
    personal = self_payload.get("personal_info") if isinstance(self_payload.get("personal_info"), dict) else {}
    organization = self_payload.get("organization") if isinstance(self_payload.get("organization"), dict) else {}

    first_name = _extract_first(profile, ["firstName", "first_name"]) or _extract_first(personal, ["first_name", "firstName"])
    last_name = _extract_first(profile, ["lastName", "last_name"]) or _extract_first(personal, ["last_name", "lastName"])
    full_name = _extract_first(self_payload, ["full_name", "name"])
    if not full_name:
        full_name = " ".join([segment for segment in [first_name, last_name] if segment]).strip()
    email = (
        _extract_first(profile, ["email"])
        or _extract_first(personal, ["email"])
        or _extract_first(self_payload, ["email"])
        or fallback_email
    )

    return {
        "full_name": full_name or email,
        "first_name": first_name,
        "last_name": last_name,
        "staff_id": (
            _extract_first(profile, ["staffId", "staff_id"])
            or _extract_first(personal, ["staff_id", "staffId"])
            or _extract_first(self_payload, ["staff_id", "staffId"])
        ),
        "email": email,
        "phone": (
            _extract_first(profile, ["phone"])
            or _extract_first(personal, ["phone", "phone_number"])
            or _extract_first(self_payload, ["phone", "phone_number"])
        ),
        "gender": (
            _extract_first(profile, ["gender"])
            or _extract_first(personal, ["gender"])
            or _extract_first(self_payload, ["gender"])
        ),
        "organization": (
            _extract_first(employment, ["organization"])
            or _extract_first(organization, ["name"])
            or _extract_first(self_payload, ["organization"])
        ),
        "branch": _extract_first(employment, ["branch"]),
        "department": _extract_first(employment, ["department"]),
        "unit": _extract_first(employment, ["unit"]),
        "position": (
            _extract_first(employment, ["position"])
            or _extract_first(self_payload, ["position", "title"])
        ),
        "rank": _extract_first(employment, ["rank", "gradeLevel"]),
        "employee_type": _extract_first(employment, ["employeeType", "employee_type"]),
        "status": (
            _extract_first(employment, ["status"])
            or _extract_first(self_payload, ["status"])
        ),
        "hire_date": (
            _extract_first(employment, ["hireDate", "hire_date"])
            or _extract_first(self_payload, ["hire_date"])
        ),
    }


def _has_rich_profile_fields(employee_payload: Dict[str, Any]) -> bool:
    if not isinstance(employee_payload, dict):
        return False
    fields = [
        employee_payload.get("staff_id"),
        employee_payload.get("organization"),
        employee_payload.get("department"),
        employee_payload.get("position"),
        employee_payload.get("hire_date"),
    ]
    return any(str(value or "").strip() for value in fields)


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _compute_trend_message(appraisals: List[Dict[str, Any]]) -> str:
    numeric_scores = [
        score for score in (_safe_float(item.get("overall_score")) for item in appraisals) if score is not None
    ]
    if len(numeric_scores) < 2:
        return "Trend insight will appear when at least two scored appraisals are available."
    if numeric_scores[0] > numeric_scores[-1]:
        return "Your latest appraisal score is improving compared to your previous cycle."
    if numeric_scores[0] < numeric_scores[-1]:
        return "Your latest appraisal score is lower than previous cycles; review section feedback for improvements."
    return "Your appraisal score is stable across recent cycles."


def _profile_stub() -> Dict[str, Any]:
    return {
        "profile": {
            "firstName": "Kwame",
            "lastName": "Asante",
            "otherNames": "Osei",
            "staffId": "STF-001",
            "email": "kwame.asante@gi-kace.gov.gh",
            "phone": "+233 24 123 4567",
            "personalEmail": "kwame.asante@gmail.com",
            "dateOfBirth": "1990-05-15",
            "gender": "Male",
            "maritalStatus": "Married",
            "nationality": "Ghanaian",
            "ghanaCardNo": "GHA-098765432-1",
            "ssnitNo": "A012345678",
            "tinNo": "P0012345678",
            "residentialAddress": "12 Independence Avenue, Accra",
            "digitalAddress": "GA-123-4567",
        },
        "employment": {
            "organization": "Development Tenant",
            "branch": "Head Office",
            "department": "Information Technology",
            "unit": "Software Development",
            "position": "Senior Software Engineer",
            "rank": "Principal Technical Officer",
            "employeeType": "Full-time",
            "hireDate": "2020-01-15",
            "confirmationDate": "2020-07-15",
            "status": "Active",
            "supervisorName": "Dr. Ama Mensah",
            "supervisorTitle": "Director of IT",
            "gradeLevel": "Grade 14",
            "salaryStep": "Step 3",
            "previousPositions": [
                {"title": "Software Engineer", "department": "IT", "from": "2020-01-15", "to": "2022-06-30"},
                {"title": "Senior Software Engineer", "department": "IT", "from": "2022-07-01", "to": "Present"},
            ],
        },
        "qualifications": [
            {"type": "Degree", "title": "BSc Computer Science", "institution": "University of Ghana", "year": "2012", "grade": "First Class"},
            {"type": "Degree", "title": "MSc Information Technology", "institution": "KNUST", "year": "2015", "grade": "Distinction"},
            {"type": "Certification", "title": "AWS Solutions Architect", "institution": "Amazon Web Services", "year": "2023", "grade": "Certified"},
        ],
        "emergency_contacts": [
            {"name": "Akua Asante", "relationship": "Spouse", "phone": "+233 20 987 6543", "email": "akua.a@gmail.com", "isPrimary": True}
        ],
        "documents": [
            {"name": "Employment Letter", "type": "PDF", "size": "245 KB", "uploadedAt": "2020-01-15", "category": "Employment"}
        ],
        "quick_stats": {
            "years_of_service": "6 years",
            "leave_balance": "15 days",
            "appraisal_score": "3.9 / 5.0",
            "certifications": "2 active",
        },
    }


@router.get("/catalog")
def get_module_catalog(
    user: AuthenticatedUser = Depends(get_current_user),
):
    mapping = get_tenant_mapping(user.tenant_id)
    manager_view = can_view_manager_sections(user)
    modules = []
    for module_id, status in mapping.modules.as_dict().items():
        normalized_module_id = _normalize_module_id(module_id)
        if not normalized_module_id:
            continue
        module_ui = _module_ui_info(normalized_module_id, manager_view)
        enabled = (
            bool(status.configured)
            and bool(status.ready)
            and str(status.status).lower() == "active"
        )
        modules.append(
            {
                "id": normalized_module_id,
                "label": module_ui["label"],
                "description": module_ui["description"],
                "status": status.model_dump(),
                "enabled": enabled,
                "visible": enabled,
                "ui": {
                    "icon": module_ui["icon"],
                    "path": module_ui["path"],
                    "manager_path": module_ui["manager_path"],
                    "self_path": module_ui["self_path"],
                },
                "capabilities": {
                    "manager_view": manager_view,
                    "self_service_view": True,
                    "read_mode": "native-readonly",
                },
            }
        )

    modules.sort(key=lambda item: item["label"])
    return {
        "tenant": {
            "tenant_id": mapping.tenant_id,
            "code": mapping.code,
            "name": mapping.name,
            "status": mapping.lifecycle_status,
        },
        "workflow_standard": {
            "version": "1.0",
            "shape": "module-catalog",
            "rbac_driven": True,
            "data_access": "capability-based",
        },
        "modules": modules,
    }


@profile_router.get("/me")
def get_my_profile(
    request: Request,
    employee_id: Optional[str] = Query(None, description="Optional employee ID override"),
    user: AuthenticatedUser = Depends(get_current_user),
):
    correlation_id = getattr(request.state, "correlation_id", "")
    settings = get_settings()
    if settings.use_stub_data:
        return _profile_stub()

    mapping = get_tenant_mapping(user.tenant_id)
    _ensure_module_ready(mapping, "srms")
    canonical_identity = resolve_canonical_identity(user)
    if employee_id:
        enforce_self_or_privileged(user, employee_id, context="Profile lookup")
    resolved_employee_id = employee_id or canonical_identity.srms.employee_id
    if settings.eappraisal_fixture_file:
        resolved_employee_id = settings.eappraisal_fixture_employee_id
    self_profile_payload = _safe_get(
        lambda: srms_client.get_self_employee_comprehensive(mapping, user.raw_token),
        {},
        module_name="srms.profile_self",
        tenant_id=user.tenant_id,
        correlation_id=correlation_id,
    )
    employee_from_self = _flatten_self_profile(self_profile_payload, user.email or "")
    employee_from_search = _safe_get(
        lambda: srms_client.list_employees(
            mapping,
            user.raw_token,
            search=(user.email or user.username or ""),
            department="",
            emp_status="all",
            page=1,
            page_size=20,
        ),
        {"employees": []},
        module_name="srms.profile_search",
        tenant_id=user.tenant_id,
        correlation_id=correlation_id,
    )
    search_rows = employee_from_search.get("employees", []) if isinstance(employee_from_search, dict) else []
    best_search_row = {}
    if isinstance(search_rows, list):
        preferred_email = str(user.email or "").strip().lower()
        for row in search_rows:
            if not isinstance(row, dict):
                continue
            row_email = str(row.get("email") or "").strip().lower()
            if preferred_email and row_email == preferred_email:
                best_search_row = row
                break
            if not best_search_row:
                best_search_row = row
    preferred_fallback = employee_from_self if _has_rich_profile_fields(employee_from_self) else best_search_row
    employee = _safe_get(
        lambda: srms_client.get_employee(mapping, str(resolved_employee_id), user.raw_token),
        preferred_fallback or {
            "full_name": user.username,
            "staff_id": "",
            "email": user.email or "",
            "phone": "",
            "gender": "",
            "organization": "",
            "branch": "",
            "department": "",
            "unit": "",
            "position": "",
            "rank": "",
            "employee_type": "",
            "status": "",
            "hire_date": "",
        },
        module_name="srms.profile_employee",
        tenant_id=user.tenant_id,
        correlation_id=correlation_id,
    )

    full_name = str(employee.get("full_name", user.username))
    parts = [p for p in full_name.split(" ") if p]
    first_name = parts[0] if parts else user.username
    last_name = parts[-1] if len(parts) > 1 else ""
    other_names = " ".join(parts[1:-1]) if len(parts) > 2 else ""

    return {
        "profile": {
            "firstName": first_name,
            "lastName": last_name,
            "otherNames": other_names,
            "staffId": employee.get("staff_id", ""),
            "email": employee.get("email", user.email or ""),
            "phone": employee.get("phone", ""),
            "personalEmail": "",
            "dateOfBirth": "",
            "gender": employee.get("gender", ""),
            "maritalStatus": "",
            "nationality": "",
            "ghanaCardNo": "",
            "ssnitNo": "",
            "tinNo": "",
            "residentialAddress": "",
            "digitalAddress": "",
        },
        "employment": {
            "organization": employee.get("organization", ""),
            "branch": employee.get("branch", ""),
            "department": employee.get("department", ""),
            "unit": employee.get("unit", ""),
            "position": employee.get("position", ""),
            "rank": employee.get("rank", ""),
            "employeeType": employee.get("employee_type", ""),
            "hireDate": employee.get("hire_date", ""),
            "confirmationDate": "",
            "status": employee.get("status", ""),
            "supervisorName": "",
            "supervisorTitle": "",
            "gradeLevel": "",
            "salaryStep": "",
            "previousPositions": [],
        },
        "qualifications": [],
        "emergency_contacts": [],
        "documents": [],
        "quick_stats": {
            "years_of_service": _years_of_service(employee.get("hire_date")),
            "leave_balance": "N/A",
            "appraisal_score": "N/A",
            "certifications": "0 active",
        },
    }


@router.get("/appraisal")
def get_appraisal_module_data(
    request: Request,
    employee_id: Optional[str] = Query(None, description="Optional employee ID override"),
    user: AuthenticatedUser = Depends(get_current_user),
):
    correlation_id = getattr(request.state, "correlation_id", "")
    settings = get_settings()
    if settings.use_stub_data and not settings.eappraisal_fixture_file and not settings.eappraisal_domain_template:
        return {
            "manager": {
                "stats": {"active_cycles": 1, "completed": 88, "pending": 12, "overdue": 3},
                "team_stats": [
                    {"name": "Kwame Asante", "score": 4.1, "completed": 2, "pending": 3},
                    {"name": "Ama Mensah", "score": None, "completed": 5, "pending": 0},
                ],
                "recent_activity": [
                    {"name": "Ama Mensah", "action": "Submitted self-assessment", "time": "2 hours ago", "status": "pending"},
                    {"name": "Kofi Osei", "action": "Appraisal completed", "time": "1 day ago", "status": "completed"},
                ],
            },
            "employee": {
                "current_cycle": {"title": "2025/2026 Appraisal Cycle", "due_date": "Mar 30, 2026", "overall_progress": 40},
                "sections": [
                    {"name": "Key Result Areas (KRA)", "weight": 40, "status": "completed", "score": 4.1, "maxScore": 5},
                    {"name": "Core Competencies", "weight": 25, "status": "completed", "score": 3.8, "maxScore": 5},
                    {"name": "Leadership & Initiative", "weight": 15, "status": "in_progress", "score": None, "maxScore": 5},
                ],
                "goals": [],
                "past_appraisals": [
                    {
                        "submission_id": "stub-submission-001",
                        "appraisal_id": "stub-appraisal-001",
                        "cycle": "2024/2025",
                        "score": 4.2,
                        "rating": "Excellent",
                        "status": "completed",
                        "date": "2025-06-15",
                    }
                ],
                "trend_message": "Your performance trend is improving over the last 3 cycles.",
            },
        }

    mapping = get_tenant_mapping(user.tenant_id)
    _ensure_module_ready(mapping, "eappraisal")
    canonical_identity = resolve_canonical_identity(user)
    if employee_id:
        enforce_self_or_privileged(user, employee_id, context="Appraisal module lookup")
    resolved_employee_id = employee_id or canonical_identity.eappraisal.employee_id
    summary = _safe_get(
        lambda: eappraisal_client.get_appraisal_summary(mapping, user.raw_token),
        {
            "active_cycles": 0,
            "pending_reviews": 0,
            "completed_reviews": 0,
            "overdue_reviews": 0,
            "average_score": 0,
            "completion_rate": 0,
        },
        module_name="eappraisal.summary",
        tenant_id=user.tenant_id,
        correlation_id=correlation_id,
    )
    employee_appraisals = _safe_get(
        lambda: eappraisal_client.get_employee_appraisals(mapping, str(resolved_employee_id), user.raw_token),
        {"appraisals": []},
        module_name="eappraisal.employee_appraisals",
        tenant_id=user.tenant_id,
        correlation_id=correlation_id,
    )
    my_appraisal = _safe_get(
        lambda: eappraisal_client.get_my_appraisals(mapping, user.raw_token),
        {"current_cycle": {"title": "Current Appraisal Cycle", "due_date": "", "overall_progress": 0}, "sections": [], "goals": []},
        module_name="eappraisal.my_appraisals",
        tenant_id=user.tenant_id,
        correlation_id=correlation_id,
    )
    appraisals = employee_appraisals.get("appraisals", [])
    normalized_past = [
        {
            "submission_id": item.get("submission_id", ""),
            "appraisal_id": item.get("appraisal_id", ""),
            "cycle": item.get("cycle_name", "Unknown Cycle"),
            "score": item.get("overall_score"),
            "rating": item.get("rating", ""),
            "status": item.get("status", ""),
            "date": item.get("date", ""),
            "submitted": bool(item.get("submitted", False)),
            "reviewed": bool(item.get("reviewed", False)),
            "reviewer": item.get("reviewer", ""),
            "comments": item.get("comments", ""),
        }
        for item in appraisals
    ]

    response = {
        "manager": {
            "stats": {
                "active_cycles": summary.get("active_cycles", 0),
                "completed": summary.get("completed_reviews", 0),
                "pending": summary.get("pending_reviews", 0),
                "overdue": summary.get("overdue_reviews", 0),
            },
            "team_stats": [],
            "recent_activity": [],
        },
        "employee": {
            "current_cycle": my_appraisal.get("current_cycle", {"title": "Current Appraisal Cycle", "due_date": "", "overall_progress": 0}),
            "sections": my_appraisal.get("sections", []),
            "goals": my_appraisal.get("goals", []),
            "past_appraisals": normalized_past,
            "trend_message": _compute_trend_message(appraisals),
        },
    }
    if not can_view_manager_sections(user):
        response["manager"] = {"stats": {}, "team_stats": [], "recent_activity": []}
    return response


@router.get("/appraisal/history/{entry_id}")
def get_appraisal_history_detail(
    request: Request,
    entry_id: str,
    employee_id: Optional[str] = Query(None, description="Optional employee ID override"),
    user: AuthenticatedUser = Depends(get_current_user),
):
    correlation_id = getattr(request.state, "correlation_id", "")
    settings = get_settings()
    if settings.use_stub_data and not settings.eappraisal_fixture_file and not settings.eappraisal_domain_template:
        return {
            "entry_id": entry_id,
            "cycle": "2024/2025",
            "status": "completed",
            "score": 4.2,
            "rating": "Excellent",
            "submitted": True,
            "reviewed": True,
            "reviewer": "Dr. Ama Mensah",
            "comments": "Strong delivery against agreed objectives.",
            "date": "2025-06-15",
        }

    mapping = get_tenant_mapping(user.tenant_id)
    _ensure_module_ready(mapping, "eappraisal")
    canonical_identity = resolve_canonical_identity(user)
    if employee_id:
        enforce_self_or_privileged(user, employee_id, context="Appraisal history lookup")
    resolved_employee_id = employee_id or canonical_identity.eappraisal.employee_id
    employee_appraisals = _safe_get(
        lambda: eappraisal_client.get_employee_appraisals(mapping, str(resolved_employee_id), user.raw_token),
        {"appraisals": []},
        module_name="eappraisal.history_lookup",
        tenant_id=user.tenant_id,
        correlation_id=correlation_id,
    )
    appraisals = employee_appraisals.get("appraisals", [])
    selected = next(
        (
            item
            for item in appraisals
            if str(item.get("submission_id", "")) == entry_id or str(item.get("appraisal_id", "")) == entry_id
        ),
        None,
    )
    if not selected:
        raise HTTPException(status_code=404, detail=f"Appraisal history entry '{entry_id}' not found")

    return {
        "entry_id": entry_id,
        "cycle": selected.get("cycle_name", ""),
        "status": selected.get("status", ""),
        "score": selected.get("overall_score"),
        "rating": selected.get("rating", ""),
        "submitted": bool(selected.get("submitted", False)),
        "reviewed": bool(selected.get("reviewed", False)),
        "reviewer": selected.get("reviewer", ""),
        "comments": selected.get("comments", ""),
        "date": selected.get("date", ""),
    }


@router.get("/leave")
def get_leave_module_data(
    request: Request,
    employee_id: Optional[str] = Query(None, description="Optional employee ID override"),
    user: AuthenticatedUser = Depends(get_current_user),
):
    correlation_id = getattr(request.state, "correlation_id", "")
    settings = get_settings()
    if settings.use_stub_data:
        return {
            "manager": {
                "stats": {"total_this_year": 320, "approved": 280, "pending": 25, "rejected": 10},
                "pending_requests": [
                    {"id": "P001", "name": "Kwame Asante", "type": "Annual Leave", "days": 3, "from": "2026-02-25", "to": "2026-02-27", "appliedOn": "2026-02-10", "department": "IT", "reliefOfficer": "Kofi Osei"}
                ],
            },
            "employee": {
                "balances": [
                    {"type": "Annual Leave", "total": 23, "used": 8, "pending": 3, "color": "bg-blue-500"},
                    {"type": "Sick Leave", "total": 10, "used": 0, "pending": 0, "color": "bg-red-500"},
                ],
                "history": [
                    {"id": "L001", "type": "Annual Leave", "days": 5, "startDate": "2025-12-20", "endDate": "2025-12-24", "status": "approved", "appliedOn": "2025-12-01", "approvedBy": "Dr. Ama Mensah"}
                ],
                "holidays": [
                    {"name": "Independence Day", "date": "Mar 6, 2026"},
                    {"name": "Good Friday", "date": "Apr 3, 2026"},
                ],
            },
        }

    mapping = get_tenant_mapping(user.tenant_id)
    _ensure_module_ready(mapping, "eleave")
    canonical_identity = resolve_canonical_identity(user)
    if employee_id:
        enforce_self_or_privileged(user, employee_id, context="Leave module lookup")
    resolved_employee_id = employee_id or canonical_identity.eleave.employee_id
    summary = _safe_get(
        lambda: eleave_client.get_leave_summary(mapping, user.raw_token),
        {
            "total_leaves_this_year": 0,
            "approved_leaves": 0,
            "pending_leaves": 0,
            "rejected_leaves": 0,
            "cancelled_leaves": 0,
            "leave_utilization_rate": 0,
        },
        module_name="eleave.summary",
        tenant_id=user.tenant_id,
        correlation_id=correlation_id,
    )
    leave_history = _safe_get(
        lambda: eleave_client.get_employee_leave_history(mapping, str(resolved_employee_id), user.raw_token),
        {"leaves": [], "balance": {}, "used": {}},
        module_name="eleave.employee_history",
        tenant_id=user.tenant_id,
        correlation_id=correlation_id,
    )

    raw_history: List[Dict[str, Any]] = leave_history.get("leaves", [])
    normalized_history = [
        {
            "id": f"L{i + 1:03d}",
            "type": item.get("type", ""),
            "days": item.get("days", 0),
            "startDate": item.get("start_date", ""),
            "endDate": item.get("end_date", ""),
            "status": item.get("status", ""),
            "appliedOn": "",
            "approvedBy": None,
        }
        for i, item in enumerate(raw_history)
    ]

    balance = leave_history.get("balance", {})
    used = leave_history.get("used", {})
    balance_colors = {
        "annual": "bg-blue-500",
        "sick": "bg-red-500",
        "casual": "bg-amber-500",
        "study": "bg-purple-500",
        "compassionate": "bg-green-500",
    }
    normalized_balances = [
        {
            "type": f"{name.title()} Leave" if name != "compassionate" else "Compassionate",
            "total": int(total_days),
            "used": int(used.get(name, 0)),
            "pending": 0,
            "color": balance_colors.get(name, "bg-gray-500"),
        }
        for name, total_days in balance.items()
    ]

    response = {
        "manager": {
            "stats": {
                "total_this_year": summary.get("total_leaves_this_year", 0),
                "approved": summary.get("approved_leaves", 0),
                "pending": summary.get("pending_leaves", 0),
                "rejected": summary.get("rejected_leaves", 0),
            },
            "pending_requests": [],
        },
        "employee": {
            "balances": normalized_balances,
            "history": normalized_history,
            "holidays": [],
        },
    }
    if not can_view_manager_sections(user):
        response["manager"] = {"stats": {}, "pending_requests": []}
    return response
