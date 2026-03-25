import re
from functools import lru_cache
from typing import Any, Dict, List, Optional

import httpx
from fastapi import HTTPException, status

from app.core.settings import get_settings
from app.models.tenant_mapping import ModuleStatus, TenantMapping, TenantModules


def _normalize_module_id(raw_module_id: str) -> Optional[str]:
    if not isinstance(raw_module_id, str):
        return None
    module_id = raw_module_id.strip().lower()
    if not module_id:
        return None
    if not re.fullmatch(r"[a-z][a-z0-9_-]*", module_id):
        return None
    return module_id


def _stub_tenant(tenant_id: str) -> TenantMapping:
    return TenantMapping(
        tenant_id=tenant_id,
        code="DEV-TENANT",
        name="Development Tenant",
        srms_schema="tenant_dev",
        srms_slug="dev-org",
        eappraisal_subdomain="devsub",
        eleave_subdomain="devsub",
        is_active=True,
        lifecycle_status="active",
        modules=TenantModules(
            srms=ModuleStatus(status="active", ready=True, configured=True),
            eappraisal=ModuleStatus(status="active", ready=True, configured=True),
            eleave=ModuleStatus(status="active", ready=True, configured=True),
        ),
    )


def _derive_modules(data: dict) -> TenantModules:
    raw_modules = data.get("modules")
    if isinstance(raw_modules, dict):
        normalized: Dict[str, ModuleStatus] = {}
        for module_name, module_value in raw_modules.items():
            module_key = _normalize_module_id(module_name)
            if not module_key:
                continue
            if isinstance(module_value, dict):
                normalized[module_key] = ModuleStatus(
                    status=str(module_value.get("status", "inactive")),
                    ready=bool(module_value.get("ready", False)),
                    configured=bool(module_value.get("configured", False)),
                )
                continue
            if isinstance(module_value, bool):
                normalized[module_key] = ModuleStatus(
                    status="active" if module_value else "inactive",
                    ready=module_value,
                    configured=module_value,
                )
                continue
            if isinstance(module_value, str):
                active = module_value.strip().lower() in {"active", "enabled", "ready", "true", "1"}
                normalized[module_key] = ModuleStatus(
                    status="active" if active else "inactive",
                    ready=active,
                    configured=active,
                )
        if normalized:
            return TenantModules(**{name: status.model_dump() for name, status in normalized.items()})

    legacy_modules = {
        "srms": ModuleStatus(
            status="active" if data.get("srms_schema") or data.get("srms_slug") else "inactive",
            ready=bool(data.get("srms_schema") or data.get("srms_slug")),
            configured=bool(data.get("srms_schema") or data.get("srms_slug")),
        ),
        "eappraisal": ModuleStatus(
            status="active" if data.get("eappraisal_subdomain") else "inactive",
            ready=bool(data.get("eappraisal_subdomain")),
            configured=bool(data.get("eappraisal_subdomain")),
        ),
        "eleave": ModuleStatus(
            status="active" if data.get("eleave_subdomain") else "inactive",
            ready=bool(data.get("eleave_subdomain")),
            configured=bool(data.get("eleave_subdomain")),
        ),
    }
    return TenantModules(**{name: status.model_dump() for name, status in legacy_modules.items()})


def _build_mapping(data: dict) -> TenantMapping:
    payload = dict(data)
    payload.setdefault("lifecycle_status", "active")
    payload["modules"] = _derive_modules(payload)
    return TenantMapping(**payload)


@lru_cache(maxsize=1024)
def get_tenant_mapping(tenant_id: str) -> TenantMapping:
    settings = get_settings()

    if settings.use_stub_data:
        return _stub_tenant(tenant_id)

    url = f"{settings.tenant_registry_base_url}/tenants/{tenant_id}"
    auth = (settings.tenant_registry_basic_auth_username, settings.tenant_registry_basic_auth_password)

    try:
        with httpx.Client(timeout=settings.tenant_registry_timeout_seconds) as client:
            response = client.get(url, auth=auth)
            if response.status_code == 404:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Tenant '{tenant_id}' not found in Tenant Registry",
                )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        if settings.tenant_registry_allow_fallback:
            return _stub_tenant(tenant_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to reach Tenant Registry: {exc}",
        ) from exc

    mapping = _build_mapping(data)
    if not mapping.is_tenant_active():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Tenant '{tenant_id}' is not active",
        )
    return mapping


def refresh_tenant_mapping_cache() -> None:
    get_tenant_mapping.cache_clear()


def _stub_tenants() -> List[TenantMapping]:
    return [
        _stub_tenant("11111111-1111-1111-1111-111111111111"),
        TenantMapping(
            tenant_id="22222222-2222-2222-2222-222222222222",
            code="MOF",
            name="Ministry of Finance",
            srms_schema="tenant_mof",
            srms_slug="mof",
            eappraisal_subdomain="mof",
            eleave_subdomain="mof",
            is_active=True,
            lifecycle_status="active",
            modules=TenantModules(
                srms=ModuleStatus(status="active", ready=True, configured=True),
                eappraisal=ModuleStatus(status="inactive", ready=False, configured=False),
                eleave=ModuleStatus(status="active", ready=True, configured=True),
            ),
        ),
    ]


def list_tenant_mappings(limit: int = 200) -> List[TenantMapping]:
    settings = get_settings()
    if settings.use_stub_data:
        return _stub_tenants()[: max(1, limit)]

    url = f"{settings.tenant_registry_base_url}/tenants"
    auth = (settings.tenant_registry_basic_auth_username, settings.tenant_registry_basic_auth_password)
    params: Dict[str, Any] = {"limit": max(1, min(limit, 1000))}
    try:
        with httpx.Client(timeout=settings.tenant_registry_timeout_seconds) as client:
            response = client.get(url, auth=auth, params=params)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        if settings.tenant_registry_allow_fallback:
            return _stub_tenants()[: max(1, limit)]
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to list tenants from Tenant Registry: {exc}",
        ) from exc

    rows: List[Dict[str, Any]] = []
    if isinstance(payload, list):
        rows = [row for row in payload if isinstance(row, dict)]
    elif isinstance(payload, dict):
        if isinstance(payload.get("tenants"), list):
            rows = [row for row in payload["tenants"] if isinstance(row, dict)]
        elif isinstance(payload.get("items"), list):
            rows = [row for row in payload["items"] if isinstance(row, dict)]
        elif isinstance(payload.get("data"), list):
            rows = [row for row in payload["data"] if isinstance(row, dict)]

    mappings: List[TenantMapping] = []
    for row in rows:
        try:
            mappings.append(_build_mapping(row))
        except Exception:
            continue
    return mappings[: max(1, limit)]


def import_tenant_if_missing(candidate: Dict[str, Any]) -> Dict[str, Any]:
    settings = get_settings()
    if settings.use_stub_data:
        return {"inserted": False, "reason": "stub_mode"}

    payload: Dict[str, Any] = {
        "tenant_id": (str(candidate.get("tenant_id") or "").strip() or None),
        "code": str(candidate.get("code") or "").strip(),
        "name": str(candidate.get("name") or "").strip(),
        "srms_schema": (str(candidate.get("srms_schema") or "").strip() or None),
        "srms_slug": (str(candidate.get("srms_slug") or "").strip() or None),
        "eappraisal_subdomain": (str(candidate.get("eappraisal_subdomain") or "").strip() or None),
        "eleave_subdomain": (str(candidate.get("eleave_subdomain") or "").strip() or None),
        "is_active": bool(candidate.get("is_active", True)),
    }
    if not payload["code"] or not payload["name"]:
        return {"inserted": False, "reason": "missing_code_or_name"}

    url = f"{settings.tenant_registry_base_url}/tenants/sync/import"
    auth = (settings.tenant_registry_basic_auth_username, settings.tenant_registry_basic_auth_password)
    try:
        with httpx.Client(timeout=settings.tenant_registry_timeout_seconds) as client:
            response = client.post(url, auth=auth, json=payload)
            response.raise_for_status()
            body = response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to import tenant into Tenant Registry: {exc}",
        ) from exc

    refresh_tenant_mapping_cache()
    inserted = bool(body.get("inserted")) if isinstance(body, dict) else False
    tenant = body.get("tenant") if isinstance(body, dict) else None
    tenant_id: Optional[str] = None
    if isinstance(tenant, dict):
        tenant_id = str(tenant.get("tenant_id") or "").strip() or None
    return {"inserted": inserted, "tenant_id": tenant_id, "payload": body}


def import_tenant(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Import/upsert a tenant into the Tenant Registry via the internal sync endpoint.

    Unlike import_tenant_if_missing(), this function runs even when USE_STUB_DATA=true,
    because tenant onboarding is a control-plane operation (not a module data read).
    """
    settings = get_settings()

    normalized: Dict[str, Any] = {
        "tenant_id": (str(payload.get("tenant_id") or "").strip() or None),
        "code": str(payload.get("code") or "").strip(),
        "name": str(payload.get("name") or "").strip(),
        "srms_schema": (str(payload.get("srms_schema") or "").strip() or None),
        "srms_slug": (str(payload.get("srms_slug") or "").strip() or None),
        "eappraisal_subdomain": (str(payload.get("eappraisal_subdomain") or "").strip() or None),
        "eleave_subdomain": (str(payload.get("eleave_subdomain") or "").strip() or None),
        "is_active": bool(payload.get("is_active", True)),
    }
    if not normalized["code"] or not normalized["name"]:
        raise HTTPException(status_code=422, detail="code and name are required")

    url = f"{settings.tenant_registry_base_url}/tenants/sync/import"
    auth = (settings.tenant_registry_basic_auth_username, settings.tenant_registry_basic_auth_password)
    try:
        with httpx.Client(timeout=settings.tenant_registry_timeout_seconds) as client:
            response = client.post(url, auth=auth, json=normalized)
            response.raise_for_status()
            body = response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to import tenant into Tenant Registry: {exc}",
        ) from exc

    refresh_tenant_mapping_cache()
    return {"payload": body}
