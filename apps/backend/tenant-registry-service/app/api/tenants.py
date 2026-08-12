from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.settings import get_settings
from app.dependencies.db import get_db
from app.models.tenant import Tenant
from app.schemas.tenant import TenantImportIn, TenantImportResult, TenantOut

router = APIRouter(prefix="/tenants", tags=["tenants"])

security = HTTPBasic()
settings = get_settings()


def verify_internal_client(credentials: HTTPBasicCredentials = Depends(security)) -> None:
    correct_username = settings.internal_basic_auth_username
    correct_password = settings.internal_basic_auth_password
    if credentials.username != correct_username or credentials.password != correct_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid client credentials",
        )


@router.get("", response_model=list[TenantOut], dependencies=[Depends(verify_internal_client)])
def list_tenants(
    is_active: Optional[bool] = Query(None),
    search: str = Query(""),
    db: Session = Depends(get_db),
):
    query = db.query(Tenant)
    if is_active is not None:
        query = query.filter(Tenant.is_active == is_active)
    if search:
        query = query.filter(Tenant.name.ilike(f"%{search}%"))
    tenants = query.order_by(Tenant.name).all()
    return [TenantOut.model_validate(t) for t in tenants]


@router.get("/{tenant_id}", response_model=TenantOut, dependencies=[Depends(verify_internal_client)])
def get_tenant(tenant_id: UUID, db: Session = Depends(get_db)) -> TenantOut:
    tenant = (
        db.query(Tenant)
        .filter(Tenant.tenant_id == tenant_id)
        .first()
    )
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    return TenantOut.model_validate(tenant)


@router.post(
    "/sync/import",
    response_model=TenantImportResult,
    dependencies=[Depends(verify_internal_client)],
)
def import_tenant(payload: TenantImportIn, db: Session = Depends(get_db)) -> TenantImportResult:
    incoming_code = payload.code.strip()
    incoming_name = payload.name.strip()
    if not incoming_code or not incoming_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="code and name are required",
        )

    # Immutable tenant_id is the only cross-module identity key. Each system
    # enforces its own label uniqueness, but the same label appearing in two
    # different modules is not proof that those tenants are the same entity.
    existing = None
    if payload.tenant_id is not None:
        existing = db.query(Tenant).filter(Tenant.tenant_id == payload.tenant_id).first()
    if existing is None and payload.tenant_id is None:
        legacy_matches = db.query(Tenant).filter(Tenant.code == incoming_code).limit(2).all()
        if len(legacy_matches) > 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Legacy code lookup is ambiguous; resubmit with canonical tenant_id",
            )
        existing = legacy_matches[0] if legacy_matches else None

    if existing is not None:
        # Idempotent merge: keep canonical identity but fill missing module metadata.
        # This allows multi-module inventory imports to enrich one tenant row over time.
        changed = False
        if payload.srms_schema and not existing.srms_schema:
            existing.srms_schema = payload.srms_schema
            changed = True
        if payload.srms_slug and not existing.srms_slug:
            existing.srms_slug = payload.srms_slug
            changed = True
        if payload.eappraisal_subdomain and not existing.eappraisal_subdomain:
            existing.eappraisal_subdomain = payload.eappraisal_subdomain
            changed = True
        if payload.eleave_subdomain and not existing.eleave_subdomain:
            existing.eleave_subdomain = payload.eleave_subdomain
            changed = True
        # Prefer active state if any trusted source marks tenant active.
        if payload.is_active and not existing.is_active:
            existing.is_active = True
            changed = True
        if changed:
            existing.updated_at = datetime.utcnow()
            db.add(existing)
            db.commit()
            db.refresh(existing)
        return TenantImportResult(inserted=False, tenant=TenantOut.model_validate(existing))

    duplicate_label = db.query(Tenant).filter(
        (func.lower(func.trim(Tenant.code)) == incoming_code.casefold())
        | (func.lower(func.trim(Tenant.name)) == incoming_name.casefold())
    ).first()
    if duplicate_label is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tenant name or code already exists in HRIS",
        )

    now = datetime.utcnow()
    tenant = Tenant(
        tenant_id=payload.tenant_id or uuid4(),
        code=incoming_code,
        name=incoming_name,
        srms_schema=(payload.srms_schema or None),
        srms_slug=(payload.srms_slug or None),
        eappraisal_subdomain=(payload.eappraisal_subdomain or None),
        eleave_subdomain=(payload.eleave_subdomain or None),
        is_active=payload.is_active,
        created_at=now,
        updated_at=now,
    )
    db.add(tenant)
    try:
        db.commit()
    except IntegrityError:
        # Handle concurrent inserts safely as idempotent behavior.
        db.rollback()
        if payload.tenant_id is not None:
            existing = db.query(Tenant).filter(Tenant.tenant_id == payload.tenant_id).first()
        if existing is None and payload.tenant_id is None:
            legacy_matches = db.query(Tenant).filter(Tenant.code == incoming_code).limit(2).all()
            existing = legacy_matches[0] if len(legacy_matches) == 1 else None
        if existing is None:
            raise
        return TenantImportResult(inserted=False, tenant=TenantOut.model_validate(existing))
    db.refresh(tenant)
    return TenantImportResult(inserted=True, tenant=TenantOut.model_validate(tenant))
