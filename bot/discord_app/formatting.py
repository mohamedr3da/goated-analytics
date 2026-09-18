from __future__ import annotations


def compact_number(value: int | None) -> str:
    if value is None:
        return "Unavailable"
    abs_value = abs(value)
    for suffix, divisor in (("B", 1_000_000_000), ("M", 1_000_000), ("K", 1_000)):
        if abs_value >= divisor:
            formatted = value / divisor
            return f"{formatted:.2f}".rstrip("0").rstrip(".") + suffix
    return f"{value:,}"


def signed_compact_number(value: int | None) -> str:
    if value is None:
        return "Unavailable"
    sign = "+" if value > 0 else ""
    return f"{sign}{compact_number(value)}"


def safe_preview(text: str, *, limit: int = 120) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def coverage_label(coverage_seconds: int, requested_seconds: int) -> str:
    return f"{_duration_label(coverage_seconds)} / {_duration_label(requested_seconds)}"


def _duration_label(seconds: int) -> str:
    hours = max(0, seconds) // 3600
    days, rem_hours = divmod(hours, 24)
    if days == 1 and rem_hours == 0:
        return "24h"
    if days and rem_hours:
        return f"{days}d {rem_hours}h"
    if days:
        return f"{days}d"
    return f"{hours}h"
