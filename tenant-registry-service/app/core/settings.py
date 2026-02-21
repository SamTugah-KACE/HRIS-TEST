from functools import lru_cache
from pydantic_settings import BaseSettings, AnyUrl, Field


class Settings(BaseSettings):
    app_name: str = "Tenant Registry Service"
    database_url: AnyUrl = Field(..., env="DATABASE_URL")

    # Basic auth for internal clients (e.g., SRMS, eAppraisal, eLeave, HRIS Core)
    internal_basic_auth_username: str = Field(..., env="INTERNAL_BASIC_AUTH_USERNAME")
    internal_basic_auth_password: str = Field(..., env="INTERNAL_BASIC_AUTH_PASSWORD")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
