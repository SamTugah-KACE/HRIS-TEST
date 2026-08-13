import logging
import random
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

import httpx

from app.core.settings import get_settings
from app.services import automation_store
from app.services.keycloak_provisioning import send_required_actions_email

logger = logging.getLogger(__name__)
_STOP = threading.Event()
_THREAD: Optional[threading.Thread] = None
_THREAD_LOCK = threading.Lock()


def _iso_after(seconds: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=max(0, seconds))).isoformat()


def _classify_failure(exc: Exception) -> Tuple[bool, str, Optional[int]]:
    """Return transient, sanitized category, and downstream HTTP status."""
    if isinstance(exc, httpx.HTTPStatusError):
        status = int(exc.response.status_code)
        if status == 429 or status >= 500:
            return True, "keycloak_email_provider_transient", status
        return False, "keycloak_action_email_rejected", status
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
        return True, "keycloak_unavailable", None
    return False, type(exc).__name__, None


def _retry_delay(attempt: int) -> int:
    settings = get_settings()
    base = int(settings.invitation_dispatch_retry_base_seconds)
    maximum = int(settings.invitation_dispatch_retry_max_seconds)
    exponential = min(maximum, base * (2 ** max(0, attempt - 1)))
    return min(maximum, exponential + random.randint(0, max(1, exponential // 5)))


def run_dispatch_once() -> bool:
    invitation = automation_store.claim_next_keycloak_invitation()
    if not invitation:
        return False
    settings = get_settings()
    tenant_id = str(invitation["tenant_id"])
    email = str(invitation["email"])
    user_id = str(invitation.get("keycloak_user_id") or "").strip()
    attempt = int(invitation.get("attempt_count") or 1)
    if not user_id:
        automation_store.finish_keycloak_invitation(
            tenant_id=tenant_id, email=email, status="failed",
            payload={"delivery": "keycloak_action_email", "reason": "missing_keycloak_user_id"},
            error_category="missing_keycloak_user_id",
        )
        return True
    try:
        send_required_actions_email(user_id=user_id, actions=["UPDATE_PASSWORD"])
        automation_store.finish_keycloak_invitation(
            tenant_id=tenant_id, email=email, status="sent",
            payload={"delivery": "keycloak_action_email", "status": "accepted_by_keycloak"},
        )
        logger.info("Keycloak invitation accepted tenant_id=%s attempt=%s", tenant_id, attempt)
    except Exception as exc:
        transient, category, provider_status = _classify_failure(exc)
        exhausted = attempt >= int(settings.invitation_dispatch_max_attempts)
        if transient and not exhausted:
            delay = _retry_delay(attempt)
            retry_at = _iso_after(delay)
            automation_store.finish_keycloak_invitation(
                tenant_id=tenant_id, email=email, status="retry_wait",
                payload={"delivery": "keycloak_action_email", "outcome": "retry_scheduled"},
                next_attempt_at=retry_at, error_category=category, provider_status=provider_status,
            )
            cooldown_at = _iso_after(int(settings.invitation_dispatch_provider_cooldown_seconds))
            deferred = automation_store.defer_pending_keycloak_invitations(
                next_attempt_at=cooldown_at, error_category="provider_circuit_open"
            )
            logger.warning(
                "Keycloak invitation transient failure tenant_id=%s category=%s status=%s attempt=%s deferred=%s",
                tenant_id, category, provider_status, attempt, deferred,
            )
        else:
            automation_store.finish_keycloak_invitation(
                tenant_id=tenant_id, email=email, status="failed",
                payload={"delivery": "keycloak_action_email", "outcome": "permanent_failure"},
                error_category=category, provider_status=provider_status,
            )
            logger.warning(
                "Keycloak invitation permanently failed tenant_id=%s category=%s status=%s attempt=%s",
                tenant_id, category, provider_status, attempt,
            )
    return True


def _worker_loop() -> None:
    while not _STOP.is_set():
        try:
            if run_dispatch_once():
                _STOP.wait(max(1, int(get_settings().invitation_dispatch_interval_seconds)))
            else:
                _STOP.wait(2)
        except Exception:
            logger.exception("Invitation dispatcher polling failed")
            _STOP.wait(5)


def start_invitation_dispatcher_if_enabled() -> None:
    global _THREAD
    settings = get_settings()
    if not settings.invitation_dispatch_worker_enabled:
        return
    with _THREAD_LOCK:
        if _THREAD and _THREAD.is_alive():
            return
        _STOP.clear()
        _THREAD = threading.Thread(target=_worker_loop, name="hris-invitation-dispatcher", daemon=True)
        _THREAD.start()
        logger.warning(
            "Invitation dispatcher started interval_seconds=%s max_attempts=%s",
            settings.invitation_dispatch_interval_seconds,
            settings.invitation_dispatch_max_attempts,
        )


def stop_invitation_dispatcher() -> None:
    _STOP.set()
