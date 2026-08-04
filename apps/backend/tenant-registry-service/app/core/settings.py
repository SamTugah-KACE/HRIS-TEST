from functools import lru_cache
from typing import Optional

from pydantic import AnyUrl, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Tenant Registry Service"
    database_url: AnyUrl = Field(..., env="DATABASE_URL")
    db_auto_create_on_startup: bool = Field(True, env="DB_AUTO_CREATE_ON_STARTUP")
    db_bootstrap_admin_url: Optional[str] = Field(None, env="DB_BOOTSTRAP_ADMIN_URL")
    db_bootstrap_admin_database: str = Field("postgres", env="DB_BOOTSTRAP_ADMIN_DATABASE")
    db_bootstrap_connect_retries: int = Field(5, env="DB_BOOTSTRAP_CONNECT_RETRIES")
    db_bootstrap_retry_delay_seconds: int = Field(2, env="DB_BOOTSTRAP_RETRY_DELAY_SECONDS")
    db_bootstrap_timeout_seconds: int = Field(5, env="DB_BOOTSTRAP_TIMEOUT_SECONDS")
    startup_init_retries: int = Field(60, env="STARTUP_INIT_RETRIES")
    startup_init_retry_delay_seconds: int = Field(5, env="STARTUP_INIT_RETRY_DELAY_SECONDS")

    # Basic auth for internal clients (e.g., SRMS, eAppraisal, eLeave, HRIS Core)
    internal_basic_auth_username: str = Field(..., env="INTERNAL_BASIC_AUTH_USERNAME")
    internal_basic_auth_password: str = Field(..., env="INTERNAL_BASIC_AUTH_PASSWORD")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
