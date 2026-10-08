from __future__ import annotations

import pandas as pd

from src.data.validators import require_columns
from src.factors.liquidity import add_liquidity_factors
from src.factors.momentum import add_momentum_factors
from src.factors.risk import add_risk_factors, max_drawdown
from src.factors.trend import add_trend_factors


PRICE_FACTOR_COLUMNS = [
    "momentum_20", "momentum_60", "momentum_120", "momentum_250", "momentum_12_1",
    "price_ma20", "price_ma60", "price_ma120", "price_ma250", "ma60_slope", "trend_consistency",
    "volatility_20", "volatility_60", "downside_volatility_60", "max_drawdown_120", "atr_14", "extreme_move_20",
    "average_amount_20", "average_turnover_20", "amihud_20",
]


def calculate_price_factors(frame: pd.DataFrame, *, calculate_rolling_drawdown: bool = True) -> pd.DataFrame:
    require_columns(frame, ["ticker", "trade_date", "open", "high", "low", "close", "volume"], "price factors")
    result = frame.copy()
    result["trade_date"] = pd.to_datetime(result["trade_date"])
    for column in ["open", "high", "low", "close", "volume", "amount", "turnover_rate"]:
        if column in result:
            result[column] = pd.to_numeric(result[column], errors="coerce").astype(float)
    result = result.sort_values(["ticker", "trade_date"], kind="stable").reset_index(drop=True)
    result = add_momentum_factors(result)
    result = add_trend_factors(result)
    result = add_risk_factors(result, calculate_rolling_drawdown=calculate_rolling_drawdown)
    result = add_liquidity_factors(result)
    return result


def latest_price_factors(frame: pd.DataFrame, as_of: str | pd.Timestamp | None = None) -> pd.DataFrame:
    calculated = calculate_price_factors(frame, calculate_rolling_drawdown=False)
    if as_of is not None:
        calculated = calculated.loc[calculated["trade_date"] <= pd.Timestamp(as_of)]
    windows = calculated.sort_values(["ticker", "trade_date"]).groupby("ticker", sort=False).tail(120)
    drawdowns = windows.groupby("ticker", sort=False)["close"].agg(
        lambda values: abs(max_drawdown(values.to_numpy(dtype=float))) if values.notna().sum() >= 120 else float("nan")
    )
    latest = calculated.sort_values(["ticker", "trade_date"]).groupby("ticker", as_index=False, sort=False).tail(1).copy()
    latest["max_drawdown_120"] = latest["ticker"].map(drawdowns)
    latest["history_count"] = latest["ticker"].map(calculated.groupby("ticker").size())
    return latest.reset_index(drop=True)

