from __future__ import annotations

from bot.config.settings import Settings
from bot.providers.base import XAnalyticsProvider
from bot.providers.mock import MockXAnalyticsProvider
from bot.providers.x_api import XApiProvider


def create_provider(settings: Settings) -> XAnalyticsProvider:
    if settings.x_provider_mode == "x_api":
        if settings.x_bearer_token is None:
            raise RuntimeError("X_BEARER_TOKEN is required when X_PROVIDER_MODE=x_api.")
        return XApiProvider(settings.x_bearer_token.get_secret_value())
    return MockXAnalyticsProvider()

