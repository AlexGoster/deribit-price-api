from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    """Configuration is instantiated by the app factory, not at import time."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str
    deribit_base_url: str = "https://www.deribit.com/api/v2"
    poll_interval_seconds: float = Field(default=60, gt=0)
    request_timeout_seconds: float = Field(default=10, gt=0)
    retry_attempts: int = Field(default=3, ge=1, le=5)
    retry_delay_seconds: float = Field(default=1, ge=0, le=30)
    collector_enabled: bool = True

    @field_validator("database_url")
    @classmethod
    def require_async_driver(cls, value: str) -> str:
        if make_url(value).drivername not in {"postgresql+asyncpg", "sqlite+aiosqlite"}:
            raise ValueError("Use postgresql+asyncpg (or sqlite+aiosqlite for tests)")
        return value

    @field_validator("deribit_base_url")
    @classmethod
    def require_https(cls, value: str) -> str:
        from urllib.parse import urlsplit

        url = urlsplit(value)
        if url.scheme != "https" or not url.netloc or url.username or url.password:
            raise ValueError("Deribit base URL must be HTTPS without credentials")
        if url.query or url.fragment:
            raise ValueError("Deribit base URL must not have query or fragment")
        return value.rstrip("/")
