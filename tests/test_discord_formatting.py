from bot.discord_app.formatting import compact_number, coverage_label, safe_preview


def test_compact_number_formats_large_values_for_discord() -> None:
    assert compact_number(None) == "Unavailable"
    assert compact_number(999) == "999"
    assert compact_number(1_420) == "1.42K"
    assert compact_number(3_810_000) == "3.81M"
    assert compact_number(1_030_000_000) == "1.03B"


def test_coverage_label_shows_partial_history() -> None:
    assert coverage_label(24 * 3600, 24 * 3600) == "24h / 24h"
    assert coverage_label((5 * 24 + 4) * 3600, 7 * 24 * 3600) == "5d 4h / 7d"


def test_safe_preview_collapses_whitespace_and_respects_limit() -> None:
    assert safe_preview("hello\n\nworld", limit=20) == "hello world"
    assert safe_preview("x" * 20, limit=10) == "xxxxxxx..."

