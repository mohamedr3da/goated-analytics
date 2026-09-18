from __future__ import annotations

import pytest

from bot.config.settings import Settings
from bot.providers.factory import create_provider
from bot.providers.mock import MockXAnalyticsProvider
from bot.providers.public_scraper import PublicScraperProvider


def test_provider_factory_uses_mock_by_default() -> None:
    assert isinstance(create_provider(Settings(x_provider_mode="mock")), MockXAnalyticsProvider)


@pytest.mark.asyncio
async def test_provider_factory_creates_public_scraper_mode() -> None:
    provider = create_provider(
        Settings(
            x_provider_mode="scraper",
            x_request_timeout_seconds=6,
            x_recent_posts_limit=7,
        )
    )

    try:
        assert isinstance(provider, PublicScraperProvider)
    finally:
        await provider.aclose()
