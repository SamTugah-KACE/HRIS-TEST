import json
import unicodedata
from typing import Any, Dict, List

from fastapi import HTTPException, status

from app.clients import srms_client
from app.core.auth import AuthenticatedUser
from app.core.settings import get_settings
from app.services.tenant_registry_client import import_tenant_if_missing, list_tenant_mappings
from app.services import automation_store
from app.clients import eappraisal_client


def _as_str(value: Any) -> str:
    return str(value or "").strip()


def _normalized_label(value: Any) -> str:
    return " ".join(unicodedata.normalize("NFKC", _as_str(value)).casefold().split())


def _record_explicit_projection(module_name: str, candidate: Dict[str, Any], source: Dict[str, Any]) -> None:
    """Activate only a native record carrying an exact existing canonical UUID."""
    canonical_id = _as_str(candidate.get("canonical_tenant_id"))
    if not canonical_id:
        return
    canonical_ids = {str(row.tenant_id) for row in list_tenant_mappings(limit=5000)}
    if canonical_id not in canonical_ids:
        raise RuntimeError("Native tenant reports an unknown canonical_tenant_id")
    automation_store.upsert_module_projection(
        canonical_tenant_id=canonical_id,
        module_name=module_name,
        native_tenant_id=_as_str(candidate.get("tenant_id")),
        state="verified",
        routing={
            "routing_key": _as_str(candidate.get("srms_slug") or candidate.get("eappraisal_subdomain")),
            "proof_type": "native_persisted_canonical_id",
            "source_version": _as_str(source.get("identity_version") or source.get("version")),
        },
        verified=True,
    )


def _auto_create_canonical_tenant(
    module_name: str, candidate: Dict[str, Any], source: Dict[str, Any]
) -> Dict[str, Any]:
    """Compatibility bootstrap for deployments that do not yet use tenant claims.

    A native tenant becomes its own canonical tenant. This deliberately creates
    no cross-module correlation: another module remains a separate tenant unless
    it reports the same canonical UUID or is linked through the federation flow.
    """
    result = import_tenant_if_missing(candidate)
    canonical_id = _as_str(result.get("tenant_id"))
    if not canonical_id:
        raise RuntimeError("Tenant Registry import did not return a canonical tenant_id")
    automation_store.upsert_native_tenant_inventory(
        module_name=module_name,
        native_tenant_id=_as_str(candidate.get("tenant_id")),
        reported_canonical_tenant_id=canonical_id,
        display_name=_as_str(candidate.get("name")),
        normalized_name=_normalized_label(candidate.get("name")),
        routing_key=_as_str(candidate.get("srms_slug") or candidate.get("eappraisal_subdomain")) or None,
        source_version=_as_str(source.get("identity_version") or source.get("version")) or None,
        source_updated_at=_as_str(source.get("updated_at")) or None,
        metadata=source,
        inventory_status="claimed",
    )
    automation_store.upsert_module_projection(
        canonical_tenant_id=canonical_id,
        module_name=module_name,
        native_tenant_id=_as_str(candidate.get("tenant_id")),
        state="verified",
        routing={
            "routing_key": _as_str(candidate.get("srms_slug") or candidate.get("eappraisal_subdomain")),
            "proof_type": "compatibility_native_auto_import",
            "source_version": _as_str(source.get("identity_version") or source.get("version")),
        },
        verified=True,
    )
    return result


def _apply_explicit_reconciliation_alias(candidate: Dict[str, Any], module_name: str) -> Dict[str, Any]:
    aliases = json.loads(get_settings().tenant_reconciliation_aliases_json or "{}")
    configured = {str(key).strip().lower(): _as_str(value) for key, value in aliases.items()}
    target_ref = next(
        (
            configured.get(f"{module_name}:{_as_str(ref)}".lower())
            for ref in (candidate.get("tenant_id"), candidate.get("code"), candidate.get("name"))
            if configured.get(f"{module_name}:{_as_str(ref)}".lower())
        ),
        "",
    )
    if not target_ref:
        return candidate
    target_norm = target_ref.lower()
    # Alias values must resolve to an immutable canonical tenant UUID. Display
    # names and codes are neither globally unique nor stable and must never
    # authorize a cross-module tenant merge.
    target = next((row for row in list_tenant_mappings(limit=5000) if target_norm == row.tenant_id.lower()), None)
    if target is None:
        raise RuntimeError(f"Configured tenant reconciliation target '{target_ref}' was not found")
    resolved = dict(candidate)
    resolved.update({"tenant_id": target.tenant_id, "code": target.code, "name": target.name})
    return resolved


def _normalize_srms_org(org: Dict[str, Any]) -> Dict[str, Any]:
    srms_slug = _as_str(org.get("tenant_slug")) or _as_str(org.get("slug"))
    tenant_url = _as_str(org.get("tenant_url")) or _as_str(org.get("access_url"))
    return {
        "tenant_id": _as_str(org.get("tenant_id")) or None,
        "canonical_tenant_id": _as_str(org.get("canonical_tenant_id")) or None,
        "code": _as_str(org.get("code")) or srms_slug or tenant_url or _as_str(org.get("name")),
        "name": _as_str(org.get("name")) or _as_str(org.get("code")) or "Unknown Tenant",
        "srms_slug": srms_slug or None,
        "srms_schema": (
            _as_str(org.get("srms_schema"))
            or _as_str(org.get("schema_name"))
            or _as_str(org.get("schema"))
            or None
        ),
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
    if not ((token or "").strip() or has_secret_auth):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "SRMS_HRIS_SHARED_SECRET/SRMS_HRIS_SERVICE_TOKEN or "
                "SRMS_SERVICE_TOKEN/SRMS_INTEGRATION_TOKEN is required for startup SRMS tenant inventory import"
            ),
        )

    payload = srms_client.list_integration_tenants(token)
    organizations = payload.get("organizations", []) if isinstance(payload, dict) else []
    organizations = [row for row in organizations if isinstance(row, dict)][: max(1, max_records)]

    scanned = 0
    inserted = 0
    canonical_created = 0
    projections_created = 0
    skipped = 0
    errors: List[Dict[str, str]] = []

    for org in organizations:
        scanned += 1
        candidate = _normalize_srms_org(org)
        if not candidate.get("tenant_id") or not candidate.get("code") or not candidate.get("name"):
            skipped += 1
            continue
        try:
            explicit = bool(_as_str(candidate.get("canonical_tenant_id")))
            automation_store.upsert_native_tenant_inventory(
                module_name="srms", native_tenant_id=_as_str(candidate.get("tenant_id")),
                reported_canonical_tenant_id=_as_str(candidate.get("canonical_tenant_id")) or None,
                display_name=_as_str(candidate.get("name")), normalized_name=_normalized_label(candidate.get("name")),
                routing_key=_as_str(candidate.get("srms_slug")) or None,
                source_version=_as_str(org.get("identity_version") or org.get("version")) or None,
                source_updated_at=_as_str(org.get("updated_at")) or None, metadata=org,
                inventory_status="claimed" if explicit else "unclaimed",
            )
            if explicit:
                _record_explicit_projection("srms", candidate, org)
                projections_created += 1
            elif settings.tenant_inventory_auto_create_canonical:
                canonical_result = _auto_create_canonical_tenant("srms", candidate, org)
                canonical_created += int(bool(canonical_result.get("inserted")))
                projections_created += 1
            inserted += 1
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
        "native_inventory_upserted": inserted,
        "canonical_tenants_created": canonical_created,
        "projections_created": projections_created,
        "skipped": skipped,
        "errors": errors[:50],
    }


def _normalize_eappraisal_tenant(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize eAppraisal inventory tenants to Tenant Registry import shape.
    """
    tenant_id = _as_str(row.get("tenant_id") or row.get("id")) or None
    code = _as_str(row.get("code") or row.get("tenant_code") or row.get("slug") or row.get("name"))
    name = _as_str(row.get("name") or row.get("tenant_name") or row.get("code")) or "Unknown Tenant"
    # Prefer explicit routing hint fields; fall back to slug/code when present.
    subdomain = _as_str(
        row.get("eappraisal_subdomain")
        or row.get("subdomain")
        or row.get("tenant_slug")
        or row.get("slug")
        or code
    )
    status = _as_str(row.get("status") or row.get("lifecycle_status"))
    is_active = status.lower() != "inactive" if status else True
    return {
        "tenant_id": tenant_id,
        "canonical_tenant_id": _as_str(row.get("canonical_tenant_id")) or None,
        "code": code,
        "name": name,
        "eappraisal_subdomain": subdomain or None,
        "is_active": bool(is_active),
    }


def import_missing_tenants_from_eappraisal(
    actor: AuthenticatedUser, *, max_records: int = 500
) -> Dict[str, Any]:
    """
    Optional control-plane import from eAppraisal integration inventory endpoint:
    GET /api/hris/v1/integration/tenants
    """
    settings = get_settings()
    token = actor.raw_token or settings.eappraisal_service_token

    # Only run when an integration base URL is configured; do not block startup otherwise.
    if not (settings.eappraisal_integration_base_url or "").strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="EAPPRAISAL_INTEGRATION_BASE_URL is required for eAppraisal tenant inventory import",
        )

    payload = eappraisal_client.list_integration_tenants(token, limit=max(1, min(int(max_records or 500), 2000)))
    tenants = payload.get("tenants", []) if isinstance(payload, dict) else []
    tenants = [row for row in tenants if isinstance(row, dict)][: max(1, max_records)]

    scanned = 0
    inserted = 0
    canonical_created = 0
    projections_created = 0
    skipped = 0
    errors: List[Dict[str, str]] = []

    for row in tenants:
        scanned += 1
        candidate = _normalize_eappraisal_tenant(row)
        if not candidate.get("tenant_id") or not candidate.get("code") or not candidate.get("name"):
            skipped += 1
            continue
        try:
            explicit = bool(_as_str(candidate.get("canonical_tenant_id")))
            automation_store.upsert_native_tenant_inventory(
                module_name="eappraisal", native_tenant_id=_as_str(candidate.get("tenant_id")),
                reported_canonical_tenant_id=_as_str(candidate.get("canonical_tenant_id")) or None,
                display_name=_as_str(candidate.get("name")), normalized_name=_normalized_label(candidate.get("name")),
                routing_key=_as_str(candidate.get("eappraisal_subdomain")) or None,
                source_version=_as_str(row.get("identity_version") or row.get("version")) or None,
                source_updated_at=_as_str(row.get("updated_at")) or None, metadata=row,
                inventory_status="claimed" if explicit else "unclaimed",
            )
            if explicit:
                _record_explicit_projection("eappraisal", candidate, row)
                projections_created += 1
            elif settings.tenant_inventory_auto_create_canonical:
                canonical_result = _auto_create_canonical_tenant("eappraisal", candidate, row)
                canonical_created += int(bool(canonical_result.get("inserted")))
                projections_created += 1
            inserted += 1
        except Exception as exc:
            errors.append(
                {
                    "tenant_id": _as_str(candidate.get("tenant_id")),
                    "code": _as_str(candidate.get("code")),
                    "error": str(exc),
                }
            )

    return {
        "source": "eappraisal",
        "scanned": scanned,
        "inserted": inserted,
        "native_inventory_upserted": inserted,
        "canonical_tenants_created": canonical_created,
        "projections_created": projections_created,
        "skipped": skipped,
        "errors": errors[:50],
    }
