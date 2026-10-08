from __future__ import annotations

from typing import Any

import pandas as pd

from src.data.data_manager import DataManager
from src.data.qlib_client import QlibDataProvider
from src.factors.price_factors import calculate_price_factors


class StockResearchService:
    """Read-only facade so UI code never calls Qlib directly."""

    def __init__(self, manager: DataManager, qlib_provider: QlibDataProvider):
        self.manager = manager
        self.qlib = qlib_provider

    def latest_rankings(self) -> pd.DataFrame:
        return self.manager.query(
            """
            WITH latest AS (SELECT max(trade_date) AS trade_date FROM daily_rankings)
            SELECT r.*, m.name, m.industry, m.board, m.exchange,
                   s.last_price, s.pct_change, s.pe_ttm, s.pb, s.market_cap,
                   s.amount, s.turnover_rate
            FROM daily_rankings r
            JOIN latest l ON r.trade_date = l.trade_date
            LEFT JOIN stock_master m USING (ticker)
            LEFT JOIN market_snapshot s ON r.ticker = s.ticker AND r.trade_date = s.trade_date
            ORDER BY r.rank
            """
        )

    def stock_summary(self, ticker: str) -> pd.DataFrame:
        return self.manager.query(
            """
            SELECT r.*, m.name, m.industry, m.board, m.exchange, m.listing_date,
                   s.last_price, s.pct_change, s.pe_ttm, s.pb, s.market_cap,
                   s.float_market_cap, s.amount, s.turnover_rate
            FROM daily_rankings r
            LEFT JOIN stock_master m USING (ticker)
            LEFT JOIN market_snapshot s ON r.ticker = s.ticker AND r.trade_date = s.trade_date
            WHERE r.ticker = ?
            ORDER BY r.trade_date DESC, r.update_time DESC
            LIMIT 1
            """,
            [ticker],
        )

    def price_history(self, ticker: str, lookback_days: int = 300) -> pd.DataFrame:
        calendar = self.qlib.calendar()
        if len(calendar) == 0:
            return pd.DataFrame()
        start = calendar[-min(lookback_days, len(calendar))]
        raw = self.qlib.daily_prices([ticker], str(start.date()), str(calendar[-1].date())).dropna(subset=["close"])
        return calculate_price_factors(raw, calculate_rolling_drawdown=False)

    def rank_history(self, ticker: str, limit: int = 250) -> pd.DataFrame:
        return self.manager.query(
            """
            SELECT trade_date, rank, percentile, final_score, factor_score, qlib_score,
                   quality_score, value_score, growth_score, momentum_score,
                   trend_score, risk_score, liquidity_score
            FROM daily_rankings WHERE ticker = ?
            ORDER BY trade_date DESC LIMIT ?
            """,
            [ticker, limit],
        ).sort_values("trade_date")

