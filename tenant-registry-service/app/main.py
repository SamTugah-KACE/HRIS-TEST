import logging
import time

from fastapi import FastAPI

from app.core.database import Base, engine
from app.core.db_bootstrap import ensure_registry_database_ready, log_registry_readiness
from app.core.settings import get_settings
from app.api.tenants import router as tenants_router

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Tenant Registry Service",
    version="1.0.0",
)

app.include_router(tenants_router)


@app.on_event("startup")
def initialize_registry_database() -> None:
    settings = get_settings()
    attempts = max(1, int(settings.startup_init_retries))
    delay = max(0, int(settings.startup_init_retry_delay_seconds))
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            created_now = ensure_registry_database_ready()
            Base.metadata.create_all(bind=engine)
            log_registry_readiness(created_now)
            logger.warning("Tenant Registry startup database initialization completed")
            return
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Tenant Registry waiting for database readiness (%s/%s): %s",
                attempt,
                attempts,
                str(exc),
            )
            if attempt < attempts and delay > 0:
                time.sleep(delay)

    raise RuntimeError(
        "Tenant Registry startup failed after waiting for database readiness. "
        f"Last error: {last_error}"
    )


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok"}


