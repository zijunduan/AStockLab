from __future__ import annotations

from datetime import date

import pandas as pd

from src.data.data_manager import DataManager
from src.data.universe import normalize_ticker
from src.utils.dates import now_shanghai


class WatchlistRepository:
    def __init__(self, manager: DataManager):
        self.manager = manager

    def add(self, ticker: str, notes: str = "") -> None:
        frame = pd.DataFrame(
            [{
                "ticker": normalize_ticker(ticker), "added_date": date.today(), "notes": notes,
                "update_time": now_shanghai().replace(tzinfo=None), "source": "manual",
            }]
        )
        self.manager._upsert("watchlist", frame, ["ticker"])

    def remove(self, ticker: str) -> None:
        with self.manager._write_lock, self.manager.connection() as connection:
            connection.execute("DELETE FROM watchlist WHERE ticker = ?", [normalize_ticker(ticker)])

    def list(self) -> pd.DataFrame:
        return self.manager.query(
            """
            WITH latest_rank AS (
              SELECT * EXCLUDE (rn) FROM (
                SELECT *, row_number() OVER (PARTITION BY ticker ORDER BY trade_date DESC, update_time DESC) rn
                FROM daily_rankings
              ) WHERE rn = 1
            ), latest_price AS (
              SELECT * EXCLUDE (rn) FROM (
                SELECT *, row_number() OVER (PARTITION BY ticker ORDER BY trade_date DESC, update_time DESC) rn
                FROM market_snapshot
              ) WHERE rn = 1
            )
            SELECT w.*, m.name, s.last_price, s.pct_change, r.rank, r.final_score,
                   r.qlib_score, r.factor_score, r.trend_score, r.risk_score
            FROM watchlist w
            LEFT JOIN stock_master m USING (ticker)
            LEFT JOIN latest_price s USING (ticker)
            LEFT JOIN latest_rank r USING (ticker)
            ORDER BY w.update_time DESC
            """
        )

