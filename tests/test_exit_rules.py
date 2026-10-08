import numpy as np
import pandas as pd

from src.strategy.exit import ExitRuleEngine, ExitState


def engine() -> ExitRuleEngine:
    return ExitRuleEngine(
        {"confirmation_days": 5, "model_exit_percentile": 0.40, "trailing_stop": 0.18},
        {"thresholds": {"volatility_20_annualized": 0.55, "max_drawdown": 0.25, "amount_drop_ratio": 0.35}},
    )


def price_frame(close=100.0, ma60=95.0, ma120=90.0, slope=0.01, volatility=0.2, drawdown=0.05):
    dates = pd.bdate_range("2026-09-01", periods=10)
    return pd.DataFrame(
        {
            "trade_date": dates, "close": close, "ma60": ma60, "ma120": ma120, "ma60_slope": slope,
            "volatility_20": volatility, "max_drawdown_120": drawdown, "amount": 1e8,
        }
    )


def test_single_risk_indicator_only_moves_to_watch():
    prices = price_frame(volatility=0.8)
    decision = engine().evaluate(pd.DataFrame(), prices)
    assert decision.state == ExitState.WATCH
    assert decision.reasons[0].code == "VOLATILITY_SPIKE"


def test_model_and_trend_persistent_break_is_exit_candidate():
    dates = pd.bdate_range("2026-09-01", periods=10)
    ranking = pd.DataFrame({"trade_date": dates, "percentile": [0.8] * 5 + [0.2] * 5})
    prices = price_frame(close=80, ma60=90, ma120=85, slope=-0.02)
    decision = engine().evaluate(ranking, prices)
    assert decision.state == ExitState.EXIT_CANDIDATE
    assert {reason.category for reason in decision.reasons}.issuperset({"model", "trend"})


def test_unannounced_financial_data_is_ignored():
    financials = pd.DataFrame(
        [
            {"report_period": "2025-12-31", "announcement_date": "2026-03-01", "roe": 0.20, "profit_yoy": 0.1, "debt_ratio": 0.3},
            {"report_period": "2026-03-31", "announcement_date": "2026-10-30", "roe": 0.01, "profit_yoy": -0.9, "debt_ratio": 0.8},
        ]
    )
    decision = engine().evaluate(pd.DataFrame(), price_frame(), financials, as_of="2026-10-08")
    assert all(reason.category != "fundamental" for reason in decision.reasons)

