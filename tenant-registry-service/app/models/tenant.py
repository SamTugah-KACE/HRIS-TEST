import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, String
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), unique=True, nullable=False)  # global tenant id
    code = Column(String(64), unique=True, nullable=False)
    name = Column(String(255), nullable=False)

    # SRMS mapping
    srms_schema = Column(String(255), nullable=True)
    srms_slug = Column(String(255), nullable=True)  # used for UI: /{slug}/signin

    # eAppraisal mapping
    eappraisal_subdomain = Column(String(255), nullable=True)  # e.g. "gigov"

    # eLeave mapping
    eleave_subdomain = Column(String(255), nullable=True)  # e.g. "gigov"

    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
