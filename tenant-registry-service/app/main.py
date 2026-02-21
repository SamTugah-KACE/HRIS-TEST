from fastapi import FastAPI

from app.core.database import Base, engine
from app.api.tenants import router as tenants_router

# Ensure models are registered
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Tenant Registry Service",
    version="1.0.0",
)

app.include_router(tenants_router)


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok"}


