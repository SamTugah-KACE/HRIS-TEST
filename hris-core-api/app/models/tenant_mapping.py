from typing import Optional

from pydantic import BaseModel


class TenantMapping(BaseModel):
    tenant_id: str
    code: str
    name: str
    srms_schema: Optional[str] = None
    srms_slug: Optional[str] = None
    eappraisal_subdomain: Optional[str] = None
    eleave_subdomain: Optional[str] = None
    is_active: bool
