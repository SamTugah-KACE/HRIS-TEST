from datetime import date
import hmac
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Query, Request
from fastapi import HTTPException
from fastapi.responses import Response
from jose import JWTError, jwt
from pydantic import BaseModel

from app.clients import eappraisal_client, eleave_client, srms_client
from app.core.auth import AuthenticatedUser, get_current_user
from app.core.settings import get_settings
from app.services.identity_resolution import resolve_canonical_identity
from app.services.persona_policy import (
    can_view_manager_sections,
    enforce_self_or_privileged,
)
from app.services.jit_module_setup import jit_setup_module_for_user
from app.services.jit_policy import get_jit_action_allowlist
from app.services.module_handoff import issue_handoff_launch, redeem_handoff_token, token_fingerprint
from app.services.module_launch import build_module_launch_descriptor
from app.services.module_readiness import check_module_readiness
from app.services.rate_limiter import enforce_rate_limit
from app.services.tenant_registry_client import get_tenant_mapping

router = APIRouter(prefix="/modules", tags=["modules"])
profile_router = APIRouter(prefix="/profile", tags=["profile"])
logger = logging.getLogger(__name__)


class ModuleHandoffRedeemRequest(BaseModel):
    handoff_token: str
    module_id: str
    tenant_id: str

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


def _module_ui_info(module_id: str, manager_view: bool, *, role: str = "") -> Dict[str, str]:
    normalized = _normalize_module_id(module_id)
    if not normalized:
        normalized = "module"
    metadata = MODULE_UI_METADATA.get(normalized, {})
    manager_path = metadata.get("manager_path", f"/modules/{normalized}")
    if normalized == "srms" and role == "hris:line_manager":
        manager_path = "/employees/team"
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


def _raise_readiness_block(readiness: Dict[str, Any], *, module_name: str) -> None:
    code = str(readiness.get("code") or "module_not_ready")
    message = str(readiness.get("detail") or f"Module '{module_name}' is not ready")
    action = "contact_admin"
    if code in {"missing_eappraisal_base_url", "missing_eleave_base_url", "missing_srms_base_url"}:
        action = "configure_module_endpoint"
    elif code in {"missing_eleave_shared_secret"}:
        action = "configure_service_auth"
    elif code in {"user_not_in_module_inventory"}:
        action = "provision_or_sync_user"
    elif code in {"eappraisal_inventory_check_failed"}:
        action = "retry_or_check_upstream"
    raise HTTPException(
        status_code=409,
        detail={
            "code": code,
            "message": message,
            "action": action,
            "module": module_name,
        },
    )


def _resolve_module_service_secret(module_name: str) -> str:
    settings = get_settings()
    normalized = str(module_name or "").strip().lower()
    if normalized == "eappraisal":
        return str(settings.eappraisal_hris_shared_secret or settings.eappraisal_hris_service_token or "").strip()
    if normalized == "eleave":
        return str(settings.eleave_hris_shared_secret or settings.eleave_hris_service_token or "").strip()
    if normalized == "srms":
        return str(settings.srms_hris_shared_secret or settings.srms_hris_service_token or "").strip()
    return ""


def _resolve_module_service_jwt_secret() -> str:
    settings = get_settings()
    for candidate in (
        settings.module_service_jwt_shared_secret,
        settings.module_token_secret,
        settings.auth_state_secret,
        settings.keycloak_portal_client_secret,
    ):
        value = str(candidate or "").strip()
        if value:
            return value
    return ""


def _validate_module_service_jwt(*, token: str, module_name: str) -> None:
    settings = get_settings()
    secret = _resolve_module_service_jwt_secret()
    if not secret:
        raise HTTPException(status_code=503, detail="Module service JWT secret is not configured")
    algorithms = [alg.strip() for alg in str(settings.module_service_jwt_algorithms or "HS256").split(",") if alg.strip()]
    if not algorithms:
        algorithms = ["HS256"]
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=algorithms,
            options={"verify_aud": False},
        )
    except JWTError as exc:
        raise HTTPException(status_code=401, detail=f"Module service JWT verification failed for '{module_name}'") from exc

    expected_issuer = str(settings.module_service_jwt_issuer or "").strip()
    if expected_issuer:
        token_issuer = str(payload.get("iss") or "").strip()
        if token_issuer != expected_issuer:
            raise HTTPException(status_code=401, detail=f"Module service JWT issuer mismatch for '{module_name}'")

    expected_audience = str(settings.module_service_jwt_audience or "").strip()
    if expected_audience:
        raw_aud = payload.get("aud")
        token_audiences: List[str] = []
        if isinstance(raw_aud, str):
            token_audiences = [raw_aud]
        elif isinstance(raw_aud, list):
            token_audiences = [str(item).strip() for item in raw_aud if str(item).strip()]
        if expected_audience not in token_audiences:
            raise HTTPException(status_code=401, detail=f"Module service JWT audience mismatch for '{module_name}'")

    declared_module = str(payload.get("module_id") or payload.get("module") or "").strip().lower()
    if declared_module and declared_module != str(module_name or "").strip().lower():
        raise HTTPException(status_code=403, detail=f"Module service JWT module mismatch for '{module_name}'")


def _require_module_service_auth(module_name: str, request: Request) -> None:
    expected = _resolve_module_service_secret(module_name)
    settings = get_settings()
    mode = str(settings.module_service_auth_mode or "shared_secret").strip().lower()
    presented = str(request.headers.get("X-HRIS-Module-Secret") or "").strip()
    bearer_token = ""
    if not presented and request.headers.get("Authorization"):
        auth = str(request.headers.get("Authorization") or "")
        if auth.lower().startswith("bearer "):
            bearer_token = auth[7:].strip()
            presented = bearer_token

    if mode in {"jwt_optional", "jwt_strict"} and bearer_token:
        _validate_module_service_jwt(token=bearer_token, module_name=module_name)
        return

    if mode == "jwt_strict":
        raise HTTPException(status_code=401, detail=f"Module service JWT is required for '{module_name}'")

    if not expected:
        raise HTTPException(status_code=503, detail=f"Module service auth is not configured for '{module_name}'")
    if not presented or not hmac.compare_digest(presented, expected):
        raise HTTPException(status_code=401, detail=f"Module service authentication failed for '{module_name}'")


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


def _require_resolved_module_identity(module_name: str, employee_id: str) -> None:
    if str(employee_id or "").strip():
        return
    settings = get_settings()
    if bool(settings.allow_low_confidence_identity_fallback):
        return
    raise HTTPException(
        status_code=422,
        detail={
            "code": "IDENTITY_UNRESOLVED",
            "message": f"Unable to resolve employee identity for module '{module_name}'",
            "action": "sync_or_provision_identity",
            "module": module_name,
        },
    )


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


def _merge_employee_sources(*sources: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge normalized employee payloads by taking the first non-empty value per field.
    Source order is highest priority first.
    """
    keys = [
        "employee_id",
        "staff_id",
        "full_name",
        "first_name",
        "last_name",
        "email",
        "phone",
        "gender",
        "organization",
        "branch",
        "department",
        "unit",
        "position",
        "rank",
        "employee_type",
        "status",
        "hire_date",
    ]
    merged: Dict[str, Any] = {}
    for key in keys:
        value = ""
        for source in sources:
            if not isinstance(source, dict):
                continue
            candidate = source.get(key)
            if str(candidate or "").strip():
                value = candidate
                break
        merged[key] = value
    return merged


def _extract_list(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _normalize_profile_qualifications(self_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen: set = set()

    def _append(items: List[Dict[str, Any]], default_type: str) -> None:
        for item in items:
            title = _extract_first(item, ["qualification", "title", "name"])
            institution = _extract_first(item, ["institution", "issuer", "organization"])
            year = _extract_first(item, ["year_obtained", "year"])
            grade = _extract_first(item, ["grade", "score"])
            doc_path = _extract_first(item, ["certificate_path", "license_path", "document_path", "file_path"])
            identity = (
                title.lower().strip(),
                institution.lower().strip(),
                year.strip(),
                default_type.strip(),
            )
            if not any(identity):
                continue
            if identity in seen:
                continue
            seen.add(identity)
            rows.append(
                {
                    "type": default_type,
                    "title": title,
                    "institution": institution,
                    "year": year,
                    "grade": grade,
                    "documentPath": doc_path,
                }
            )

    _append(_extract_list(self_payload.get("academic_qualifications")), "Academic")
    _append(_extract_list(self_payload.get("professional_qualifications")), "Professional")
    _append(_extract_list(self_payload.get("qualifications")), "Qualification")
    return rows


def _normalize_profile_emergency_contacts(self_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    primary_rows = _extract_list(self_payload.get("emergency_contacts"))
    personal_info = self_payload.get("personal_info") if isinstance(self_payload.get("personal_info"), dict) else {}
    fallback_rows = _extract_list(personal_info.get("emergency_contacts"))
    next_of_kin_rows = _extract_list(self_payload.get("next_of_kin")) or _extract_list(personal_info.get("next_of_kin"))
    source_rows = primary_rows or fallback_rows or next_of_kin_rows

    contacts: List[Dict[str, Any]] = []
    seen: set = set()
    for item in source_rows:
        name = _extract_first(item, ["name", "full_name"])
        phone = _extract_first(item, ["phone", "phone_number"])
        relationship = _extract_first(item, ["relationship", "relation"])
        key = (name.lower().strip(), phone.strip(), relationship.lower().strip())
        if key in seen:
            continue
        seen.add(key)
        contacts.append(
            {
                "name": name,
                "relationship": relationship,
                "phone": phone,
                "email": _extract_first(item, ["email"]),
                "address": _extract_first(item, ["address", "residential_address"]),
                "isPrimary": bool(item.get("is_primary", False)),
            }
        )
    return contacts


def _normalize_profile_documents(self_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    documents: List[Dict[str, Any]] = []
    seen: set = set()

    def _add(path: str, *, category: str = "Document", label: str = "") -> None:
        normalized_path = str(path or "").strip()
        if not normalized_path:
            return
        key = normalized_path.lower()
        if key in seen:
            return
        seen.add(key)
        name = label or normalized_path.split("/")[-1] or "Document"
        ext = name.split(".")[-1].upper() if "." in name else ""
        documents.append(
            {
                "name": name,
                "category": category,
                "type": ext,
                "path": normalized_path,
                "url": _build_document_url(normalized_path),
                "inlineUrl": _build_document_inline_url(normalized_path),
            }
        )

    for item in _extract_list(self_payload.get("documents")):
        _add(
            _extract_first(item, ["path", "file_path", "document_path", "url"]),
            category=_extract_first(item, ["category", "type"]) or "Document",
            label=_extract_first(item, ["name", "title"]),
        )

    for item in _extract_list(self_payload.get("academic_qualifications")):
        _add(
            _extract_first(item, ["certificate_path", "document_path"]),
            category="Academic Qualification",
            label=_extract_first(item, ["qualification", "title"]),
        )
    for item in _extract_list(self_payload.get("professional_qualifications")):
        _add(
            _extract_first(item, ["license_path", "document_path"]),
            category="Professional Qualification",
            label=_extract_first(item, ["qualification", "title"]),
        )

    custom_data = self_payload.get("custom_data") if isinstance(self_payload.get("custom_data"), dict) else {}
    nested_custom = custom_data.get("custom_data") if isinstance(custom_data.get("custom_data"), dict) else {}
    dynamic_data = nested_custom.get("dynamic_data") if isinstance(nested_custom.get("dynamic_data"), dict) else {}
    employment_details = dynamic_data.get("employment_details") if isinstance(dynamic_data.get("employment_details"), dict) else {}
    for key, value in employment_details.items():
        if isinstance(value, dict):
            payload_value = value.get("value")
            if isinstance(payload_value, list):
                for entry in payload_value:
                    _add(str(entry), category="Employment Detail", label=str(key))
            else:
                _add(str(payload_value or ""), category="Employment Detail", label=str(key))
        elif isinstance(value, list):
            for entry in value:
                _add(str(entry), category="Employment Detail", label=str(key))
        else:
            _add(str(value or ""), category="Employment Detail", label=str(key))
    return documents


_HONORIFIC_ALLOWED = {
    "mr",
    "mrs",
    "ms",
    "miss",
    "dr",
    "prof",
    "phd",
}


def _is_honorific(value: Any) -> bool:
    raw = str(value or "").strip()
    if not raw:
        return False
    compact = "".join(ch for ch in raw.lower() if ch.isalnum())
    return compact in _HONORIFIC_ALLOWED


def _extract_honorific_preserve(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    return raw if _is_honorific(raw) else ""


def _extract_profile_title(value: Any) -> str:
    """Trust explicit SRMS title values, but keep them bounded and printable."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    cleaned = "".join(ch for ch in raw if ch.isprintable()).strip()
    if not cleaned:
        return ""
    return cleaned[:64]


def _build_document_url(path_value: str) -> str:
    path_text = str(path_value or "").strip()
    if not path_text:
        return ""
    if path_text.startswith("http://") or path_text.startswith("https://"):
        return path_text
    settings = get_settings()
    base = str(settings.srms_base_url or "").strip().rstrip("/")
    if not base:
        return ""
    normalized_path = path_text.lstrip("/")
    if normalized_path.startswith("api/"):
        return f"{base}/{normalized_path}"
    return f"{base}/api/storage/download/{normalized_path}"


def _build_document_inline_url(path_value: str) -> str:
    path_text = str(path_value or "").strip()
    if not path_text:
        return ""
    return f"/profile/documents/inline?path={quote(path_text, safe='')}"


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _is_uuid(value: Any) -> bool:
    try:
        UUID(str(value or "").strip())
        return True
    except Exception:
        return False


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


@router.get("/catalog")
def get_module_catalog(
    user: AuthenticatedUser = Depends(get_current_user),
):
    if user.effective_role == "hris:super_admin":
        return {
            "tenant": {
                "tenant_id": "platform",
                "code": "PLATFORM",
                "name": "HRIS Platform",
                "status": "active",
            },
            "workflow_standard": {
                "version": "1.0",
                "shape": "module-catalog",
                "rbac_driven": True,
                "data_access": "capability-based",
            },
            # Platform superadmin routes are handled by dedicated admin pages.
            "modules": [],
        }

    mapping = get_tenant_mapping(user.tenant_id)
    manager_view = can_view_manager_sections(user)
    modules = []
    for module_id, status in mapping.modules.as_dict().items():
        normalized_module_id = _normalize_module_id(module_id)
        if not normalized_module_id:
            continue
        module_ui = _module_ui_info(normalized_module_id, manager_view, role=user.effective_role)
        configured_and_active = (
            bool(status.configured)
            and bool(status.ready)
            and str(status.status).lower() == "active"
        )
        readiness = check_module_readiness(
            module_name=normalized_module_id,
            mapping=mapping,
            user=user,
        )
        enabled = bool(configured_and_active and readiness.get("ready"))
        launch = build_module_launch_descriptor(normalized_module_id, mapping)
        modules.append(
            {
                "id": normalized_module_id,
                "label": module_ui["label"],
                "description": module_ui["description"],
                "status": status.model_dump(),
                "enabled": enabled,
                "visible": bool(configured_and_active),
                "ui": {
                    "icon": module_ui["icon"],
                    "path": module_ui["path"],
                    "manager_path": module_ui["manager_path"],
                    "self_path": module_ui["self_path"],
                    "launch": launch,
                },
                "capabilities": {
                    "manager_view": manager_view,
                    "self_service_view": True,
                    # Only modules with a real, dedicated native profile view
                    # belong in the unified profile hub.  A dashboard or an
                    # appraisal list is not a profile substitute.
                    "profile_view": normalized_module_id == "srms",
                    "profile_path": "/hris/profile" if normalized_module_id == "srms" else None,
                    "read_mode": "native-readonly",
                    "readiness": readiness,
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


@router.post("/catalog/{module_id}/handoff")
def issue_module_handoff(
    module_id: str,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    settings = get_settings()
    if not settings.module_handoff_enabled:
        raise HTTPException(status_code=403, detail="Module handoff is disabled by policy")
    mapping = get_tenant_mapping(user.tenant_id)
    normalized_module_id = _normalize_module_id(module_id)
    if not normalized_module_id:
        raise HTTPException(status_code=422, detail="Invalid module id")
    _ensure_module_ready(mapping, normalized_module_id)
    launch = build_module_launch_descriptor(normalized_module_id, mapping, expose_native_url=True)
    if not bool(launch.get("native_entry_available")):
        raise HTTPException(status_code=409, detail=f"Native launch is unavailable for module '{normalized_module_id}'")
    native_app_url = str(launch.get("native_app_url") or "").strip()
    if not native_app_url:
        raise HTTPException(status_code=409, detail=f"Native launch URL is missing for module '{normalized_module_id}'")
    tenant_routing_key = (
        mapping.srms_slug if normalized_module_id == "srms"
        else mapping.eappraisal_subdomain if normalized_module_id == "eappraisal"
        else mapping.eleave_subdomain
    )
    issued = issue_handoff_launch(
        user=user,
        module_id=normalized_module_id,
        tenant_id=mapping.tenant_id,
        tenant_routing_key=str(tenant_routing_key or ""),
        native_app_url=native_app_url,
        settings=settings,
    )
    logger.info(
        "Issued module handoff launch token",
        extra={
            "correlation_id": getattr(request.state, "correlation_id", ""),
            "tenant_id": mapping.tenant_id,
            "module_id": normalized_module_id,
            "jti": issued.get("jti"),
            "token_fingerprint": issued.get("token_fingerprint"),
        },
    )
    return {
        "module_id": normalized_module_id,
        "tenant_id": mapping.tenant_id,
        "tenant_slug": tenant_routing_key,
        "launch_url": issued.get("launch_url"),
        "expires_at": issued.get("expires_at"),
        "target_route": issued.get("target_route"),
        "open_mode": launch.get("open_mode"),
        "embeddable": True,
        "module_label": MODULE_UI_METADATA.get(normalized_module_id, {}).get("label", normalized_module_id),
    }


@router.post("/handoff/redeem")
def redeem_module_handoff(
    payload: ModuleHandoffRedeemRequest,
    request: Request,
):
    settings = get_settings()
    enforce_rate_limit(
        request,
        scope="module_handoff_redeem",
        limit=settings.rate_limit_module_redeem_max,
        user_key=f"module:{str(payload.module_id or '').strip().lower()}",
    )
    module_id = _normalize_module_id(payload.module_id)
    if not module_id:
        raise HTTPException(status_code=422, detail="Invalid module id")
    _require_module_service_auth(module_id, request)
    redeemed = redeem_handoff_token(
        token=payload.handoff_token,
        module_id=module_id,
        tenant_id=str(payload.tenant_id or ""),
    )
    logger.info(
        "Redeemed module handoff token",
        extra={
            "correlation_id": getattr(request.state, "correlation_id", ""),
            "tenant_id": redeemed.get("tenant_id"),
            "module_id": module_id,
            "jti": redeemed.get("jti"),
            "token_fingerprint": token_fingerprint(payload.handoff_token),
        },
    )
    return {
        "ok": True,
        "tenant_id": redeemed.get("tenant_id"),
        "module_id": module_id,
        "target_route": redeemed.get("target_route"),
        "session_bootstrap": {
            "sub": redeemed.get("sub"),
            "username": redeemed.get("username"),
            "email": redeemed.get("email"),
            "employee_id": redeemed.get("employee_id"),
        },
    }


@profile_router.get("/me")
def get_my_profile(
    request: Request,
    employee_id: Optional[str] = Query(None, description="Optional employee ID override"),
    user: AuthenticatedUser = Depends(get_current_user),
):
    correlation_id = getattr(request.state, "correlation_id", "")
    mapping = get_tenant_mapping(user.tenant_id)
    if not mapping.module_enabled("srms"):
        raise HTTPException(status_code=503, detail="SRMS profile module is not enabled for this tenant")
    if employee_id:
        enforce_self_or_privileged(user, employee_id, context="Profile lookup")
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
    self_employee_id = str(
        self_profile_payload.get("id")
        or (self_profile_payload.get("profile", {}) if isinstance(self_profile_payload.get("profile"), dict) else {}).get("employee_id")
        or ""
    ).strip()
    search_employee_id = str(
        best_search_row.get("employee_id") if isinstance(best_search_row, dict) else ""
    ).strip()
    # Keep SRMS identity authoritative for profile lookups to avoid cross-module ID drift.
    resolved_employee_id = str(employee_id or self_employee_id or search_employee_id or "").strip()
    preferred_fallback = employee_from_self if _has_rich_profile_fields(employee_from_self) else best_search_row
    employee_detail_fallback = _merge_employee_sources(
        preferred_fallback if isinstance(preferred_fallback, dict) else {},
        best_search_row if isinstance(best_search_row, dict) else {},
        employee_from_self if isinstance(employee_from_self, dict) else {},
    ) or {
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
    }
    if resolved_employee_id and _is_uuid(resolved_employee_id):
        employee_from_detail = _safe_get(
            lambda: srms_client.get_employee(mapping, str(resolved_employee_id), user.raw_token),
            employee_detail_fallback,
            module_name="srms.profile_employee",
            tenant_id=user.tenant_id,
            correlation_id=correlation_id,
        )
        employee = _merge_employee_sources(
            employee_from_detail if isinstance(employee_from_detail, dict) else {},
            employee_detail_fallback,
        )
    else:
        employee = employee_detail_fallback

    fallback_full_name = str(
        user.token_claims.get("name")
        or " ".join(
            [
                str(user.token_claims.get("given_name") or "").strip(),
                str(user.token_claims.get("family_name") or "").strip(),
            ]
        ).strip()
        or user.username
    ).strip()
    full_name = str(employee.get("full_name") or fallback_full_name).strip()
    self_profile_block = self_profile_payload.get("profile") if isinstance(self_profile_payload.get("profile"), dict) else {}
    self_personal_info = self_profile_payload.get("personal_info") if isinstance(self_profile_payload.get("personal_info"), dict) else {}
    self_contact_info = self_profile_payload.get("contact_info") if isinstance(self_profile_payload.get("contact_info"), dict) else {}
    parts = [p for p in full_name.split(" ") if p]
    first_name = (
        _extract_first(self_profile_block, ["first_name", "firstName"])
        or (parts[0] if parts else user.username)
    )
    last_name = (
        _extract_first(self_profile_block, ["last_name", "lastName"])
        or (parts[-1] if len(parts) > 1 else "")
    )
    other_names = (
        _extract_first(self_profile_block, ["middle_name", "middleName"])
        or (" ".join(parts[1:-1]) if len(parts) > 2 else "")
    )
    resolved_title = (
        _extract_profile_title(self_profile_payload.get("title"))
        or _extract_profile_title(self_profile_block.get("title"))
        or _extract_honorific_preserve(employee.get("position"))
    )
    raw_position = str(employee.get("position") or "").strip()
    position_value = "" if _is_honorific(raw_position) else raw_position
    qualifications = _normalize_profile_qualifications(self_profile_payload)
    emergency_contacts = _normalize_profile_emergency_contacts(self_profile_payload)
    documents = _normalize_profile_documents(self_profile_payload)
    date_of_birth = (
        _extract_first(self_personal_info, ["date_of_birth", "dateOfBirth"])
        or _extract_first(self_profile_payload, ["date_of_birth"])
    )
    marital_status = (
        _extract_first(self_personal_info, ["marital_status", "maritalStatus"])
        or _extract_first(self_profile_payload, ["marital_status"])
    )
    residential_address = (
        _extract_first(self_contact_info, ["residential_address", "address"])
        or _extract_first(self_personal_info.get("contact_info") if isinstance(self_personal_info.get("contact_info"), dict) else {}, ["residential_address", "address"])
    )
    phone_value = (
        str(employee.get("phone") or "").strip()
        or _extract_first(self_profile_block, ["phone", "phone_number"])
        or _extract_first(self_contact_info, ["phone", "phone_number"])
    )

    return {
        "profile": {
            "firstName": first_name,
            "lastName": last_name,
            "otherNames": other_names,
            "title": resolved_title,
            "staffId": employee.get("staff_id", ""),
            "email": employee.get("email", user.email or ""),
            "phone": phone_value,
            "personalEmail": "",
            "dateOfBirth": date_of_birth,
            "gender": employee.get("gender", ""),
            "maritalStatus": marital_status,
            "nationality": "",
            "ghanaCardNo": "",
            "ssnitNo": "",
            "tinNo": "",
            "residentialAddress": residential_address,
            "digitalAddress": "",
        },
        "employment": {
            "organization": employee.get("organization", ""),
            "branch": employee.get("branch", ""),
            "department": employee.get("department", ""),
            "unit": employee.get("unit", ""),
            "position": position_value,
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
        "emergency_contacts": emergency_contacts,
        "documents": documents,
        "qualifications": qualifications,
        "quick_stats": {
            "years_of_service": _years_of_service(employee.get("hire_date")),
            "leave_balance": "N/A",
            "appraisal_score": "N/A",
            "certifications": f"{len(qualifications)} active",
        },
    }


@profile_router.get("/documents/inline")
def get_my_profile_document_inline(
    path: str = Query(..., description="SRMS relative document path"),
    user: AuthenticatedUser = Depends(get_current_user),
):
    raw_path = str(path or "").strip()
    if not raw_path:
        raise HTTPException(status_code=422, detail="Document path is required")
    if raw_path.startswith("http://") or raw_path.startswith("https://"):
        raise HTTPException(status_code=400, detail="Absolute document URLs are not allowed")
    normalized_path = raw_path.lstrip("/")
    if ".." in normalized_path.replace("\\", "/").split("/"):
        raise HTTPException(status_code=400, detail="Invalid document path")

    mapping = get_tenant_mapping(user.tenant_id)
    _ensure_module_ready(mapping, "srms")
    source_url = _build_document_url(normalized_path)
    if not source_url:
        raise HTTPException(status_code=404, detail="Document URL is unavailable")

    headers: Dict[str, str] = {}
    if user.raw_token:
        headers["Authorization"] = f"Bearer {user.raw_token}"
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            upstream = client.get(source_url, headers=headers)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch document from SRMS: {exc}") from exc

    if upstream.status_code >= 400:
        raise HTTPException(status_code=upstream.status_code, detail="SRMS document fetch failed")

    filename = normalized_path.split("/")[-1] or "document"
    return Response(
        content=upstream.content,
        media_type=upstream.headers.get("content-type") or "application/octet-stream",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/appraisal")
def get_appraisal_module_data(
    request: Request,
    employee_id: Optional[str] = Query(None, description="Optional employee ID override"),
    user: AuthenticatedUser = Depends(get_current_user),
):
    correlation_id = getattr(request.state, "correlation_id", "")
    mapping = get_tenant_mapping(user.tenant_id)
    if not mapping.module_enabled("eappraisal"):
        try:
            jit_out = jit_setup_module_for_user(
                tenant_id=user.tenant_id,
                module_name="eappraisal",
                actor=user,
                dry_run=False,
            )
            if not jit_out.get("ok"):
                raise HTTPException(
                    status_code=403,
                    detail=str(jit_out.get("provision", {}).get("detail") or jit_out.get("detail") or "eAppraisal setup failed"),
                )
            mapping = get_tenant_mapping(user.tenant_id)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=403, detail=f"eAppraisal setup failed: {exc}") from exc
    _ensure_module_ready(mapping, "eappraisal")
    readiness = check_module_readiness(module_name="eappraisal", mapping=mapping, user=user)
    if not readiness.get("ready"):
        _raise_readiness_block(readiness, module_name="eappraisal")
    canonical_identity = resolve_canonical_identity(user)
    if employee_id:
        enforce_self_or_privileged(user, employee_id, context="Appraisal module lookup")
    resolved_employee_id = str(employee_id or canonical_identity.eappraisal.employee_id or "").strip()
    _require_resolved_module_identity("eappraisal", resolved_employee_id)
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
    employee_appraisals = (
        _safe_get(
            lambda: eappraisal_client.get_employee_appraisals(mapping, resolved_employee_id, user.raw_token),
            {"appraisals": []},
            module_name="eappraisal.employee_appraisals",
            tenant_id=user.tenant_id,
            correlation_id=correlation_id,
        )
        if resolved_employee_id
        else {"appraisals": []}
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


def _build_appraisal_capabilities(*, user: AuthenticatedUser, data: Dict[str, Any]) -> Dict[str, Any]:
    is_manager = can_view_manager_sections(user)
    manager_actions = [
        "create_cycle",
        "configure_section",
        "assign_reviewer",
        "approve_appraisal",
        "view_reports",
    ]
    employee_actions = [
        "submit_self_assessment",
        "update_goal",
        "add_comment",
        "view_past_appraisals",
    ]
    actions = manager_actions + employee_actions if is_manager else employee_actions
    allowlist = get_jit_action_allowlist(tenant_id=user.tenant_id, module_name="eappraisal")
    if allowlist:
        actions = [a for a in actions if a in allowlist]
    sections = ((data.get("employee") or {}).get("sections") or []) if isinstance(data, dict) else []
    section_statuses = [str((row or {}).get("status") or "").strip().lower() for row in sections if isinstance(row, dict)]
    state = "in_progress"
    if sections and all(s == "completed" for s in section_statuses if s):
        state = "ready_for_submission"
    if "locked" in section_statuses and not is_manager:
        state = "awaiting_supervisor"
    return {
        "module": "eappraisal",
        "version": "1.0",
        "features": [
            "manager_dashboard" if is_manager else "self_dashboard",
            "goal_tracking",
            "history_view",
        ],
        "actions": sorted(list(dict.fromkeys(actions))),
        "workflow": {"state": state, "stage": "appraisal_cycle"},
    }


@router.get("/appraisal/capabilities")
def get_appraisal_capabilities(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    payload = get_appraisal_module_data(request=request, employee_id=None, user=user)
    return _build_appraisal_capabilities(user=user, data=payload)


@router.get("/appraisal/tasks")
def get_appraisal_tasks(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    payload = get_appraisal_module_data(request=request, employee_id=None, user=user)
    capabilities = _build_appraisal_capabilities(user=user, data=payload)
    tasks: List[Dict[str, Any]] = []
    sections = ((payload.get("employee") or {}).get("sections") or []) if isinstance(payload, dict) else []
    for idx, section in enumerate(sections):
        if not isinstance(section, dict):
            continue
        status = str(section.get("status") or "").strip().lower()
        if status in {"in_progress", "not_started"}:
            tasks.append(
                {
                    "task_id": f"employee-section-{idx+1}",
                    "module": "eappraisal",
                    "title": f"Complete section: {section.get('name') or 'Section'}",
                    "status": status,
                    "action_id": "submit_self_assessment",
                }
            )
    manager_recent = ((payload.get("manager") or {}).get("recent_activity") or []) if isinstance(payload, dict) else []
    for idx, row in enumerate(manager_recent):
        if not isinstance(row, dict):
            continue
        row_status = str(row.get("status") or "").strip().lower()
        if row_status == "pending":
            tasks.append(
                {
                    "task_id": f"manager-review-{idx+1}",
                    "module": "eappraisal",
                    "title": f"Review pending appraisal: {row.get('name') or 'staff'}",
                    "status": row_status,
                    "action_id": "approve_appraisal",
                }
            )
    return {"module": "eappraisal", "workflow": capabilities.get("workflow"), "tasks": tasks}


@router.post("/appraisal/actions/{action_id}")
def execute_appraisal_action(
    request: Request,
    action_id: str,
    payload: Optional[Dict[str, Any]] = None,
    user: AuthenticatedUser = Depends(get_current_user),
):
    capabilities = get_appraisal_capabilities(request=request, user=user)
    normalized_action = str(action_id or "").strip().lower()
    allowed = [str(x).strip().lower() for x in (capabilities.get("actions") or [])]
    if normalized_action not in allowed:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "target_denied",
                "message": f"Action '{normalized_action}' is not allowed for this user in appraisal workflow",
                "action": "refresh_capabilities",
                "module": "eappraisal",
            },
        )
    # Dual-check: probe native module access before allowing action handoff.
    mapping = get_tenant_mapping(user.tenant_id)
    _ = eappraisal_client.get_my_appraisals(mapping, user.raw_token)
    return {
        "ok": False,
        "status": "native_action_required",
        "module": "eappraisal",
        "action_id": normalized_action,
        "detail": "Native module final action endpoint is required for write execution.",
    }


@router.get("/appraisal/history/{entry_id}")
def get_appraisal_history_detail(
    request: Request,
    entry_id: str,
    employee_id: Optional[str] = Query(None, description="Optional employee ID override"),
    user: AuthenticatedUser = Depends(get_current_user),
):
    correlation_id = getattr(request.state, "correlation_id", "")
    mapping = get_tenant_mapping(user.tenant_id)
    _ensure_module_ready(mapping, "eappraisal")
    canonical_identity = resolve_canonical_identity(user)
    if employee_id:
        enforce_self_or_privileged(user, employee_id, context="Appraisal history lookup")
    resolved_employee_id = str(employee_id or canonical_identity.eappraisal.employee_id or "").strip()
    _require_resolved_module_identity("eappraisal", resolved_employee_id)
    if not resolved_employee_id:
        raise HTTPException(status_code=422, detail="Unable to resolve appraisal employee identity")
    employee_appraisals = _safe_get(
        lambda: eappraisal_client.get_employee_appraisals(mapping, resolved_employee_id, user.raw_token),
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
    mapping = get_tenant_mapping(user.tenant_id)
    _ensure_module_ready(mapping, "eleave")
    leave_readiness = check_module_readiness(module_name="eleave", mapping=mapping, user=user)
    if not leave_readiness.get("ready"):
        _raise_readiness_block(leave_readiness, module_name="eleave")
    canonical_identity = resolve_canonical_identity(user)
    if employee_id:
        enforce_self_or_privileged(user, employee_id, context="Leave module lookup")
    resolved_employee_id = str(employee_id or canonical_identity.eleave.employee_id or "").strip()
    _require_resolved_module_identity("eleave", resolved_employee_id)
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
    leave_history = (
        _safe_get(
            lambda: eleave_client.get_employee_leave_history(mapping, resolved_employee_id, user.raw_token),
            {"leaves": [], "balance": {}, "used": {}},
            module_name="eleave.employee_history",
            tenant_id=user.tenant_id,
            correlation_id=correlation_id,
        )
        if resolved_employee_id
        else {"leaves": [], "balance": {}, "used": {}}
    )

    raw_history: List[Dict[str, Any]] = leave_history.get("leaves", [])
    normalized_history = [
        {
            "id": str(item.get("id") or item.get("leave_id") or item.get("request_id") or f"L{i + 1:03d}"),
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
            "total": _safe_int(total_days),
            "used": _safe_int(used.get(name, 0)),
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
