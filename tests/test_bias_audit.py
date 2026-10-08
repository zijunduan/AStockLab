import pandas as pd

from src.backtest.bias_audit import audit_inputs
from src.backtest.walk_forward import expanding_year_folds


def test_bias_audit_flags_same_day_execution_and_unknown_universe():
    signals = pd.DataFrame({"trade_date": ["2025-01-01"], "ticker": ["A"]})
    prices = pd.DataFrame({"trade_date": ["2025-01-01"], "ticker": ["A"]})
    checks = audit_inputs(signals, prices, execution_delay_days=0, universe_is_point_in_time=None)
    statuses = {check.name: check.status for check in checks}
    assert statuses["look_ahead"] == "fail"
    assert statuses["survivorship"] == "warning"


def test_expanding_walk_forward_never_trains_on_prediction_year():
    folds = expanding_year_folds(2015, 2020, 2022)
    assert len(folds) == 3
    assert all(fold.train_end < fold.predict_start for fold in folds)
    assert folds[1].train_end.year == 2020

