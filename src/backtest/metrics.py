from __future__ import annotations

import math

import numpy as np
import pandas as pd


def max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return float("nan")
    peaks = equity.cummax()
    return float((equity / peaks - 1.0).min())


def performance_metrics(
    equity_curve: pd.DataFrame,
    trades: pd.DataFrame,
    *,
    initial_cash: float,
    benchmark_returns: pd.Series | None = None,
) -> dict[str, float | int | None]:
    if equity_curve.empty:
        return {}
    equity = pd.to_numeric(equity_curve["equity"], errors="coerce").dropna()
    returns = equity.pct_change(fill_method=None).dropna()
    periods = max(len(returns), 1)
    cumulative = equity.iloc[-1] / initial_cash - 1.0
    annualized = (equity.iloc[-1] / initial_cash) ** (252 / periods) - 1.0 if equity.iloc[-1] > 0 else -1.0
    volatility = returns.std(ddof=0) * math.sqrt(252) if not returns.empty else float("nan")
    sharpe = returns.mean() / returns.std(ddof=0) * math.sqrt(252) if returns.std(ddof=0) > 0 else float("nan")
    downside = returns.loc[returns < 0]
    sortino = returns.mean() / downside.std(ddof=0) * math.sqrt(252) if downside.std(ddof=0) > 0 else float("nan")
    drawdown = max_drawdown(equity)
    calmar = annualized / abs(drawdown) if drawdown < 0 else float("nan")
    benchmark_cumulative = None
    benchmark_annualized = None
    excess = None
    if benchmark_returns is not None and not benchmark_returns.empty:
        aligned = pd.to_numeric(benchmark_returns, errors="coerce").dropna()
        benchmark_cumulative = float((1.0 + aligned).prod() - 1.0)
        benchmark_annualized = float((1.0 + benchmark_cumulative) ** (252 / max(len(aligned), 1)) - 1.0)
        excess = float(cumulative - benchmark_cumulative)
    sells = trades.loc[trades["side"] == "SELL"] if not trades.empty else pd.DataFrame()
    win_rate = float((sells["realized_pnl"] > 0).mean()) if not sells.empty else None
    average_holding_days = float(sells["holding_days"].mean()) if not sells.empty else None
    traded_value = float(trades["notional"].sum()) if not trades.empty else 0.0
    average_equity = float(equity.mean()) if not equity.empty else initial_cash
    turnover = traded_value / (2.0 * average_equity) if average_equity > 0 else float("nan")
    return {
        "cumulative_return": float(cumulative),
        "annualized_return": float(annualized),
        "annualized_volatility": float(volatility),
        "benchmark_return": benchmark_cumulative,
        "benchmark_annualized_return": benchmark_annualized,
        "excess_return": excess,
        "sharpe": float(sharpe),
        "sortino": float(sortino),
        "max_drawdown": float(drawdown),
        "calmar": float(calmar),
        "win_rate": win_rate,
        "turnover": float(turnover),
        "trade_count": int(len(trades)),
        "average_holding_days": average_holding_days,
        "ending_equity": float(equity.iloc[-1]),
    }

