from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field


class TenantOut(BaseModel):
    tenant_id: UUID
    code: str
    name: str

    srms_schema: str | None = None
    srms_slug: str | None = None

    eappraisal_subdomain: str | None = None
    eleave_subdomain: str | None = None

    is_active: bool

    created_at: datetime = Field(...)
    updated_at: datetime = Field(...)

    class Config:
        from_attributes = True
