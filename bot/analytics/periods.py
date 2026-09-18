from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True)
class AnalyticsPeriod:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        start = self.start.astimezone(UTC)
        end = self.end.astimezone(UTC)
        if end <= start:
            raise ValueError("Analytics period end must be after start.")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)

    @classmethod
    def trailing(cls, label: str, *, now: datetime | None = None) -> AnalyticsPeriod:
        end = (now or datetime.now(UTC)).astimezone(UTC)
        normalized = label.strip().lower()
        durations = {
            "24h": timedelta(hours=24),
            "1d": timedelta(days=1),
            "7d": timedelta(days=7),
            "30d": timedelta(days=30),
        }
        try:
            duration = durations[normalized]
        except KeyError as exc:
            raise ValueError("Supported periods are 24h, 1d, 7d, and 30d.") from exc
        return cls(start=end - duration, end=end)

