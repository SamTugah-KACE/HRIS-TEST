from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.dashboard import router as dashboard_router
from app.api.employees import router as employees_router
from app.api.me import router as me_router

app = FastAPI(
    title="HRIS Core API",
    version="1.0.0",
    description="Integration layer aggregating SRMS, eAppraisal, and eLeave for the HRIS Portal",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(me_router)
app.include_router(dashboard_router)
app.include_router(employees_router)


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok"}
