from typing import Any, Dict, List

from fastapi import HTTPException, status

from app.clients import srms_client
from app.core.auth import AuthenticatedUser
from app.core.settings import get_settings
from app.services.tenant_registry_client import import_tenant_if_missing


def _as_str(value: Any) -> str:
    return str(value or "").strip()


def _normalize_srms_org(org: Dict[str, Any]) -> Dict[str, Any]:
    srms_slug = _as_str(org.get("tenant_slug")) or _as_str(org.get("slug"))
    tenant_url = _as_str(org.get("tenant_url")) or _as_str(org.get("access_url"))
    return {
        "tenant_id": _as_str(org.get("tenant_id")) or None,
        "code": _as_str(org.get("code")) or srms_slug or tenant_url or _as_str(org.get("name")),
        "name": _as_str(org.get("name")) or _as_str(org.get("code")) or "Unknown Tenant",
        "srms_slug": srms_slug or None,
        "srms_schema": _as_str(org.get("schema")) or _as_str(org.get("srms_schema")) or None,
        "is_active": _as_str(org.get("status")).lower() != "inactive",
    }


def import_missing_tenants_from_srms(actor: AuthenticatedUser, *, max_records: int = 500) -> Dict[str, Any]:
    settings = get_settings()
    has_secret_auth = bool(
        (settings.srms_hris_shared_secret or "").strip()
        or (settings.srms_hris_service_token or "").strip()
    )
    token = (
        actor.raw_token
        or settings.srms_service_token
        or settings.srms_integration_token
    )
    if not settings.use_stub_data and not ((token or "").strip() or has_secret_auth):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "SRMS_HRIS_SHARED_SECRET/SRMS_HRIS_SERVICE_TOKEN or "
                "SRMS_SERVICE_TOKEN/SRMS_INTEGRATION_TOKEN is required for startup SRMS tenant inventory import "
                "when USE_STUB_DATA=false"
            ),
        )

    payload = srms_client.list_integration_tenants(token)
    organizations = payload.get("organizations", []) if isinstance(payload, dict) else []
    organizations = [row for row in organizations if isinstance(row, dict)][: max(1, max_records)]

    scanned = 0
    inserted = 0
    skipped = 0
    errors: List[Dict[str, str]] = []

    for org in organizations:
        scanned += 1
        candidate = _normalize_srms_org(org)
        if not candidate.get("code") or not candidate.get("name"):
            skipped += 1
            continue
        try:
            result = import_tenant_if_missing(candidate)
            if result.get("inserted"):
                inserted += 1
            else:
                skipped += 1
        except Exception as exc:
            errors.append(
                {
                    "tenant_id": _as_str(candidate.get("tenant_id")),
                    "code": _as_str(candidate.get("code")),
                    "error": str(exc),
                }
            )

    return {
        "source": "srms",
        "scanned": scanned,
        "inserted": inserted,
        "skipped": skipped,
        "errors": errors[:50],
    }
