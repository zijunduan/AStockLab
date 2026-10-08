import pandas as pd
import pytest

from src.backtest.engine import BacktestEngine


def trading_config():
    return {
        "initial_cash": 100_000,
        "commission_rate": 0.0003,
        "min_commission": 5.0,
        "stamp_duty_rate": 0.0005,
        "slippage_rate": 0.001,
        "board_lot": 100,
        "respect_price_limits": True,
        "price_limit_main": 0.10,
        "price_limit_growth_star": 0.20,
        "price_limit_bj": 0.30,
    }


def test_close_signal_executes_at_next_open_with_costs():
    dates = pd.bdate_range("2026-01-05", periods=4)
    prices = pd.DataFrame(
        [
            {"trade_date": day, "ticker": ticker, "open": open_price, "close": close, "volume": 1_000_000}
            for day, open_price, close in zip(dates, [10.0, 11.0, 12.0, 13.0], [10.5, 11.5, 12.5, 13.5])
            for ticker in ["SH600000"]
        ]
    )
    signals = pd.DataFrame({"trade_date": dates[:3], "ticker": "SH600000", "score": [1.0, 1.0, 1.0]})
    result = BacktestEngine(trading_config()).run(signals, prices, top_n=1, rebalance="daily")

    first = result.trades.iloc[0]
    assert first["signal_date"] == dates[0]
    assert first["trade_date"] == dates[1]
    assert first["price"] == pytest.approx(11.0 * 1.001)
    assert first["commission"] >= 5.0
    assert first["stamp_duty"] == 0.0


def test_limit_up_stock_cannot_be_bought():
    dates = pd.bdate_range("2026-01-05", periods=2)
    prices = pd.DataFrame(
        {
            "trade_date": dates,
            "ticker": "SH600000",
            "open": [10.0, 11.0],
            "close": [10.0, 11.0],
            "prev_close": [9.8, 10.0],
            "volume": [1_000_000, 1_000_000],
        }
    )
    signals = pd.DataFrame({"trade_date": [dates[0]], "ticker": ["SH600000"], "score": [1.0]})
    result = BacktestEngine(trading_config()).run(signals, prices, top_n=1, rebalance="daily")
    assert result.trades.empty

