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
        "short_name": str(stored.get("short_name") or ""),
        "support_email": str(stored.get("support_email") or settings.tenant_support_email_default),
        "support_phone": str(stored.get("support_phone") or ""),
        "website": str(stored.get("website") or ""),
        "locale": str(stored.get("locale") or "en-GH"),
        "timezone": str(stored.get("timezone") or "Africa/Accra"),
        "date_format": str(stored.get("date_format") or "DD/MM/YYYY"),
        "logo_primary_uri": str(stored.get("logo_primary_uri") or ""),
        "logo_symbol_uri": str(stored.get("logo_symbol_uri") or ""),
        "favicon_uri": str(stored.get("favicon_uri") or ""),
        "login_background_uri": str(stored.get("login_background_uri") or ""),
        "theme": stored.get("theme") if isinstance(stored.get("theme"), dict) else {},
    }


def upsert_tenant_branding(
    tenant_id: str,
    *,
    brand_name: Optional[str] = None,
    short_name: Optional[str] = None,
    support_email: Optional[str] = None,
    support_phone: Optional[str] = None,
    website: Optional[str] = None,
    locale: Optional[str] = None,
    timezone: Optional[str] = None,
    date_format: Optional[str] = None,
    theme: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    current = get_tenant_branding(tenant_id)
    if brand_name is not None:
        current["brand_name"] = str(brand_name).strip() or current["brand_name"]
    if short_name is not None:
        current["short_name"] = str(short_name).strip()[:40]
    if support_email is not None:
        current["support_email"] = str(support_email).strip() or current["support_email"]
    for key, value in (("support_phone", support_phone), ("website", website), ("locale", locale), ("timezone", timezone), ("date_format", date_format)):
        if value is not None:
            current[key] = str(value).strip()
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
        "login_background": "login_background_uri",
    }
    if kind not in key_map:
        raise ValueError("logo_kind must be one of: primary, symbol, favicon, login_background")

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
