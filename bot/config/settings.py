from __future__ import annotations

import json
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
        normalized = value.strip()
        if normalized == "":
            return set()
        if normalized.startswith("["):
            try:
                parsed = json.loads(normalized)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "Expected blank, JSON list, comma-separated, or single integer Discord IDs."
                ) from exc
            return _parse_id_set(parsed)
        try:
            return {int(item.strip()) for item in normalized.split(",") if item.strip()}
        except ValueError as exc:
            raise ValueError(
                "Expected blank, JSON list, comma-separated, or single integer Discord IDs."
            ) from exc
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
    x_initial_backfill_days: int = Field(default=30, ge=1, le=365)
    x_initial_backfill_max_posts: int = Field(default=200, ge=5, le=5000)
    x_request_timeout_seconds: int = Field(default=20, ge=5, le=120)
    x_max_retries: int = Field(default=3, ge=0, le=8)
    x_max_concurrency: int = Field(default=2, ge=1, le=20)
    snapshot_min_interval_minutes: int = Field(default=60, ge=0, le=1440)
    authorized_discord_user_ids: set[int] = Field(default_factory=set)
    authorized_discord_role_ids: set[int] = Field(default_factory=set)
    public_analytics_enabled: bool = True
    log_level: str = "INFO"

    @field_validator("authorized_discord_user_ids", "authorized_discord_role_ids", mode="before")
    @classmethod
    def parse_id_sets(cls, value: object) -> set[int]:
        return _parse_id_set(value)
