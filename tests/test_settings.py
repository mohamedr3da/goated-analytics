import pytest
from pydantic import ValidationError

from bot.config.settings import Settings


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", set()),
        ("[]", set()),
        ("[123, 456]", {123, 456}),
        ("123", {123}),
        ("123,456", {123, 456}),
        ([123, "456"], {123, 456}),
    ],
)
def test_authorized_id_settings_accept_blank_json_and_comma_lists(
    raw: object,
    expected: set[int],
) -> None:
    settings = Settings(
        x_provider_mode="mock",
        authorized_discord_user_ids=raw,
        authorized_discord_role_ids=raw,
    )

    assert settings.authorized_discord_user_ids == expected
    assert settings.authorized_discord_role_ids == expected


def test_authorized_id_settings_reject_invalid_ids_with_clear_error() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(x_provider_mode="mock", authorized_discord_user_ids="123,not-a-number")

    assert "integer Discord IDs" in str(exc_info.value)


def test_real_x_runtime_settings_have_safe_defaults() -> None:
    settings = Settings(x_provider_mode="mock")

    assert settings.x_initial_backfill_days == 30
    assert settings.x_initial_backfill_max_posts == 200
    assert settings.x_request_timeout_seconds == 20
    assert settings.x_max_retries == 3
    assert settings.x_max_concurrency == 2
    assert settings.snapshot_min_interval_minutes == 60


def test_scraper_provider_mode_is_accepted_for_local_proof_of_concept() -> None:
    settings = Settings(x_provider_mode="scraper")

    assert settings.x_provider_mode == "scraper"


def test_legacy_api_provider_mode_aliases_to_official_x_api_mode() -> None:
    settings = Settings(x_provider_mode="api")

    assert settings.x_provider_mode == "x_api"
