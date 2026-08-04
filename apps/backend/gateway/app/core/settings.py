from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = Field("HRIS Gateway API", alias="APP_NAME")
    app_env: str = Field("development", alias="APP_ENV")
    cors_allowed_origins: str = Field(
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000",
        alias="CORS_ALLOWED_ORIGINS",
    )
    # Gateway federates by orchestrating existing Core contracts.
    core_api_base_url: str = Field("http://localhost:8000", alias="CORE_API_BASE_URL")
    core_api_timeout_seconds: int = Field(15, alias="CORE_API_TIMEOUT_SECONDS")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[arg-type]

