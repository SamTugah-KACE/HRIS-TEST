from __future__ import annotations

import base64
import hashlib
import json
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet, InvalidToken

from app.core.settings import get_settings
from app.services import automation_store
from app.services.providers.arkesel import ArkeselVerificationProvider


def _fernet() -> Fernet:
    settings = get_settings()
    configured = str(settings.provider_secret_encryption_key or "").strip().encode()
    if configured:
        try:
            return Fernet(configured)
        except ValueError:
            pass
    fallback = str(settings.auth_session_encryption_key or settings.auth_state_secret or "").encode()
    if not fallback:
        raise RuntimeError("Provider secret encryption is not configured")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(fallback).digest()))


def _encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def _decrypt_secret(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except (InvalidToken, ValueError) as exc:
        raise RuntimeError("Provider credential cannot be decrypted") from exc


def upsert_sms_provider(
    *, tenant_id: str, provider: str, api_key: Optional[str], sender_id: str,
    enabled: bool, allow_platform_fallback: bool, purpose: str,
) -> Dict[str, Any]:
    normalized_provider = str(provider or "").strip().lower()
    if normalized_provider not in {"arkesel"}:
        raise ValueError("Unsupported SMS provider")
    if purpose not in {"notifications", "otp", "both"}:
        raise ValueError("Purpose must be notifications, otp, or both")
    existing = automation_store.get_tenant_setting(tenant_id=tenant_id, setting_key="sms_provider") or {}
    encrypted = str(existing.get("api_key_ciphertext") or "")
    if api_key:
        encrypted = _encrypt_secret(api_key.strip())
    if enabled and not encrypted:
        raise ValueError("API key is required before enabling the provider")
    value = {
        "provider": normalized_provider, "api_key_ciphertext": encrypted,
        "sender_id": str(sender_id).strip(), "enabled": bool(enabled),
        "allow_platform_fallback": bool(allow_platform_fallback), "purpose": purpose,
        "verified": False,
    }
    automation_store.upsert_tenant_setting(tenant_id=tenant_id, setting_key="sms_provider", value=value)
    return public_sms_provider(value)


def public_sms_provider(value: Dict[str, Any]) -> Dict[str, Any]:
    encrypted = str(value.get("api_key_ciphertext") or "")
    return {
        "provider": value.get("provider"), "sender_id": value.get("sender_id"),
        "enabled": bool(value.get("enabled")), "allow_platform_fallback": bool(value.get("allow_platform_fallback")),
        "purpose": value.get("purpose"), "verified": bool(value.get("verified")),
        "credential_configured": bool(encrypted), "credential_mask": "••••••••" if encrypted else None,
    }


def get_sms_provider(*, tenant_id: str) -> Dict[str, Any]:
    value = automation_store.get_tenant_setting(tenant_id=tenant_id, setting_key="sms_provider") or {}
    return public_sms_provider(value)


def verify_sms_provider(*, tenant_id: str) -> Dict[str, Any]:
    value = automation_store.get_tenant_setting(tenant_id=tenant_id, setting_key="sms_provider") or {}
    encrypted = str(value.get("api_key_ciphertext") or "")
    if not encrypted:
        raise ValueError("Provider credential is not configured")
    provider = ArkeselVerificationProvider(api_key=_decrypt_secret(encrypted), sender_id=str(value.get("sender_id") or "HRIS"))
    verified = provider.health_check()
    value["verified"] = verified
    automation_store.upsert_tenant_setting(tenant_id=tenant_id, setting_key="sms_provider", value=value)
    return public_sms_provider(value)


def build_tenant_sms_provider(*, tenant_id: str) -> Optional[ArkeselVerificationProvider]:
    value = automation_store.get_tenant_setting(tenant_id=tenant_id, setting_key="sms_provider") or {}
    if not bool(value.get("enabled")) or not bool(value.get("verified")):
        return None
    encrypted = str(value.get("api_key_ciphertext") or "")
    if not encrypted:
        return None
    return ArkeselVerificationProvider(
        api_key=_decrypt_secret(encrypted), sender_id=str(value.get("sender_id") or "HRIS")
    )
