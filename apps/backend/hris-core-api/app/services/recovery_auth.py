from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Optional

import httpx
from cryptography.fernet import Fernet, InvalidToken

from app.core.settings import get_settings
from app.services import automation_store
from app.services.capability_registry import resolve_capability
from app.services.providers.arkesel import ArkeselVerificationProvider
from app.services.provider_config_service import build_tenant_sms_provider
from app.services.email_delivery import send_email


RECOVERY_COOKIE_NAME = "hris_recovery_session"
GENERIC_MESSAGE = "If an eligible account matches, a recovery code will be sent to its registered contact."
_health_lock = threading.Lock()
_health_state = {"failures": 0, "healthy_since": 0.0}


def _secret_material() -> bytes:
    settings = get_settings()
    raw = str(settings.auth_recovery_pepper or settings.auth_session_encryption_key or settings.auth_state_secret or "")
    if not raw:
        raise RuntimeError("Recovery authentication secret is not configured")
    return raw.encode("utf-8")


def _fernet() -> Fernet:
    configured = str(get_settings().provider_secret_encryption_key or "").strip().encode("utf-8")
    if configured:
        try:
            return Fernet(configured)
        except ValueError:
            pass
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(_secret_material()).digest()))


def _encrypt(value: Optional[str]) -> Optional[str]:
    return _fernet().encrypt(str(value).encode()).decode() if value else None


def _decrypt(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        return _fernet().decrypt(str(value).encode()).decode()
    except (InvalidToken, ValueError):
        return None


def _digest(value: str) -> str:
    return hmac.new(_secret_material(), value.encode("utf-8"), hashlib.sha256).hexdigest()


def normalize_identifier(value: str) -> str:
    return "".join(str(value or "").strip().casefold().split())


def upsert_recovery_user(
    *, user_id: str, tenant_id: str, username: str, role_class: str, identifiers: Iterable[str],
    phone: Optional[str], email: Optional[str], phone_verified_at: Optional[str],
    email_verified_at: Optional[str], active: bool, second_factor_enrolled: bool,
) -> None:
    lookup_values = {normalize_identifier(value) for value in identifiers if normalize_identifier(value)}
    lookup_values.add(normalize_identifier(username))
    automation_store.upsert_recovery_user(row={
        "user_id": user_id,
        "tenant_id": tenant_id,
        "username": username,
        "role_class": role_class,
        "active": active,
        "lookup_hashes": sorted(_digest(value) for value in lookup_values),
        "phone_ciphertext": _encrypt(phone) if phone_verified_at else None,
        "email_ciphertext": _encrypt(email.lower()) if email and email_verified_at else None,
        "phone_verified_at": phone_verified_at,
        "email_verified_at": email_verified_at,
        "second_factor_enrolled": second_factor_enrolled,
    })


def _keycloak_healthy() -> bool:
    settings = get_settings()
    urls = [url.strip() for url in str(settings.keycloak_health_urls or "").split(",") if url.strip()]
    if not urls and settings.keycloak_jwks_url:
        urls = [str(settings.keycloak_jwks_url)]
    if not urls:
        return False
    for url in urls:
        try:
            with httpx.Client(timeout=2.0, trust_env=False) as client:
                response = client.get(url)
            if response.status_code < 500:
                return True
        except httpx.HTTPError:
            continue
    return False


def recovery_available() -> bool:
    settings = get_settings()
    mode = str(settings.auth_recovery_mode).strip().lower()
    if mode == "disabled":
        return False
    if mode == "manual":
        return bool(settings.auth_recovery_manual_active)
    healthy = _keycloak_healthy()
    now = time.time()
    with _health_lock:
        if healthy:
            _health_state["failures"] = 0
            if not _health_state["healthy_since"]:
                _health_state["healthy_since"] = now
            return False
        _health_state["healthy_since"] = 0.0
        _health_state["failures"] += 1
        return _health_state["failures"] >= int(settings.auth_recovery_failure_threshold)


def _send_email_code(destination: str, code: str) -> bool:
    try:
        send_email(
            to_email=destination,
            subject="Your HRIS recovery code",
            text_body=f"Your HRIS recovery code is {code}. It expires shortly. Do not share this code.",
        )
        return True
    except Exception:
        return False


def start_challenge(identifier: str) -> Dict[str, Any]:
    settings = get_settings()
    challenge_id = secrets.token_urlsafe(36)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=int(settings.auth_recovery_otp_ttl_seconds))
    user = automation_store.find_recovery_user(lookup_hash=_digest(normalize_identifier(identifier)))
    provider = "none"
    provider_reference: Optional[str] = None
    destination_ciphertext: Optional[str] = None
    if user:
        phone = _decrypt(user.get("phone_ciphertext"))
        email = _decrypt(user.get("email_ciphertext"))
        if phone and resolve_capability("sms", tenant_id=str(user["tenant_id"])).enabled:
            sms_provider = build_tenant_sms_provider(tenant_id=str(user["tenant_id"])) or ArkeselVerificationProvider()
            result = sms_provider.start_verification(
                destination=phone,
                length=int(settings.auth_recovery_otp_length),
                ttl_seconds=int(settings.auth_recovery_otp_ttl_seconds),
            )
            if result.accepted:
                provider, provider_reference = result.provider, result.reference
                destination_ciphertext = _encrypt(phone)
        if provider == "none" and email and resolve_capability("email", tenant_id=str(user["tenant_id"])).enabled:
            code = "".join(secrets.choice("0123456789") for _ in range(int(settings.auth_recovery_otp_length)))
            if _send_email_code(email, code):
                provider = "internal_email"
                provider_reference = "hmac:" + _digest(challenge_id + ":" + code)
                destination_ciphertext = _encrypt(email)
    automation_store.create_recovery_challenge(row={
        "challenge_hash": _digest(challenge_id),
        "user_id": user.get("user_id") if user else None,
        "tenant_id": user.get("tenant_id") if user else None,
        "provider": provider,
        "destination_ciphertext": destination_ciphertext,
        "provider_reference": provider_reference,
        "expires_at": expires_at.isoformat(),
    })
    return {"challenge_token": challenge_id, "message": GENERIC_MESSAGE, "expires_in": int(settings.auth_recovery_otp_ttl_seconds)}


def verify_challenge(challenge_id: str, code: str) -> Optional[str]:
    settings = get_settings()
    row = automation_store.get_recovery_challenge(challenge_hash=_digest(challenge_id))
    if not row or not row.get("user_id"):
        return None
    if int(row.get("attempts") or 0) >= int(settings.auth_recovery_max_attempts):
        return None
    accepted = False
    reference = str(row.get("provider_reference") or "")
    if str(row.get("provider")) == "internal_email" and reference.startswith("hmac:"):
        accepted = hmac.compare_digest(reference[5:], _digest(challenge_id + ":" + str(code).strip()))
    elif str(row.get("provider")) == "arkesel":
        destination = _decrypt(row.get("destination_ciphertext"))
        if destination:
            tenant_id = str(row.get("tenant_id") or "")
            sms_provider = build_tenant_sms_provider(tenant_id=tenant_id) or ArkeselVerificationProvider()
            accepted = sms_provider.check_verification(
                destination=destination, code=str(code).strip(), reference=reference or None
            ).accepted
    automation_store.increment_recovery_attempt(challenge_hash=_digest(challenge_id), consume=accepted)
    if not accepted:
        return None
    directory = automation_store.find_recovery_user(lookup_hash=_digest(normalize_identifier(str(row.get("user_id")))))
    # The user id may not be a login identifier, so retrieve from the challenge
    # through a direct lookup implemented below when necessary.
    if not directory:
        directory = get_recovery_user_by_id(str(row["user_id"]))
    if not directory:
        return None
    role = str(directory.get("role_class") or "hris:employee")
    # A flag saying that a factor is enrolled is not proof that the factor was
    # presented for this login. Until the recovery verifier supports an actual
    # WebAuthn/TOTP/recovery-key assertion, privileged recovery must fail closed.
    if role != "hris:employee" and settings.auth_recovery_privileged_second_factor_required:
        return None
    session_id = secrets.token_urlsafe(48)
    automation_store.create_recovery_session(row={
        "session_hash": _digest(session_id), "user_id": directory["user_id"], "tenant_id": directory["tenant_id"],
        "username": directory["username"], "role_class": role,
        "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=int(settings.auth_recovery_session_ttl_seconds))).isoformat(),
    })
    return session_id


def get_recovery_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    # Kept in this service so contact decryption never leaks into callers.
    return automation_store.get_recovery_user_by_id(user_id=user_id)


def load_recovery_session(session_id: str) -> Optional[Dict[str, Any]]:
    return automation_store.get_recovery_session(session_hash=_digest(session_id)) if session_id else None


def revoke_recovery_session(session_id: str) -> None:
    if session_id:
        automation_store.revoke_recovery_session(session_hash=_digest(session_id))
