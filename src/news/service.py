from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class NewsItem:
    ticker: str | None
    published_at: datetime
    title: str
    source: str
    url: str | None = None
    summary: str | None = None


class NewsProvider(Protocol):
    """Contract for optional future news sources; not a trading-signal API."""

    def fetch_since(self, since: datetime) -> list[NewsItem]: ...
