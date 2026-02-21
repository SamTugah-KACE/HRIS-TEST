from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "HRIS Core API"

    auth_mode: str = Field("dev", alias="AUTH_MODE")

    dev_default_tenant_id: Optional[str] = Field(
        "11111111-1111-1111-1111-111111111111", alias="DEV_DEFAULT_TENANT_ID"
    )
    dev_default_username: Optional[str] = Field("dev.admin", alias="DEV_DEFAULT_USERNAME")
    dev_default_roles: str = Field("hris:hr_manager", alias="DEV_DEFAULT_ROLES")

    keycloak_issuer: Optional[str] = Field(None, alias="KEYCLOAK_ISSUER")
    keycloak_jwks_url: Optional[str] = Field(None, alias="KEYCLOAK_JWKS_URL")
    keycloak_audience: Optional[str] = Field(None, alias="KEYCLOAK_AUDIENCE_HRIS_CORE")

    tenant_registry_base_url: str = Field(
        "http://localhost:8001", alias="TENANT_REGISTRY_BASE_URL"
    )
    tenant_registry_timeout_seconds: int = Field(5, alias="TENANT_REGISTRY_TIMEOUT_SECONDS")
    tenant_registry_basic_auth_username: str = Field(
        "hris_internal", alias="TENANT_REGISTRY_BASIC_AUTH_USERNAME"
    )
    tenant_registry_basic_auth_password: str = Field(
        "change-me", alias="TENANT_REGISTRY_BASIC_AUTH_PASSWORD"
    )

    srms_base_url: Optional[str] = Field(None, alias="SRMS_BASE_URL")

    eappraisal_domain_template: Optional[str] = Field(
        None, alias="EAPPRAISAL_DOMAIN_TEMPLATE"
    )

    eleave_domain_template: Optional[str] = Field(
        None, alias="ELEAVE_DOMAIN_TEMPLATE"
    )

    use_stub_data: bool = Field(True, alias="USE_STUB_DATA")
    http_client_timeout_seconds: int = Field(10, alias="HTTP_CLIENT_TIMEOUT_SECONDS")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "populate_by_name": True}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
