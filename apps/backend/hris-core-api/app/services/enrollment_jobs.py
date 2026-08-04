import logging
import threading
import time
import uuid
from typing import Any, Dict, Optional

from app.core.auth import AuthenticatedUser
from app.core.settings import get_settings
from app.services import automation_store
from app.services.federated_directory_sync import sync_keycloak_from_federated_directory
from app.services.tenant_inventory_import import (
    import_missing_tenants_from_eappraisal,
    import_missing_tenants_from_srms,
)

logger = logging.getLogger(__name__)
_STOP = threading.Event()
_THREAD: Optional[threading.Thread] = None
_THREAD_LOCK = threading.Lock()


def enqueue_enrollment(*, actor: AuthenticatedUser, tenant_id: Optional[str], mode: str, max_users: int = 0) -> Dict[str, Any]:
    normalized_mode = str(mode).strip().lower()
    if normalized_mode not in {"discover", "apply"}:
        raise ValueError("mode must be discover or apply")
    return automation_store.create_enrollment_job(
        job_id=str(uuid.uuid4()), tenant_id=str(tenant_id or "").strip() or None,
        mode=normalized_mode, requested_by=actor.sub, max_users=max(0, int(max_users)),
    )


def _job_actor(job: Dict[str, Any]) -> AuthenticatedUser:
    return AuthenticatedUser(
        sub=str(job.get("requested_by") or "enrollment.worker"), username="enrollment.worker",
        email="enrollment.worker@hris.local", tenant_id=str(job.get("tenant_id") or "system"),
        roles=["hris:super_admin"], effective_role="hris:super_admin", employee_id=None,
        raw_token=None, token_claims={},
    )


def run_worker_once() -> bool:
    job = automation_store.claim_next_enrollment_job()
    if not job:
        return False
    job_id = str(job["job_id"])
    started = time.perf_counter()
    logger.warning("Enrollment job started job_id=%s mode=%s tenant_id=%s", job_id, job["mode"], job.get("tenant_id"))
    try:
        settings = get_settings()
        inventory_refresh: Dict[str, Any] = {"attempted": False, "sources": []}
        # A global enrollment must discover module-native tenants before it can
        # resolve their users. This remains worker-side so API health/readiness
        # never waits for remote module APIs.
        if not job.get("tenant_id") and settings.enrollment_refresh_tenant_inventory:
            inventory_refresh["attempted"] = True
            for source, importer in (
                ("srms", import_missing_tenants_from_srms),
                ("eappraisal", import_missing_tenants_from_eappraisal),
            ):
                try:
                    source_result = importer(
                        _job_actor(job),
                        max_records=settings.startup_tenant_inventory_max_records,
                    )
                    inventory_refresh["sources"].append(
                        {"source": source, "status": "completed", **source_result}
                    )
                except Exception as exc:
                    # One unavailable module must not prevent enrollment from
                    # healthy modules. Keep the sanitized category observable.
                    inventory_refresh["sources"].append(
                        {
                            "source": source,
                            "status": "unavailable",
                            "error_type": type(exc).__name__,
                            "detail": str(getattr(exc, "detail", exc))[:500],
                        }
                    )
                    logger.warning(
                        "Enrollment tenant inventory refresh unavailable job_id=%s source=%s error_type=%s",
                        job_id, source, type(exc).__name__,
                    )
        result = sync_keycloak_from_federated_directory(
            actor=_job_actor(job), tenant_id=job.get("tenant_id"),
            max_tenants=settings.auto_sync_max_tenants, limit_per_module=0,
            max_users=int(job.get("max_users") or 0), dry_run_override=job["mode"] != "apply",
        )
        result["tenant_inventory_refresh"] = inventory_refresh
        result["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
        discovery_errors = sum(
            len(row.get("errors") or [])
            for row in (result.get("tenant_discovery") or [])
            if isinstance(row, dict)
        )
        processed = int(result.get("processed_users") or 0)
        if processed == 0 and discovery_errors:
            final_status = "failed"
            final_error = f"No users discovered; {discovery_errors} upstream discovery error(s). Inspect result_json."
        elif discovery_errors or int(result.get("failed_count") or 0):
            final_status = "completed_with_errors"
            final_error = None
        else:
            final_status = "completed"
            final_error = None
        automation_store.finish_enrollment_job(
            job_id=job_id, status=final_status, result=result, error=final_error
        )
        logger.warning(
            "Enrollment job finished job_id=%s status=%s processed=%s discovery_errors=%s duration_ms=%s",
            job_id, final_status, processed, discovery_errors, result["duration_ms"],
        )
    except Exception as exc:
        automation_store.finish_enrollment_job(job_id=job_id, status="failed", error=f"{type(exc).__name__}: {exc}")
        logger.exception("Enrollment job failed job_id=%s", job_id)
    return True


def _worker_loop() -> None:
    while not _STOP.is_set():
        try:
            if not run_worker_once():
                _STOP.wait(2)
        except Exception:
            logger.exception("Enrollment worker polling failed")
            _STOP.wait(5)


def start_enrollment_worker_if_enabled() -> None:
    global _THREAD
    if not get_settings().enrollment_worker_enabled:
        return
    with _THREAD_LOCK:
        if _THREAD and _THREAD.is_alive():
            return
        _STOP.clear()
        _THREAD = threading.Thread(target=_worker_loop, name="hris-enrollment-worker", daemon=True)
        _THREAD.start()
        logger.warning("Enrollment worker started")


def stop_enrollment_worker() -> None:
    _STOP.set()
