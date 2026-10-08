from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol


@dataclass(frozen=True)
class AnnouncementItem:
    ticker: str
    announcement_time: datetime
    title: str
    source: str
    report_period: date | None = None
    url: str | None = None

    def available_on(self, as_of: date | datetime) -> bool:
        cutoff = as_of.date() if isinstance(as_of, datetime) else as_of
        return self.announcement_time.date() <= cutoff


class AnnouncementProvider(Protocol):
    """Provider contract requiring the real publication timestamp."""

    def fetch_since(self, since: datetime) -> list[AnnouncementItem]: ...
