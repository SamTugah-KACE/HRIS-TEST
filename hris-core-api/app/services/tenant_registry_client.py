from functools import lru_cache

import httpx
from fastapi import HTTPException, status

from app.core.settings import get_settings
from app.models.tenant_mapping import TenantMapping


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
    )


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
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to reach Tenant Registry: {exc}",
        ) from exc

    mapping = TenantMapping(**data)
    if not mapping.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Tenant '{tenant_id}' is inactive",
        )
    return mapping
