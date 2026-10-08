from __future__ import annotations

import uuid
from datetime import date

import pandas as pd

from src.data.data_manager import DataManager
from src.data.universe import normalize_ticker
from src.utils.dates import now_shanghai


class HoldingsRepository:
    def __init__(self, manager: DataManager):
        self.manager = manager

    def add(self, ticker: str, buy_date: date, cost: float, quantity: float, notes: str = "") -> str:
        ticker = normalize_ticker(ticker)
        if cost <= 0 or quantity <= 0:
            raise ValueError("成本和数量必须大于 0")
        now = now_shanghai().replace(tzinfo=None)
        ranking = self.manager.query(
            "SELECT rank FROM daily_rankings WHERE ticker = ? AND trade_date <= ? ORDER BY trade_date DESC LIMIT 1",
            [ticker, buy_date],
        )
        position_id = uuid.uuid4().hex
        frame = pd.DataFrame(
            [{
                "position_id": position_id, "ticker": ticker, "buy_date": buy_date, "cost": cost,
                "quantity": quantity, "buy_rank": None if ranking.empty else int(ranking.iloc[0, 0]),
                "status": "HOLD", "notes": notes, "created_time": now, "update_time": now, "source": "manual",
            }]
        )
        self.manager._upsert("portfolio", frame, ["position_id"])
        return position_id

    def remove(self, position_id: str) -> None:
        with self.manager._write_lock, self.manager.connection() as connection:
            connection.execute("DELETE FROM portfolio WHERE position_id = ?", [position_id])

    def list(self) -> pd.DataFrame:
        frame = self.manager.query(
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
            SELECT p.*, m.name, s.last_price, s.pct_change, r.rank AS current_rank,
                   r.percentile AS current_percentile, r.final_score, r.risk_score,
                   date_diff('day', p.buy_date, current_date) AS holding_days
            FROM portfolio p
            LEFT JOIN stock_master m USING (ticker)
            LEFT JOIN latest_price s USING (ticker)
            LEFT JOIN latest_rank r USING (ticker)
            ORDER BY p.created_time
            """
        )
        if not frame.empty:
            frame["market_value"] = frame["last_price"] * frame["quantity"]
            frame["pnl"] = (frame["last_price"] - frame["cost"]) * frame["quantity"]
            frame["pnl_pct"] = frame["last_price"].div(frame["cost"]).sub(1.0)
            frame["rank_change"] = frame["buy_rank"] - frame["current_rank"]
        return frame

