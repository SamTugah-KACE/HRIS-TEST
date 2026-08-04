"""
HRIS Account Management API
============================
Proxy endpoints that let HRIS users edit their own Keycloak identity
(display name, email, password) without ever exposing Keycloak URLs to
the browser.  All mutations go through HRIS Core → Keycloak Admin API.

Endpoints:
  GET  /account/profile          — fetch the user's Keycloak profile
  PATCH /account/profile         — update first name, last name, or email
  POST  /account/password        — change password (validates current first)

Security:
  - All endpoints require a valid HRIS session (get_current_user).
  - The user's Keycloak sub (UUID) is taken from the validated JWT; the
    caller cannot impersonate another user.
  - Password change first verifies the current password via a token-grant
    call before issuing the Admin API reset — prevents password takeover
    if an HRIS session is left open on a shared machine.
  - Admin credentials never leave the HRIS backend.
"""

import logging
import hashlib
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, field_validator

from app.core.auth import AuthenticatedUser, get_current_user
from app.core.settings import get_settings
from app.services.rate_limiter import enforce_rate_limit
from app.services import automation_store

router = APIRouter(prefix="/account", tags=["account"])
logger = logging.getLogger("hris_core.account")

# ---------------------------------------------------------------------------
# Keycloak Admin API helpers
# ---------------------------------------------------------------------------

def _kc_base(settings) -> str:
    """Derive the Keycloak server root from the issuer URL."""
    internal_base = str(getattr(settings, "keycloak_internal_base_url", None) or "").strip()
    if internal_base:
        return internal_base.rstrip("/")
    issuer = (settings.keycloak_issuer or "").rstrip("/")
    # issuer is like https://auth.example.com/realms/hris
    # We need        https://auth.example.com
    if "/realms/" in issuer:
        return issuer.split("/realms/")[0]
    return issuer


def _realm(settings) -> str:
    configured = str(settings.keycloak_realm or "").strip()
    if configured:
        return configured
    issuer = str(settings.keycloak_issuer or "").rstrip("/")
    if "/realms/" in issuer:
        return issuer.rsplit("/realms/", 1)[1].split("/", 1)[0]
    return "hris-platform"


def _admin_api(settings) -> str:
    return f"{_kc_base(settings)}/admin/realms/{_realm(settings)}"


def _token_url(settings) -> str:
    return f"{_kc_base(settings)}/realms/{_realm(settings)}/protocol/openid-connect/token"


async def _get_admin_token(settings) -> str:
    """
    Obtain a short-lived Keycloak admin token via client_credentials.
    Uses the admin service account configured in settings.
    Raises HTTPException(503) if Keycloak is unreachable or credentials wrong.
    """
    master_token_url = f"{_kc_base(settings)}/realms/{settings.keycloak_admin_realm}/protocol/openid-connect/token"

    payload: dict = {}
    if settings.keycloak_admin_client_id and settings.keycloak_admin_client_secret:
        payload = {
            "grant_type": "client_credentials",
            "client_id": settings.keycloak_admin_client_id,
            "client_secret": settings.keycloak_admin_client_secret,
        }
    elif settings.keycloak_admin_username and settings.keycloak_admin_password:
        payload = {
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": settings.keycloak_admin_username,
            "password": settings.keycloak_admin_password,
        }
    else:
        raise HTTPException(503, "Keycloak admin credentials not configured on HRIS server.")

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.post(master_token_url, data=payload)
        except httpx.RequestError as exc:
            logger.error("Keycloak admin token request failed: %s", exc)
            raise HTTPException(503, "Could not connect to identity provider.") from exc

    if r.status_code != 200:
        logger.error("Keycloak admin token error %s: %s", r.status_code, r.text[:300])
        raise HTTPException(503, "Identity provider returned an error. Check admin credentials.")

    return r.json()["access_token"]


async def _validate_current_password(settings, username: str, password: str) -> bool:
    """
    Verify the user's current password by attempting a resource-owner
    password grant against the HRIS realm client.
    Returns True if valid, False if wrong password.
    """
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.post(_token_url(settings), data={
                "grant_type": "password",
                "client_id": settings.keycloak_portal_client_id,
                "client_secret": settings.keycloak_portal_client_secret or "",
                "username": username,
                "password": password,
            })
        except httpx.RequestError:
            return False
    return r.status_code == 200


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ProfileUpdateRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def strip_whitespace(cls, v):
        return v.strip() if v else v


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v):
        if len(v) < 8:
            raise ValueError("New password must be at least 8 characters.")
        return v


class PasswordResetRequest(BaseModel):
    email: EmailStr


_RESET_ACCEPTED = {
    "status": "accepted",
    "message": "If an active account matches that email address, a password reset link will be sent shortly.",
}


@router.post("/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
async def request_password_reset(body: PasswordResetRequest, request: Request):
    """Request a Keycloak-owned, expiring password-reset link without revealing account existence."""
    settings = get_settings()
    email = str(body.email).strip().lower()
    recipient_hash = hashlib.sha256(email.encode("utf-8")).hexdigest()[:16]
    correlation_id = getattr(request.state, "correlation_id", "")
    enforce_rate_limit(
        request,
        scope="password_reset",
        limit=settings.password_reset_rate_limit_max,
        user_key=f"email:{email}",
    )
    enforce_rate_limit(
        request,
        scope="password_reset_ip",
        limit=max(settings.password_reset_rate_limit_max * 3, 10),
    )
    if not settings.keycloak_issuer:
        return _RESET_ACCEPTED
    try:
        admin_token = await _get_admin_token(settings)
        headers = {"Authorization": f"Bearer {admin_token}"}
        async with httpx.AsyncClient(timeout=10) as client:
            lookup = await client.get(
                f"{_admin_api(settings)}/users",
                params={"email": email, "exact": "true", "enabled": "true", "max": 2},
                headers=headers,
            )
            if lookup.status_code != 200:
                raise RuntimeError(f"keycloak_user_lookup_http_{lookup.status_code}")
            if lookup.status_code == 200:
                users = lookup.json() if isinstance(lookup.json(), list) else []
                matches = [u for u in users if str(u.get("email") or "").strip().lower() == email]
                if len(matches) == 1 and matches[0].get("id"):
                    dispatched = await client.put(
                        f"{_admin_api(settings)}/users/{matches[0]['id']}/execute-actions-email",
                        params={
                            "client_id": settings.keycloak_portal_client_id,
                            "redirect_uri": settings.portal_base_url.rstrip("/") + "/",
                            "lifespan": settings.password_reset_action_lifespan_seconds,
                        },
                        json=["UPDATE_PASSWORD"],
                        headers=headers,
                    )
                    if dispatched.status_code not in (200, 204):
                        raise RuntimeError(f"keycloak_execute_actions_email_http_{dispatched.status_code}")
                    automation_store.record_email_delivery(
                        purpose="password_reset", recipient_hash=recipient_hash, status="accepted_by_keycloak",
                        provider="keycloak", correlation_id=correlation_id,
                    )
                else:
                    automation_store.record_email_delivery(
                        purpose="password_reset", recipient_hash=recipient_hash, status="no_unique_active_account",
                        provider="keycloak", correlation_id=correlation_id,
                    )
    except Exception as exc:
        # A public reset endpoint must not disclose lookup, SMTP, or identity-provider state.
        logger.exception("Password reset dispatch failed recipient_hash=%s correlation_id=%s", recipient_hash, correlation_id)
        try:
            automation_store.record_email_delivery(
                purpose="password_reset", recipient_hash=recipient_hash, status="failed",
                provider="keycloak", detail=f"{type(exc).__name__}: {exc}", correlation_id=correlation_id,
            )
        except Exception:
            logger.exception("Password reset delivery audit failed correlation_id=%s", correlation_id)
    return _RESET_ACCEPTED


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/profile")
async def get_account_profile(
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Return the authenticated user's Keycloak profile fields."""
    settings = get_settings()
    if not settings.keycloak_issuer:
        # Dev mode — return what we have from the JWT claims.
        return {
            "sub": user.sub,
            "username": user.username,
            "email": user.email,
            "first_name": user.token_claims.get("given_name") or "",
            "last_name": user.token_claims.get("family_name") or "",
            "email_verified": user.token_claims.get("email_verified", False),
        }

    admin_token = await _get_admin_token(settings)
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.get(
                f"{_admin_api(settings)}/users/{user.sub}",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        except httpx.RequestError as exc:
            raise HTTPException(503, "Could not reach identity provider.") from exc

    if r.status_code == 404:
        raise HTTPException(404, "User not found in identity provider.")
    if r.status_code != 200:
        raise HTTPException(502, "Identity provider error.")

    kc = r.json()
    return {
        "sub": kc.get("id") or user.sub,
        "username": kc.get("username") or user.username,
        "email": kc.get("email") or user.email,
        "first_name": kc.get("firstName") or "",
        "last_name": kc.get("lastName") or "",
        "email_verified": kc.get("emailVerified", False),
    }


@router.patch("/profile")
async def update_account_profile(
    body: ProfileUpdateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Update the user's Keycloak profile (first name, last name, and/or email).
    An email change marks the address as unverified — Keycloak will send a
    verification email if the realm has that workflow enabled.
    """
    settings = get_settings()
    if not settings.keycloak_issuer:
        return {"status": "ok", "note": "dev mode — no Keycloak to update"}

    admin_token = await _get_admin_token(settings)

    # Fetch current profile first so we only patch what changed.
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{_admin_api(settings)}/users/{user.sub}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    if r.status_code != 200:
        raise HTTPException(502, "Could not fetch current profile before update.")

    current = r.json()
    patch: dict = {}
    if body.first_name is not None:
        patch["firstName"] = body.first_name
    if body.last_name is not None:
        patch["lastName"] = body.last_name
    if body.email is not None and body.email != current.get("email"):
        patch["email"] = body.email
        patch["emailVerified"] = False  # re-verify after email change

    if not patch:
        return {"status": "ok", "note": "nothing changed"}

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.put(
                f"{_admin_api(settings)}/users/{user.sub}",
                json={**current, **patch},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        except httpx.RequestError as exc:
            raise HTTPException(503, "Could not reach identity provider.") from exc

    if r.status_code not in (200, 204):
        logger.error("Keycloak profile update failed %s: %s", r.status_code, r.text[:300])
        raise HTTPException(502, "Identity provider rejected the profile update.")

    email_changed = "email" in patch

    # Trigger Keycloak to send a verification email to the new address automatically.
    # Uses the execute-actions-email Admin API — no realm workflow config required.
    if email_changed:
        await _send_verification_email(settings, user.sub, admin_token)

    return {
        "status": "ok",
        "email_changed": email_changed,
        "verification_required": email_changed,
        "message": (
            "Profile updated. A verification link has been sent to your new email address."
            if email_changed
            else "Profile updated successfully."
        ),
    }


async def _send_verification_email(settings, user_id: str, admin_token: str) -> None:
    """Tell Keycloak to send a VERIFY_EMAIL action email to the user's address."""
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.put(
                f"{_admin_api(settings)}/users/{user_id}/execute-actions-email",
                json=["VERIFY_EMAIL"],
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            if r.status_code not in (200, 204):
                logger.warning(
                    "Keycloak execute-actions-email returned %s — verification email may not be sent",
                    r.status_code,
                )
        except httpx.RequestError as exc:
            # Non-fatal: profile was updated; verification email is best-effort.
            logger.warning("Could not send Keycloak verification email: %s", exc)


@router.post("/resend-verification")
async def resend_verification_email(
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Resend a Keycloak email-verification link to the user's current address.
    No-op if the email is already verified (returns 200 with a note).
    """
    settings = get_settings()
    if not settings.keycloak_issuer:
        return {"status": "ok", "note": "dev mode — no Keycloak configured"}

    admin_token = await _get_admin_token(settings)

    # Check current verification status first.
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{_admin_api(settings)}/users/{user.sub}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    if r.status_code != 200:
        raise HTTPException(502, "Could not fetch profile from identity provider.")
    if r.json().get("emailVerified"):
        return {"status": "ok", "message": "Email is already verified."}

    await _send_verification_email(settings, user.sub, admin_token)
    return {"status": "ok", "message": "Verification email sent. Check your inbox."}


@router.post("/password")
async def change_account_password(
    body: PasswordChangeRequest,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Change the user's Keycloak password.
    Validates the current password via a token grant before applying the change.
    """
    settings = get_settings()
    if not settings.keycloak_issuer:
        return {"status": "ok", "note": "dev mode — no Keycloak to update"}

    # Step 1: verify current password is correct.
    valid = await _validate_current_password(settings, user.username, body.current_password)
    if not valid:
        raise HTTPException(400, "Current password is incorrect.")

    # Step 2: set the new password via Admin API.
    admin_token = await _get_admin_token(settings)
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.put(
                f"{_admin_api(settings)}/users/{user.sub}/reset-password",
                json={"type": "password", "value": body.new_password, "temporary": False},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        except httpx.RequestError as exc:
            raise HTTPException(503, "Could not reach identity provider.") from exc

    if r.status_code not in (200, 204):
        logger.error("Keycloak password reset failed %s: %s", r.status_code, r.text[:300])
        raise HTTPException(502, "Identity provider rejected the password change.")

    return {"status": "ok", "message": "Password changed successfully."}
