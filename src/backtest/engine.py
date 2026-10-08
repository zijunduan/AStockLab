from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from src.backtest.metrics import performance_metrics


@dataclass
class Position:
    shares: int
    average_cost: float
    buy_date: pd.Timestamp


@dataclass
class BacktestResult:
    equity_curve: pd.DataFrame
    trades: pd.DataFrame
    metrics: dict[str, Any]
    execution_assumption: str = "T 日收盘形成信号，T+1 交易日开盘成交"


class BacktestEngine:
    def __init__(self, trading_config: dict[str, Any]):
        self.config = trading_config
        self.initial_cash = float(trading_config.get("initial_cash", 1_000_000))
        self.commission_rate = float(trading_config.get("commission_rate", 0.0003))
        self.min_commission = float(trading_config.get("min_commission", 5.0))
        self.stamp_duty = float(trading_config.get("stamp_duty_rate", 0.0005))
        self.slippage = float(trading_config.get("slippage_rate", 0.001))
        self.board_lot = int(trading_config.get("board_lot", 100))
        self.respect_limits = bool(trading_config.get("respect_price_limits", True))

    def _price_limit(self, ticker: str) -> float:
        digits = ticker[2:]
        if ticker.startswith("BJ"):
            return float(self.config.get("price_limit_bj", 0.30))
        if digits.startswith(("300", "301", "688")):
            return float(self.config.get("price_limit_growth_star", 0.20))
        return float(self.config.get("price_limit_main", 0.10))

    def _tradable(self, row: pd.Series, side: str) -> bool:
        price = row.get("open")
        volume = row.get("volume")
        if pd.isna(price) or price <= 0 or pd.isna(volume) or volume <= 0:
            return False
        if not self.respect_limits or pd.isna(row.get("prev_close")) or row.get("prev_close", 0) <= 0:
            return True
        ratio = price / row["prev_close"] - 1.0
        limit = self._price_limit(str(row["ticker"]))
        if side == "BUY" and ratio >= limit - 1e-6:
            return False
        if side == "SELL" and ratio <= -limit + 1e-6:
            return False
        return True

    def run(
        self,
        signals: pd.DataFrame,
        prices: pd.DataFrame,
        *,
        top_n: int = 20,
        rebalance: str = "weekly",
        score_column: str = "score",
        benchmark_returns: pd.Series | None = None,
    ) -> BacktestResult:
        required_signal = {"trade_date", "ticker", score_column}
        required_price = {"trade_date", "ticker", "open", "close", "volume"}
        if not required_signal.issubset(signals.columns):
            raise ValueError(f"信号缺少字段: {sorted(required_signal - set(signals.columns))}")
        if not required_price.issubset(prices.columns):
            raise ValueError(f"行情缺少字段: {sorted(required_price - set(prices.columns))}")
        signal_data = signals.copy()
        price_data = prices.copy()
        signal_data["trade_date"] = pd.to_datetime(signal_data["trade_date"])
        price_data["trade_date"] = pd.to_datetime(price_data["trade_date"])
        price_data = price_data.sort_values(["ticker", "trade_date"])
        if "prev_close" not in price_data:
            price_data["prev_close"] = price_data.groupby("ticker")["close"].shift(1)
        price_lookup = price_data.set_index(["trade_date", "ticker"]).sort_index()
        calendar = pd.DatetimeIndex(sorted(price_data["trade_date"].dropna().unique()))
        signal_groups = {date: group for date, group in signal_data.groupby("trade_date")}

        cash = self.initial_cash
        positions: dict[str, Position] = {}
        pending_targets: list[str] | None = None
        pending_signal_date: pd.Timestamp | None = None
        equity_rows: list[dict[str, Any]] = []
        trade_rows: list[dict[str, Any]] = []

        def row_for(day: pd.Timestamp, ticker: str) -> pd.Series | None:
            try:
                row = price_lookup.loc[(day, ticker)]
                return row.iloc[-1] if isinstance(row, pd.DataFrame) else row
            except KeyError:
                return None

        for calendar_index, day in enumerate(calendar):
            if pending_targets is not None:
                open_values = {
                    ticker: float(row["open"])
                    for ticker in set(positions).union(pending_targets)
                    if (row := row_for(day, ticker)) is not None and pd.notna(row.get("open")) and row.get("open", 0) > 0
                }
                opening_equity = cash + sum(position.shares * open_values.get(ticker, 0.0) for ticker, position in positions.items())
                target_value = opening_equity / max(len(pending_targets), 1)
                desired_shares = {
                    ticker: int(target_value / (open_values[ticker] * (1 + self.slippage)) // self.board_lot * self.board_lot)
                    for ticker in pending_targets
                    if ticker in open_values
                }
                # Sell first. Shares bought today are never considered for sale today.
                for ticker in list(positions):
                    position = positions[ticker]
                    desired = desired_shares.get(ticker, 0)
                    sell_shares = position.shares - desired
                    if sell_shares <= 0:
                        continue
                    row = row_for(day, ticker)
                    if row is None or not self._tradable(pd.Series({**row.to_dict(), "ticker": ticker}), "SELL"):
                        continue
                    raw_price = float(row["open"])
                    execution_price = raw_price * (1 - self.slippage)
                    notional = execution_price * sell_shares
                    commission = max(self.min_commission, notional * self.commission_rate)
                    tax = notional * self.stamp_duty
                    cash += notional - commission - tax
                    realized = (execution_price - position.average_cost) * sell_shares - commission - tax
                    trade_rows.append(
                        {
                            "signal_date": pending_signal_date, "trade_date": day, "ticker": ticker, "side": "SELL",
                            "shares": sell_shares, "price": execution_price, "notional": notional,
                            "commission": commission, "stamp_duty": tax, "slippage_rate": self.slippage,
                            "realized_pnl": realized, "holding_days": (day - position.buy_date).days,
                        }
                    )
                    if desired == 0:
                        del positions[ticker]
                    else:
                        position.shares = desired

                for ticker in pending_targets:
                    current = positions.get(ticker)
                    desired = desired_shares.get(ticker, 0)
                    buy_shares = desired - (current.shares if current else 0)
                    if buy_shares < self.board_lot:
                        continue
                    row = row_for(day, ticker)
                    if row is None or not self._tradable(pd.Series({**row.to_dict(), "ticker": ticker}), "BUY"):
                        continue
                    raw_price = float(row["open"])
                    execution_price = raw_price * (1 + self.slippage)
                    affordable = int(max(cash - self.min_commission, 0) / execution_price // self.board_lot * self.board_lot)
                    buy_shares = min(buy_shares, affordable)
                    if buy_shares < self.board_lot:
                        continue
                    notional = execution_price * buy_shares
                    commission = max(self.min_commission, notional * self.commission_rate)
                    if notional + commission > cash:
                        continue
                    cash -= notional + commission
                    if current:
                        total_cost = current.average_cost * current.shares + notional + commission
                        current.shares += buy_shares
                        current.average_cost = total_cost / current.shares
                    else:
                        positions[ticker] = Position(buy_shares, (notional + commission) / buy_shares, day)
                    trade_rows.append(
                        {
                            "signal_date": pending_signal_date, "trade_date": day, "ticker": ticker, "side": "BUY",
                            "shares": buy_shares, "price": execution_price, "notional": notional,
                            "commission": commission, "stamp_duty": 0.0, "slippage_rate": self.slippage,
                            "realized_pnl": np.nan, "holding_days": np.nan,
                        }
                    )
                pending_targets = None
                pending_signal_date = None

            market_value = 0.0
            for ticker, position in positions.items():
                row = row_for(day, ticker)
                if row is not None and pd.notna(row.get("close")):
                    market_value += position.shares * float(row["close"])
            equity_rows.append({"trade_date": day, "cash": cash, "market_value": market_value, "equity": cash + market_value, "positions": len(positions)})

            next_day = calendar[calendar_index + 1] if calendar_index + 1 < len(calendar) else None
            if next_day is None or day not in signal_groups:
                continue
            if rebalance == "daily":
                should_signal = True
            elif rebalance == "weekly":
                should_signal = day.isocalendar()[:2] != next_day.isocalendar()[:2]
            elif rebalance == "monthly":
                should_signal = (day.year, day.month) != (next_day.year, next_day.month)
            else:
                raise ValueError(f"未知调仓频率: {rebalance}")
            if should_signal:
                day_signals = signal_groups[day].dropna(subset=[score_column]).sort_values(score_column, ascending=False)
                pending_targets = day_signals.drop_duplicates("ticker").head(top_n)["ticker"].tolist()
                pending_signal_date = day

        equity_curve = pd.DataFrame(equity_rows)
        trades = pd.DataFrame(trade_rows)
        metrics = performance_metrics(equity_curve, trades, initial_cash=self.initial_cash, benchmark_returns=benchmark_returns)
        return BacktestResult(equity_curve, trades, metrics)

