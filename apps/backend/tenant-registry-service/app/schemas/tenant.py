from uuid import UUID
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class TenantOut(BaseModel):
    tenant_id: UUID
    code: str
    name: str

    srms_schema: Optional[str] = None
    srms_slug: Optional[str] = None

    eappraisal_subdomain: Optional[str] = None
    eleave_subdomain: Optional[str] = None

    is_active: bool

    created_at: datetime = Field(...)
    updated_at: datetime = Field(...)

    class Config:
        from_attributes = True


class TenantImportIn(BaseModel):
    tenant_id: Optional[UUID] = None
    code: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=255)
    srms_schema: Optional[str] = None
    srms_slug: Optional[str] = None
    eappraisal_subdomain: Optional[str] = None
    eleave_subdomain: Optional[str] = None
    is_active: bool = True


class TenantImportResult(BaseModel):
    inserted: bool
    tenant: TenantOut
