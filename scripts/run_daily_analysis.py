from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.data_manager import DataManager
from src.data.qlib_client import QlibDataProvider
from src.data.universe import apply_default_universe_filters
from src.factors.price_factors import PRICE_FACTOR_COLUMNS, latest_price_factors
from src.models.ensemble import ensemble_scores
from src.models.factor_model import FactorModel
from src.strategy.ranking import rank_cross_section
from src.utils.config import load_config
from src.utils.dates import now_shanghai
from src.utils.paths import resolve_project_path


def chunks(values: list[str], size: int):
    for start in range(0, len(values), size):
        yield values[start : start + size]


def main() -> int:
    parser = argparse.ArgumentParser(description="计算当日可解释多因子与全市场排名")
    parser.add_argument("--as-of", help="分析日，默认 Qlib 最新交易日")
    parser.add_argument("--chunk-size", type=int, default=500)
    parser.add_argument("--lookback", type=int, default=400, help="价格因子回看交易日数，至少 300")
    parser.add_argument("--persist-prices", action="store_true", help="同时把回看窗口行情写入 DuckDB")
    args = parser.parse_args()
    if args.lookback < 300:
        parser.error("--lookback 至少为 300，确保 250 日因子有足够历史")

    config = load_config()
    manager = DataManager(resolve_project_path(config["database"]["path"]))
    qlib_provider = QlibDataProvider(
        config["qlib"]["provider_uri"],
        config["qlib"].get("region", "cn"),
        config["qlib"].get("kernels", 1),
    )
    calendar = qlib_provider.calendar(end_time=args.as_of)
    if len(calendar) < args.lookback:
        raise RuntimeError(f"Qlib 日历不足 {args.lookback} 个交易日")
    end_date = calendar[-1]
    start_date = calendar[-args.lookback]

    master = manager.query("SELECT * FROM stock_master WHERE is_active = true")
    master = apply_default_universe_filters(
        master,
        min_listing_days=config["market"]["min_listing_trading_days"],
        exclude_st=config["market"]["exclude_st"],
        exclude_delisting=config["market"]["exclude_delisting"],
    )
    qlib_tickers = set(qlib_provider.instruments(config["qlib"].get("market", "all"), end_time=str(end_date.date())))
    tickers = sorted(set(master["ticker"]).intersection(qlib_tickers))
    if not tickers:
        raise RuntimeError("股票主表与 Qlib 股票池交集为空，请先运行 update_data.py")

    latest_parts: list[pd.DataFrame] = []
    errors: list[dict[str, str]] = []
    for index, batch in enumerate(chunks(tickers, args.chunk_size), start=1):
        try:
            prices = qlib_provider.daily_prices(batch, str(start_date.date()), str(end_date.date()))
            prices = prices.dropna(subset=["close"])
            if args.persist_prices and not prices.empty:
                manager.upsert_daily_prices(prices)
            latest_parts.append(latest_price_factors(prices, end_date))
            print(f"factor_batch={index} tickers={len(batch)} latest_rows={len(latest_parts[-1])}")
        except Exception as exc:
            errors.append({"batch": str(index), "first_ticker": batch[0], "message": str(exc)})
            print(f"factor_batch={index} failed={exc}", file=sys.stderr)

    if not latest_parts:
        raise RuntimeError(f"全部因子批次失败: {errors}")
    latest = pd.concat(latest_parts, ignore_index=True)
    latest["trade_date"] = pd.to_datetime(latest["trade_date"])
    freshness_days = int(config["market"].get("exclude_long_suspension_days", 20))
    freshness_cutoff = calendar[-min(freshness_days, len(calendar))]
    latest = latest.loc[latest["trade_date"].ge(freshness_cutoff)].copy()
    latest["trade_date"] = latest["trade_date"].dt.date
    latest = latest.merge(master[["ticker", "name", "industry", "board", "exchange"]], on="ticker", how="left")

    financials = manager.query(
        """
        SELECT * EXCLUDE (rn, trade_date, update_time, source) FROM (
            SELECT *, row_number() OVER (
                PARTITION BY ticker ORDER BY report_period DESC, announcement_date DESC, update_time DESC
            ) AS rn
            FROM financial_metrics
            WHERE announcement_date <= ?
        ) WHERE rn = 1
        """,
        [end_date.date()],
    )
    if not financials.empty:
        latest = latest.merge(financials, on="ticker", how="left", suffixes=("", "_financial"))

    snapshot = manager.latest_snapshot()
    if not snapshot.empty:
        snapshot_columns = [
            "ticker", "last_price", "pct_change", "pe_ttm", "pb", "market_cap", "float_market_cap",
            "turnover_rate", "amount",
        ]
        snapshot = snapshot[[column for column in snapshot_columns if column in snapshot]]
        latest = latest.merge(snapshot, on="ticker", how="left", suffixes=("", "_snapshot"))
        if "amount_snapshot" in latest:
            latest["latest_amount"] = latest["amount_snapshot"]
            min_amount = float(config["market"].get("min_average_amount_20d", 0))
            latest = latest.loc[latest["latest_amount"].isna() | latest["latest_amount"].ge(min_amount)].copy()
        if "last_price" in latest:
            latest = latest.loc[latest["last_price"].isna() | latest["last_price"].gt(0)].copy()

    factor_result = FactorModel(config["factors"]).score_cross_section(latest)
    eligible_scores = factor_result.scores.loc[
        factor_result.scores["factor_score"].notna()
        & factor_result.scores.get("history_count", pd.Series(index=factor_result.scores.index, data=0)).ge(
            int(config["market"].get("min_listing_trading_days", 120))
        )
    ].copy()
    scored = ensemble_scores(
        eligible_scores,
        factor_weight=float(config["ensemble"]["factor_weight"]),
        qlib_weight=float(config["ensemble"]["qlib_weight"]),
        missing_qlib_policy=config["ensemble"].get("missing_qlib_policy", "factor_only"),
    )
    ranked = rank_cross_section(scored)
    ranked["strategy_version"] = config["project"]["strategy_version"]
    ranked["source"] = "astocklab_factor_model"

    factor_rows: list[pd.DataFrame] = []
    for factor in factor_result.factor_columns:
        columns = ["ticker", "trade_date", factor, f"{factor}_percentile", f"{factor}_zscore"]
        available = [column for column in columns if column in ranked]
        values = ranked[available].copy()
        values = values.rename(
            columns={factor: "factor_value", f"{factor}_percentile": "percentile", f"{factor}_zscore": "zscore"}
        )
        values["factor_name"] = factor
        values["strategy_version"] = config["project"]["strategy_version"]
        values["source"] = "astocklab_factor_model"
        factor_rows.append(values)
    if factor_rows:
        manager._upsert("factor_values", pd.concat(factor_rows, ignore_index=True), ["ticker", "trade_date", "factor_name", "strategy_version"])

    ranking_columns = [
        "ticker", "trade_date", "rank", "percentile", "final_score", "factor_score",
        "quality_score", "value_score", "growth_score", "momentum_score", "trend_score", "risk_score", "liquidity_score",
        "strategy_version", "factor_explanation", "source",
    ]
    persisted = ranked[[column for column in ranking_columns if column in ranked]].copy()
    persisted = persisted.rename(columns={"factor_explanation": "explanation_json"})
    persisted["qlib_score"] = np.nan
    for column in ["quality_score", "value_score", "growth_score", "momentum_score", "trend_score", "risk_score", "liquidity_score"]:
        if column not in persisted:
            persisted[column] = np.nan
    with manager._write_lock, manager.connection() as connection:
        connection.execute(
            "DELETE FROM daily_rankings WHERE trade_date = ? AND strategy_version = ?",
            [end_date.date(), config["project"]["strategy_version"]],
        )
    manager._upsert("daily_rankings", persisted, ["ticker", "trade_date", "strategy_version"])

    parquet_path = resolve_project_path(config["database"]["parquet_dir"]) / f"rankings_{end_date.date()}.parquet"
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    ranked.to_parquet(parquet_path, index=False)
    summary = {
        "status": "success" if not errors else "partial_success",
        "as_of": str(end_date.date()),
        "universe_count": len(tickers),
        "ranked_count": len(ranked),
        "errors": errors,
        "parquet": str(parquet_path),
        "top20": ranked[["rank", "ticker", "name", "final_score", "factor_score"]].head(20).to_dict("records"),
        "completed_at": now_shanghai().isoformat(),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

