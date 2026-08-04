from typing import Any, Dict, Optional

from app.core.settings import get_settings
from app.services import automation_store
from app.services.tenant_storage_service import TenantStorageService


def get_tenant_branding(tenant_id: str) -> Dict[str, Any]:
    settings = get_settings()
    stored = automation_store.get_tenant_setting(tenant_id=tenant_id, setting_key="branding") or {}
    if not isinstance(stored, dict):
        stored = {}
    return {
        "brand_name": str(stored.get("brand_name") or settings.tenant_brand_name_default),
        "support_email": str(stored.get("support_email") or settings.tenant_support_email_default),
        "logo_primary_uri": str(stored.get("logo_primary_uri") or ""),
        "logo_symbol_uri": str(stored.get("logo_symbol_uri") or ""),
        "favicon_uri": str(stored.get("favicon_uri") or ""),
        "theme": stored.get("theme") if isinstance(stored.get("theme"), dict) else {},
    }


def upsert_tenant_branding(
    tenant_id: str,
    *,
    brand_name: Optional[str] = None,
    support_email: Optional[str] = None,
    theme: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    current = get_tenant_branding(tenant_id)
    if brand_name is not None:
        current["brand_name"] = str(brand_name).strip() or current["brand_name"]
    if support_email is not None:
        current["support_email"] = str(support_email).strip() or current["support_email"]
    if isinstance(theme, dict):
        current["theme"] = theme
    automation_store.upsert_tenant_setting(tenant_id=tenant_id, setting_key="branding", value=current)
    return current


def upload_tenant_logo(
    tenant_id: str,
    *,
    logo_kind: str,
    file_name: str,
    content: bytes,
    content_type: Optional[str],
) -> Dict[str, Any]:
    kind = str(logo_kind or "primary").strip().lower()
    key_map = {
        "primary": "logo_primary_uri",
        "symbol": "logo_symbol_uri",
        "favicon": "favicon_uri",
    }
    if kind not in key_map:
        raise ValueError("logo_kind must be one of: primary, symbol, favicon")

    storage = TenantStorageService()
    write = storage.store_document(
        tenant_id=tenant_id,
        owner_type="system",
        owner_id="system",
        document_key=f"branding_{kind}",
        file_name=file_name,
        content=content,
        content_type=content_type,
    )
    current = get_tenant_branding(tenant_id)
    current[key_map[kind]] = f"/tenants/{tenant_id}/media/system/system/branding_{kind}"
    automation_store.upsert_tenant_setting(tenant_id=tenant_id, setting_key="branding", value=current)
    return {"branding": current, "asset": write}
