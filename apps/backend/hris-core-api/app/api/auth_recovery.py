from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.core.auth import AuthenticatedUser, require_roles
from app.core.settings import get_settings
from app.services.rate_limiter import enforce_rate_limit
from app.services.recovery_auth import (
    RECOVERY_COOKIE_NAME,
    recovery_available,
    revoke_recovery_session,
    start_challenge,
    upsert_recovery_user,
    verify_challenge,
)

router = APIRouter(prefix="/api/hris/v1/auth/recovery", tags=["auth-recovery"])


class RecoveryStartIn(BaseModel):
    identifier: str = Field(min_length=2, max_length=254)


class RecoveryVerifyIn(BaseModel):
    challenge_token: str = Field(min_length=20, max_length=200)
    code: str = Field(min_length=6, max_length=15)


class RecoveryDirectoryIn(BaseModel):
    user_id: str
    tenant_id: str
    username: str
    role_class: str = "hris:employee"
    identifiers: List[str] = []
    phone: Optional[str] = None
    email: Optional[str] = None
    phone_verified_at: Optional[datetime] = None
    email_verified_at: Optional[datetime] = None
    active: bool = True
    second_factor_enrolled: bool = False


@router.get("/status")
def recovery_status():
    available = recovery_available()
    return {"available": available, "mode": "outage_recovery" if available else "normal"}


@router.post("/challenges", status_code=status.HTTP_202_ACCEPTED)
def recovery_start(payload: RecoveryStartIn, request: Request):
    enforce_rate_limit(request, scope="auth_recovery_start", limit=5, user_key=payload.identifier.casefold()[:64])
    if not recovery_available():
        raise HTTPException(status_code=503, detail="Recovery authentication is not available")
    return start_challenge(payload.identifier)


@router.post("/challenges/verify")
def recovery_verify(payload: RecoveryVerifyIn, request: Request, response: Response):
    enforce_rate_limit(request, scope="auth_recovery_verify", limit=10, user_key=payload.challenge_token[:32])
    if not recovery_available():
        raise HTTPException(status_code=503, detail="Recovery authentication is not available")
    session_id = verify_challenge(payload.challenge_token, payload.code)
    if not session_id:
        raise HTTPException(status_code=401, detail="Recovery code is invalid or expired")
    settings = get_settings()
    response.set_cookie(
        key=RECOVERY_COOKIE_NAME, value=session_id,
        max_age=int(settings.auth_recovery_session_ttl_seconds), httponly=True,
        secure=bool(settings.auth_cookie_secure or request.url.scheme == "https"),
        samesite=settings.auth_cookie_samesite, path="/",
    )
    return {"authenticated": True, "restricted": True, "normal_reauthentication_required": True}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def recovery_logout(request: Request, response: Response):
    revoke_recovery_session(str(request.cookies.get(RECOVERY_COOKIE_NAME) or ""))
    response.delete_cookie(RECOVERY_COOKIE_NAME, path="/")
    return response


@router.put("/directory/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def recovery_directory_upsert(
    user_id: str, payload: RecoveryDirectoryIn,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin")),
):
    if user_id != payload.user_id:
        raise HTTPException(status_code=422, detail="User id does not match request path")
    upsert_recovery_user(
        user_id=payload.user_id, tenant_id=payload.tenant_id, username=payload.username,
        role_class=payload.role_class,
        identifiers=[*payload.identifiers, payload.user_id, payload.username, payload.email or "", payload.phone or ""],
        phone=payload.phone, email=payload.email,
        phone_verified_at=payload.phone_verified_at.astimezone(timezone.utc).isoformat() if payload.phone_verified_at else None,
        email_verified_at=payload.email_verified_at.astimezone(timezone.utc).isoformat() if payload.email_verified_at else None,
        active=payload.active, second_factor_enrolled=payload.second_factor_enrolled,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
