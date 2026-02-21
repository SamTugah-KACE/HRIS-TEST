from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.dependencies.db import get_db
from app.models.tenant import Tenant
from app.schemas.tenant import TenantOut

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
