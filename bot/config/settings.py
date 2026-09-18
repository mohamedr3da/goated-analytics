from __future__ import annotations

from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_id_set(value: object) -> set[int]:
    if value is None or value == "":
        return set()
    if isinstance(value, set):
        return {int(item) for item in value}
    if isinstance(value, list | tuple):
        return {int(item) for item in value}
    if isinstance(value, str):
        return {int(item.strip()) for item in value.split(",") if item.strip()}
    raise TypeError("Expected a comma-separated string or collection of integer IDs.")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    discord_token: SecretStr | None = None
    database_url: str = "sqlite+aiosqlite:///./data/x_analytics.db"
    x_provider_mode: Literal["mock", "x_api"] = "mock"
    x_bearer_token: SecretStr | None = None
    collection_interval_minutes: int = Field(default=60, ge=15, le=1440)
    x_recent_posts_limit: int = Field(default=20, ge=5, le=100)
    authorized_discord_user_ids: set[int] = Field(default_factory=set)
    authorized_discord_role_ids: set[int] = Field(default_factory=set)
    public_analytics_enabled: bool = True
    log_level: str = "INFO"

    @field_validator("authorized_discord_user_ids", "authorized_discord_role_ids", mode="before")
    @classmethod
    def parse_id_sets(cls, value: object) -> set[int]:
        return _parse_id_set(value)

