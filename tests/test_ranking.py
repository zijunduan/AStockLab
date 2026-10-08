import pandas as pd

from src.models.ensemble import ensemble_scores
from src.strategy.ranking import rank_cross_section


def test_ranking_is_descending_and_percentile_is_high_for_best():
    frame = pd.DataFrame(
        {
            "ticker": ["SH600000", "SZ000001", "SZ000002"],
            "trade_date": [pd.Timestamp("2026-10-08").date()] * 3,
            "factor_score": [50.0, 90.0, 10.0],
            "qlib_score": [0.2, 0.1, -0.3],
        }
    )
    result = rank_cross_section(ensemble_scores(frame, factor_weight=0.5, qlib_weight=0.5))
    assert result.iloc[0]["ticker"] == "SZ000001"
    assert result.iloc[0]["rank"] == 1
    assert result.iloc[0]["percentile"] == 1.0


def test_factor_only_fallback_does_not_halve_score():
    frame = pd.DataFrame(
        {"ticker": ["A", "B"], "trade_date": ["2026-10-08"] * 2, "factor_score": [80.0, 20.0]}
    )
    result = ensemble_scores(frame, factor_weight=0.5, qlib_weight=0.5, missing_qlib_policy="factor_only")
    assert result["final_score"].tolist() == [80.0, 20.0]

