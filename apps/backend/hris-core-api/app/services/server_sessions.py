from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet, InvalidToken
from jose import jwt

from app.core.settings import get_settings
from app.services import automation_store


SESSION_COOKIE_NAME = "hris_session"


def _fernet() -> Fernet:
    settings = get_settings()
    configured = str(settings.auth_session_encryption_key or "").strip()
    if configured:
        raw = configured.encode("utf-8")
        try:
            return Fernet(raw)
        except ValueError:
            pass
    fallback = str(settings.auth_state_secret or settings.keycloak_portal_client_secret or "").encode("utf-8")
    if not fallback:
        raise RuntimeError("Server-side session encryption is not configured")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(fallback).digest()))


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _unverified_claims(access_token: str) -> Dict[str, Any]:
    try:
        return dict(jwt.get_unverified_claims(access_token))
    except Exception:
        return {}


def create_session(
    *, access_token: str, refresh_token: Optional[str], id_token: Optional[str],
    access_expires_in: Optional[int], refresh_expires_in: Optional[int], user_agent: str,
) -> str:
    settings = get_settings()
    session_id = secrets.token_urlsafe(48)
    claims = _unverified_claims(access_token)
    lifetime = max(60, int(refresh_expires_in or settings.auth_cookie_refresh_max_age_seconds))
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=lifetime)
    payload = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "id_token": id_token,
        "access_expires_in": access_expires_in,
        "refresh_expires_in": refresh_expires_in,
    }
    ciphertext = _fernet().encrypt(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("ascii")
    automation_store.create_auth_session(
        session_hash=_hash(session_id),
        token_ciphertext=ciphertext,
        subject=str(claims.get("sub") or "") or None,
        tenant_id=str(claims.get("tenant_id") or claims.get("tenantId") or "") or None,
        refresh_fingerprint=_hash(refresh_token)[:24] if refresh_token else None,
        user_agent_hash=_hash(user_agent)[:24] if user_agent else None,
        expires_at=expires_at.isoformat(),
    )
    return session_id


def load_session(session_id: str) -> Optional[Dict[str, Any]]:
    if not session_id:
        return None
    row = automation_store.get_auth_session(session_hash=_hash(session_id))
    if not row:
        return None
    try:
        payload = json.loads(_fernet().decrypt(str(row["token_ciphertext"]).encode("ascii")))
    except (InvalidToken, ValueError, TypeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def revoke_session(session_id: str) -> None:
    if session_id:
        automation_store.revoke_auth_session(session_hash=_hash(session_id))
