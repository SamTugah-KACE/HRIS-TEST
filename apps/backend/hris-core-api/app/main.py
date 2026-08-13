import uuid
import time
import logging
import json
import socket
import httpx

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.requests import Request
from starlette.responses import Response

from app.api.account import router as account_router
from app.api.auth_sso import router as auth_sso_router
from app.api.dashboard import router as dashboard_router
from app.api.employees import router as employees_router
from app.api.federated_directory_debug import router as federated_directory_debug_router
from app.api.integrations_debug import router as integrations_debug_router
from app.api.integration_sync import router as integration_sync_router
from app.api.jit_setup import router as jit_setup_router
from app.api.me import router as me_router
from app.api.modules import router as modules_router, profile_router
from app.api.tenants_onboarding import router as tenants_router
from app.api.tenant_federation import router as tenant_federation_router
from app.core.auth import AuthenticatedUser
from app.core.settings import get_settings
from app.core.logging_config import configure_logging
from app.services.admin_bootstrap import bootstrap_admin_accounts_if_enabled
from app.services.auto_sync_service import start_auto_sync_loop_if_enabled
from app.services.db_health import ensure_runtime_databases_ready
from app.services.onboarding_automation import run_post_deploy_automation
from app.services.keycloak_realm_email import configure_keycloak_realm_email_if_enabled
from app.services.keycloak_portal_client import configure_keycloak_portal_client_if_enabled
from app.services.federated_directory_sync import sync_keycloak_from_federated_directory
from app.services.enrollment_jobs import enqueue_enrollment, start_enrollment_worker_if_enabled, stop_enrollment_worker
from app.services.invitation_dispatcher import start_invitation_dispatcher_if_enabled, stop_invitation_dispatcher
from app.services.tenant_inventory_import import (
    import_missing_tenants_from_eappraisal,
    import_missing_tenants_from_srms,
)

settings = get_settings()
configure_logging(settings.app_env)
allowed_origins = [origin.strip() for origin in settings.cors_allowed_origins.split(",") if origin.strip()]
logger = logging.getLogger("hris_core.access")

app = FastAPI(
    title="HRIS Core API",
    version="1.0.0",
    description="Integration layer aggregating SRMS, eAppraisal, and eLeave for the HRIS Portal",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def attach_correlation_id(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-Id") or str(uuid.uuid4())
    request.state.correlation_id = correlation_id
    start = time.perf_counter()
    try:
        response: Response = await call_next(request)
    except Exception:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.exception(
            "HTTP request failed",
            extra={
                "correlation_id": correlation_id,
                "method": request.method,
                "path": request.url.path,
                "query": str(request.url.query or ""),
                "duration_ms": duration_ms,
            },
        )
        raise

    response.headers["X-Correlation-Id"] = correlation_id
    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    logger.info(
        "HTTP request completed",
        extra={
            "correlation_id": correlation_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    return response


@app.on_event("startup")
def validate_runtime_settings() -> None:
    settings.validate_runtime()
    db_readiness = ensure_runtime_databases_ready()
    created_now = bool((db_readiness or {}).get("database_created_on_this_startup"))
    pause_seconds = max(0, int(settings.startup_pause_after_db_create_seconds))
    if created_now and pause_seconds > 0:
        logger.warning(
            "Startup pause after first-time DB creation enabled: sleeping for %ss before continuing startup",
            pause_seconds,
        )
        time.sleep(pause_seconds)
    _wait_for_tenant_registry_if_needed()
    try:
        email_config_result = configure_keycloak_realm_email_if_enabled()
        logger.warning("Keycloak email configuration: %s", json.dumps(email_config_result))
    except Exception:
        logger.exception("Keycloak realm email configuration failed")
    try:
        portal_client_result = configure_keycloak_portal_client_if_enabled()
        logger.warning("Keycloak portal client configuration: %s", json.dumps(portal_client_result))
    except Exception:
        logger.exception("Keycloak portal client configuration failed")
    try:
        bootstrap_admin_accounts_if_enabled()
    except Exception:
        logger.exception("Startup admin bootstrap failed")
    if settings.enable_startup_tenant_inventory_import:
        system_actor = AuthenticatedUser(
            sub="startup.import",
            username="startup.import",
            email="startup.import@hris.local",
            tenant_id=settings.dev_default_tenant_id or "system",
            roles=["hris:super_admin"],
            effective_role="hris:super_admin",
            employee_id=None,
            raw_token=None,
            token_claims={},
        )
        try:
            import_result = import_missing_tenants_from_srms(
                system_actor,
                max_records=settings.startup_tenant_inventory_max_records,
            )
            logger.warning(
                "Startup tenant inventory import completed: %s",
                json.dumps(
                    {
                        "scanned": import_result.get("scanned", 0),
                        "inserted": import_result.get("inserted", 0),
                        "native_inventory_upserted": import_result.get("native_inventory_upserted", 0),
                        "canonical_tenants_created": import_result.get("canonical_tenants_created", 0),
                        "projections_created": import_result.get("projections_created", 0),
                        "skipped": import_result.get("skipped", 0),
                        "errors_count": len(import_result.get("errors", []) or []),
                        "errors_sample": (import_result.get("errors", []) or [])[:10],
                    },
                    ensure_ascii=True,
                ),
            )
        except HTTPException as exc:
            # Do not block API startup if inventory source is unavailable or auth is not aligned yet.
            logger.warning(
                "Startup tenant inventory import skipped: %s",
                str(exc.detail),
            )
        except Exception:
            # Keep non-HTTP failures visible for diagnosis but still non-fatal to startup.
            logger.exception("Startup tenant inventory import failed")
    if settings.enable_startup_eappraisal_tenant_inventory_import:
        system_actor = AuthenticatedUser(
            sub="startup.import.eappraisal",
            username="startup.import.eappraisal",
            email="startup.import.eappraisal@hris.local",
            tenant_id=settings.dev_default_tenant_id or "system",
            roles=["hris:super_admin"],
            effective_role="hris:super_admin",
            employee_id=None,
            raw_token=None,
            token_claims={},
        )
        try:
            import_result = import_missing_tenants_from_eappraisal(
                system_actor,
                max_records=settings.startup_tenant_inventory_max_records,
            )
            logger.warning(
                "Startup eAppraisal tenant inventory import completed: %s",
                json.dumps(
                    {
                        "scanned": import_result.get("scanned", 0),
                        "inserted": import_result.get("inserted", 0),
                        "native_inventory_upserted": import_result.get("native_inventory_upserted", 0),
                        "canonical_tenants_created": import_result.get("canonical_tenants_created", 0),
                        "projections_created": import_result.get("projections_created", 0),
                        "skipped": import_result.get("skipped", 0),
                        "errors_count": len(import_result.get("errors", []) or []),
                        "errors_sample": (import_result.get("errors", []) or [])[:10],
                    },
                    ensure_ascii=True,
                ),
            )
        except HTTPException as exc:
            logger.warning(
                "Startup eAppraisal tenant inventory import skipped: %s",
                str(exc.detail),
            )
        except Exception:
            logger.exception("Startup eAppraisal tenant inventory import failed")
    enrollment_mode = settings.startup_federated_enrollment_mode.strip().lower()
    if enrollment_mode in {"discover", "apply"}:
        system_actor = AuthenticatedUser(
            sub="startup.enrollment",
            username="startup.enrollment",
            email="startup.enrollment@hris.local",
            tenant_id=settings.dev_default_tenant_id or "system",
            roles=["hris:super_admin"],
            effective_role="hris:super_admin",
            employee_id=None,
            raw_token=None,
            token_claims={},
        )
        try:
            enrollment_result = enqueue_enrollment(
                actor=system_actor, tenant_id=None, mode=enrollment_mode,
                max_users=settings.federated_keycloak_sync_max_users_per_run,
            )
            logger.warning(
                "Startup federated enrollment %s queued: %s",
                enrollment_mode,
                json.dumps({"job_id": enrollment_result.get("job_id"), "status": enrollment_result.get("status")}),
            )
        except Exception:
            logger.exception("Startup federated enrollment %s failed", enrollment_mode)
    if settings.enable_post_deploy_sync_automation:
        system_actor = AuthenticatedUser(
            sub="startup.automation",
            username="startup.automation",
            email="startup.automation@hris.local",
            tenant_id=settings.dev_default_tenant_id or "system",
            roles=["hris:super_admin"],
            effective_role="hris:super_admin",
            employee_id=None,
            raw_token=None,
            token_claims={},
        )
        try:
            run_post_deploy_automation(system_actor)
        except Exception:
            logger.exception("Startup post-deploy automation failed")
    start_auto_sync_loop_if_enabled()
    start_enrollment_worker_if_enabled()
    start_invitation_dispatcher_if_enabled()


@app.on_event("shutdown")
def stop_background_workers() -> None:
    stop_enrollment_worker()
    stop_invitation_dispatcher()


def _wait_for_tenant_registry_if_needed() -> None:
    wait_needed = bool(
        settings.enable_startup_tenant_inventory_import
        or settings.enable_auto_sync_loop
        or settings.enable_post_deploy_sync_automation
        or settings.onboarding_auto_sync_new_tenants
    )
    if not wait_needed:
        return

    retries = max(1, int(settings.tenant_registry_startup_wait_retries))
    delay = max(0, int(settings.tenant_registry_startup_retry_delay_seconds))
    # In fail-open mode, keep startup responsive for local development.
    if settings.tenant_registry_startup_wait_fail_open:
        retries = min(retries, 5)
        delay = min(delay, 2)
    configured_base = str(settings.tenant_registry_base_url).rstrip("/")
    health_url = f"{configured_base}/health"
    probe_urls = [health_url]
    # Prefer configured URL, but probe 127.0.0.1 fallback for local runs where
    # localhost/IPv6 or proxy env can make loopback checks flaky.
    if "localhost" in configured_base.lower():
        probe_urls.append(health_url.replace("localhost", "127.0.0.1"))
    last_error: Exception | None = None

    def _tcp_reachable(url: str) -> bool:
        split = httpx.URL(url)
        host = split.host or "127.0.0.1"
        port = split.port or (443 if split.scheme == "https" else 80)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(max(1, settings.tenant_registry_timeout_seconds))
        try:
            sock.connect((host, int(port)))
            return True
        except Exception:
            return False
        finally:
            try:
                sock.close()
            except Exception:
                pass

    for attempt in range(1, retries + 1):
        readiness_confirmed = False
        for probe_url in probe_urls:
            try:
                with httpx.Client(
                    timeout=max(2, settings.tenant_registry_timeout_seconds),
                    trust_env=False,
                ) as client:
                    response = client.get(probe_url)
                    response.raise_for_status()
                logger.warning(
                    "Tenant Registry readiness confirmed before automation startup: %s",
                    json.dumps(
                        {
                            "health_url": probe_url,
                            "attempt": attempt,
                            "retries": retries,
                            "ready": True,
                        },
                        ensure_ascii=True,
                    ),
                )
                readiness_confirmed = True
                break
            except Exception as exc:
                last_error = exc
                if _tcp_reachable(probe_url):
                    logger.warning(
                        "Tenant Registry HTTP health probe failed but TCP is reachable; continuing startup: %s",
                        json.dumps(
                            {
                                "health_url": probe_url,
                                "attempt": attempt,
                                "retries": retries,
                                "tcp_reachable": True,
                                "last_error": str(exc),
                            },
                            ensure_ascii=True,
                        ),
                    )
                    readiness_confirmed = True
                    break
        if readiness_confirmed:
            return
        else:
            if attempt == 1 or attempt == retries or attempt % 5 == 0:
                logger.warning(
                    "Waiting for Tenant Registry readiness (%s/%s): %s",
                    attempt,
                    retries,
                    str(last_error),
                )
            if attempt < retries and delay > 0:
                time.sleep(delay)

    if settings.tenant_registry_startup_wait_fail_open:
        logger.warning(
            "Tenant Registry readiness wait exhausted; continuing startup with fail-open enabled: %s",
            json.dumps(
                {
                    "retries": retries,
                    "delay_seconds": delay,
                    "last_error": str(last_error),
                    "fail_open": True,
                },
                ensure_ascii=True,
            ),
        )
        return

    raise RuntimeError(
        "Tenant Registry readiness wait exhausted during HRIS Core startup. "
        f"Last error: {last_error}"
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    correlation_id = getattr(request.state, "correlation_id", "")
    detail = exc.detail
    if isinstance(detail, dict):
        code = str(detail.get("code") or f"HTTP_{exc.status_code}")
        message = str(detail.get("message") or detail.get("detail") or "Request failed")
    else:
        code = f"HTTP_{exc.status_code}"
        message = str(detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": code,
            "message": message,
            "correlation_id": correlation_id,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    correlation_id = getattr(request.state, "correlation_id", "")
    logger.warning(
        "Request validation failed",
        extra={
            "correlation_id": correlation_id,
            "method": request.method,
            "path": request.url.path,
            "errors": exc.errors(),
        },
    )
    return JSONResponse(
        status_code=422,
        content={
            "code": "HTTP_422",
            "message": "Request validation failed",
            "correlation_id": correlation_id,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    correlation_id = getattr(request.state, "correlation_id", "")
    logger.exception(
        "Unhandled application exception",
        extra={
            "correlation_id": correlation_id,
            "method": request.method,
            "path": request.url.path,
        },
    )
    return JSONResponse(
        status_code=500,
        content={
            "code": "HTTP_500",
            "message": "Internal server error",
            "correlation_id": correlation_id,
        },
    )


app.include_router(account_router)
app.include_router(me_router)
app.include_router(auth_sso_router)
app.include_router(dashboard_router)
app.include_router(employees_router)
app.include_router(profile_router)
app.include_router(modules_router)
app.include_router(tenants_router)
app.include_router(tenant_federation_router)
app.include_router(integrations_debug_router)
app.include_router(federated_directory_debug_router)
app.include_router(integration_sync_router)
app.include_router(jit_setup_router)


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok"}
