from datetime import datetime, timezone
import threading
import time
import logging
import json
from typing import Any, Dict, Optional

from app.core.auth import AuthenticatedUser
from app.core.settings import get_settings
from app.services import automation_store
from app.services.auto_provision_service import provision_missing_users_globally
from app.services.onboarding_automation import (
    snapshot_current_tenant_mappings,
    sync_tenant_users_identity_snapshot,
    sync_tenant_users_and_send_welcome,
)
from app.services.tenant_inventory_import import import_missing_tenants_from_eappraisal, import_missing_tenants_from_srms
from app.services.tenant_drift_sync import build_drift_snapshot
from app.services.tenant_registry_client import list_tenant_mappings
from app.services.user_drift_sync import build_global_user_drift

logger = logging.getLogger(__name__)

class _AutoSyncState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._last_result: Dict[str, Any] = {}
        self._last_error: str = ""
        self._last_run_at: str = ""

    def _system_actor(self) -> AuthenticatedUser:
        settings = get_settings()
        return AuthenticatedUser(
            sub="sync.automation",
            username="sync.automation",
            email="sync.automation@hris.local",
            tenant_id=settings.dev_default_tenant_id or "system",
            roles=["hris:super_admin"],
            effective_role="hris:super_admin",
            employee_id=None,
            raw_token=None,
            token_claims={},
        )

    def run_cycle(self) -> Dict[str, Any]:
        settings = get_settings()
        scheduler_lock = automation_store.try_acquire_scheduler_lock()
        if scheduler_lock is None:
            return {"run_mode": "automatic", "status": "skipped", "reason": "another_replica_is_reconciling"}
        actor = self._system_actor()
        logger.warning(
            "Auto-sync cycle starting: %s",
            json.dumps(
                {
                    "auto_sync_max_tenants": settings.auto_sync_max_tenants,
                    "auto_sync_max_users_per_tenant": settings.auto_sync_max_users_per_tenant,
                    "onboarding_auto_sync_new_tenants": settings.onboarding_auto_sync_new_tenants,
                    "onboarding_auto_keycloak_provision": settings.onboarding_auto_keycloak_provision,
                    "onboarding_welcome_email_enabled": settings.onboarding_welcome_email_enabled,
                },
                ensure_ascii=True,
            ),
        )
        import_result: Dict[str, Any] = {}
        try:
            return self._run_locked_cycle(settings=settings, actor=actor, import_result=import_result)
        finally:
            automation_store.release_scheduler_lock(scheduler_lock)

    def _run_locked_cycle(self, *, settings, actor: AuthenticatedUser, import_result: Dict[str, Any]) -> Dict[str, Any]:
        if settings.onboarding_auto_sync_new_tenants:
            for module_name, importer in (
                ("srms", import_missing_tenants_from_srms),
                ("eappraisal", import_missing_tenants_from_eappraisal),
            ):
                try:
                    import_result[module_name] = importer(
                        actor, max_records=settings.startup_tenant_inventory_max_records
                    )
                except Exception as exc:
                    logger.warning("Tenant inventory scan unavailable module=%s error_type=%s", module_name, type(exc).__name__)
                    import_result[module_name] = {"status": "unavailable", "error_type": type(exc).__name__}
        tenant_drift = build_drift_snapshot(actor, max_registry_tenants=settings.auto_sync_max_tenants)
        user_drift = build_global_user_drift(
            actor=actor,
            max_tenants=settings.auto_sync_max_tenants,
            max_users_per_tenant=settings.auto_sync_max_users_per_tenant,
        )
        mapping_snapshot = snapshot_current_tenant_mappings(limit=settings.auto_sync_max_tenants)
        user_identity_sync = []
        for tenant in list_tenant_mappings(limit=settings.auto_sync_max_tenants):
            if not tenant.is_tenant_active():
                continue
            try:
                user_identity_sync.append(
                    sync_tenant_users_identity_snapshot(
                        tenant_id=tenant.tenant_id,
                        actor=actor,
                        limit=settings.auto_sync_max_users_per_tenant,
                    )
                )
            except Exception as exc:
                user_identity_sync.append(
                    {
                        "tenant_id": tenant.tenant_id,
                        "processed": 0,
                        "persisted": 0,
                        "skipped": 0,
                        "errors": [{"error": str(exc)}],
                    }
                )
        persisted_total = sum(int(row.get("persisted", 0)) for row in user_identity_sync)
        processed_total = sum(int(row.get("processed", 0)) for row in user_identity_sync)
        keycloak_linked_total = sum(int(row.get("keycloak_linked", 0)) for row in user_identity_sync)
        try:
            automation_store.record_drift_snapshot(scope="tenant", tenant_id=None, payload=tenant_drift)
            automation_store.record_drift_snapshot(scope="user", tenant_id=None, payload=user_drift)
            automation_store.record_checkpoint(
                checkpoint_type="auto_sync_cycle",
                tenant_id=None,
                payload={
                    "tenant_summary": tenant_drift.get("summary", {}),
                    "user_summary": user_drift.get("summary", {}),
                    "import_result": import_result or {},
                    "mapping_snapshot": mapping_snapshot,
                    "identity_sync_summary": {
                        "tenants": len(user_identity_sync),
                        "processed_users": processed_total,
                        "persisted_users": persisted_total,
                        "keycloak_linked_users": keycloak_linked_total,
                    },
                },
            )
        except Exception as exc:
            logger.warning("Auto-sync persistence layer unavailable: %s", exc)
        result = {
            "tenant_drift": tenant_drift,
            "user_drift": user_drift,
            "run_mode": "automatic",
            "tenant_import": import_result,
            "mapping_snapshot": mapping_snapshot,
            "tenant_user_identity_sync": {
                "tenants": len(user_identity_sync),
                "processed_users": processed_total,
                "persisted_users": persisted_total,
                "keycloak_linked_users": keycloak_linked_total,
                "details": user_identity_sync[:100],
            },
        }
        if settings.onboarding_welcome_email_enabled:
            welcome_summary = []
            for tenant in list_tenant_mappings(limit=settings.auto_sync_max_tenants):
                if not tenant.is_tenant_active():
                    continue
                welcome_summary.append(
                    sync_tenant_users_and_send_welcome(
                        tenant_id=tenant.tenant_id,
                        actor=actor,
                        limit=settings.onboarding_welcome_max_users_per_tenant,
                    )
                )
            result["welcome_sync"] = welcome_summary
        if settings.enable_auto_provision:
            try:
                result["auto_provision"] = provision_missing_users_globally(actor)
            except Exception as exc:
                logger.warning("Auto-provision failed during sync cycle: %s", exc)
                result["auto_provision"] = {"error": str(exc)}
        logger.warning(
            "Auto-sync cycle completed: %s",
            json.dumps(
                {
                    "tenant_import": import_result or {},
                    "identity_sync": {
                        "tenants": len(user_identity_sync),
                        "processed_users": processed_total,
                        "persisted_users": persisted_total,
                        "keycloak_linked_users": keycloak_linked_total,
                    },
                    "identity_sync_details_sample": user_identity_sync[:20],
                    "has_welcome_sync": bool("welcome_sync" in result),
                    "has_auto_provision": bool("auto_provision" in result),
                },
                ensure_ascii=True,
            ),
        )
        with self._lock:
            self._last_result = result
            self._last_error = ""
            self._last_run_at = datetime.now(timezone.utc).isoformat()
        return result

    def _loop(self) -> None:
        settings = get_settings()
        while self._running:
            try:
                self.run_cycle()
            except Exception as exc:
                with self._lock:
                    self._last_error = str(exc)
                    self._last_run_at = datetime.now(timezone.utc).isoformat()
            time.sleep(settings.auto_sync_interval_seconds)

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._loop, name="hris-auto-sync", daemon=True)
            self._thread.start()

    def status(self) -> Dict[str, Any]:
        settings = get_settings()
        with self._lock:
            return {
                "enabled": settings.enable_auto_sync_loop,
                "running": self._running,
                "last_run_at": self._last_run_at,
                "last_error": self._last_error,
                "last_result": self._last_result,
                "interval_seconds": settings.auto_sync_interval_seconds,
            }


_STATE = _AutoSyncState()


def start_auto_sync_loop_if_enabled() -> None:
    settings = get_settings()
    if settings.enable_auto_sync_loop:
        _STATE.start()


def run_auto_sync_now() -> Dict[str, Any]:
    return _STATE.run_cycle()


def get_auto_sync_status() -> Dict[str, Any]:
    return _STATE.status()
