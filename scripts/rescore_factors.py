from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.data_manager import DataManager
from src.models.ensemble import ensemble_scores
from src.models.factor_model import FactorModel
from src.strategy.ranking import rank_cross_section
from src.utils.config import load_config
from src.utils.paths import resolve_project_path


def main() -> int:
    config = load_config()
    version = config["project"]["strategy_version"]
    manager = DataManager(resolve_project_path(config["database"]["path"]))
    long = manager.query(
        """
        SELECT ticker, trade_date, factor_name, factor_value
        FROM factor_values
        WHERE trade_date = (SELECT max(trade_date) FROM factor_values)
          AND strategy_version = ?
        """,
        [version],
    )
    if long.empty:
        raise RuntimeError("没有可重评分的因子记录")
    wide = long.pivot_table(index=["ticker", "trade_date"], columns="factor_name", values="factor_value", aggfunc="last").reset_index()
    wide.columns.name = None
    as_of = pd.Timestamp(wide["trade_date"].max()).date()
    master = manager.query("SELECT ticker, name, industry, board, exchange FROM stock_master")
    snapshot = manager.query(
        """
        SELECT * EXCLUDE (rn, update_time, source) FROM (
          SELECT *, row_number() OVER (PARTITION BY ticker ORDER BY trade_date DESC, update_time DESC) rn
          FROM market_snapshot WHERE trade_date <= ?
        ) WHERE rn = 1
        """,
        [as_of],
    ).drop(columns=["trade_date", "name"], errors="ignore")
    financials = manager.query(
        """
        SELECT * EXCLUDE (rn, trade_date, update_time, source) FROM (
          SELECT *, row_number() OVER (PARTITION BY ticker ORDER BY report_period DESC, announcement_date DESC, update_time DESC) rn
          FROM financial_metrics WHERE announcement_date <= ?
        ) WHERE rn = 1
        """,
        [as_of],
    )
    data = wide.merge(master, on="ticker", how="left").merge(snapshot, on="ticker", how="left")
    if not financials.empty:
        # factor_values also stores the prior run's raw financial factors.  Drop
        # those stale copies before joining the newest PIT-safe financial row;
        # otherwise pandas suffixes them to *_x/*_y and FactorModel cannot see
        # canonical names such as roe and profit_yoy on the first rescore.
        fresh_columns = [
            column for column in financials.columns
            if column != "ticker" and column in data.columns
        ]
        data = data.drop(columns=fresh_columns)
        data = data.merge(financials, on="ticker", how="left")
    factor_result = FactorModel(config["factors"]).score_cross_section(data)
    scored = factor_result.scores.loc[
        factor_result.scores["factor_score"].notna()
        & factor_result.scores["momentum_120"].notna()
    ].copy()
    model_scores = manager.query(
        """
        SELECT ticker, trade_date, raw_score AS qlib_score FROM model_scores
        WHERE trade_date = ? AND model_name = 'Alpha158_LightGBM'
        QUALIFY row_number() OVER (PARTITION BY ticker ORDER BY update_time DESC) = 1
        """,
        [as_of],
    )
    scored["trade_date"] = pd.to_datetime(scored["trade_date"])
    if not model_scores.empty:
        model_scores["trade_date"] = pd.to_datetime(model_scores["trade_date"])
        scored = scored.merge(model_scores, on=["ticker", "trade_date"], how="left")
    ranked = rank_cross_section(
        ensemble_scores(
            scored,
            factor_weight=float(config["ensemble"]["factor_weight"]),
            qlib_weight=float(config["ensemble"]["qlib_weight"]),
            missing_qlib_policy=config["ensemble"].get("missing_qlib_policy", "factor_only"),
        )
    )
    ranked["strategy_version"] = version
    ranked["source"] = "astocklab_ensemble_rescore"

    factor_rows: list[pd.DataFrame] = []
    for factor in factor_result.factor_columns:
        values = ranked[["ticker", "trade_date", factor, f"{factor}_percentile", f"{factor}_zscore"]].copy()
        values = values.rename(columns={factor: "factor_value", f"{factor}_percentile": "percentile", f"{factor}_zscore": "zscore"})
        values["factor_name"] = factor
        values["strategy_version"] = version
        values["source"] = "astocklab_factor_rescore"
        factor_rows.append(values)
    manager._upsert("factor_values", pd.concat(factor_rows, ignore_index=True), ["ticker", "trade_date", "factor_name", "strategy_version"])

    ranking_columns = [
        "ticker", "trade_date", "rank", "percentile", "final_score", "factor_score", "qlib_score",
        "quality_score", "value_score", "growth_score", "momentum_score", "trend_score", "risk_score", "liquidity_score",
        "strategy_version", "factor_explanation", "source",
    ]
    persisted = ranked[[column for column in ranking_columns if column in ranked]].rename(columns={"factor_explanation": "explanation_json"})
    for column in ["qlib_score", "quality_score", "value_score", "growth_score", "momentum_score", "trend_score", "risk_score", "liquidity_score"]:
        if column not in persisted:
            persisted[column] = np.nan
    with manager._write_lock, manager.connection() as connection:
        connection.execute("DELETE FROM daily_rankings WHERE trade_date = ? AND strategy_version = ?", [as_of, version])
    manager._upsert("daily_rankings", persisted, ["ticker", "trade_date", "strategy_version"])
    output = resolve_project_path(config["database"]["parquet_dir"]) / f"rankings_{as_of}.parquet"
    ranked.to_parquet(output, index=False)
    print(
        json.dumps(
            {
                "status": "success", "as_of": str(as_of), "ranked_count": len(ranked),
                "financial_coverage": float(ranked["roe"].notna().mean()) if "roe" in ranked else 0.0,
                "output": str(output),
                "top20": ranked[["rank", "ticker", "name", "final_score", "factor_score", "qlib_score"]].head(20).to_dict("records"),
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

