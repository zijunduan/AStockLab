from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.data_manager import DataManager
from src.data.qlib_client import QlibDataProvider
from src.models.qlib_model import QlibLightGBMModel
from src.models.ensemble import ensemble_scores
from src.strategy.ranking import rank_cross_section
from src.utils.config import load_config
from src.utils.paths import resolve_project_path


def main() -> int:
    parser = argparse.ArgumentParser(description="运行最新 Alpha158 LightGBM 推理")
    parser.add_argument("--as-of")
    parser.add_argument("--limit", type=int, help="仅用于冒烟测试；生产运行不设置")
    parser.add_argument("--chunk-size", type=int, default=250)
    parser.add_argument("--reuse-scores", action="store_true", help="复用已落库的同日模型分数，仅重做全市场 Ensemble")
    args = parser.parse_args()
    config = load_config()
    manager = DataManager(resolve_project_path(config["database"]["path"]))
    provider = QlibDataProvider(
        config["qlib"]["provider_uri"], config["qlib"].get("region", "cn"), config["qlib"].get("kernels", 1)
    )
    service = QlibLightGBMModel(provider, resolve_project_path(config["model"]["artifact_path"]))
    current_rankings = manager.query(
        """
        SELECT * FROM daily_rankings
        WHERE trade_date = (SELECT max(trade_date) FROM daily_rankings)
          AND strategy_version = ?
        ORDER BY ticker
        """,
        [config["project"]["strategy_version"]],
    )
    if current_rankings.empty:
        raise RuntimeError("尚无多因子排名，请先运行 run_daily_analysis.py")
    current_rankings = current_rankings.loc[current_rankings["factor_score"].notna()].copy()
    effective_as_of = args.as_of or str(current_rankings["trade_date"].max())
    tickers = current_rankings["ticker"].tolist()
    qlib_set = set(provider.instruments(config["qlib"].get("market", "all"), end_time=effective_as_of))
    tickers = [ticker for ticker in tickers if ticker in qlib_set]
    if args.limit:
        tickers = tickers[: args.limit]
    if args.reuse_scores:
        bundle = service.load()
        result = manager.query(
            """
            SELECT ticker, trade_date, raw_score AS qlib_score, model_name, model_version
            FROM model_scores WHERE trade_date = ? AND model_name = ? AND model_version = ?
            """,
            [effective_as_of, bundle.model_name, bundle.model_version],
        )
        if result.empty:
            raise RuntimeError("没有可复用的同日模型分数")
        result = result.loc[result["ticker"].isin(tickers)].copy()
    else:
        parts: list[pd.DataFrame] = []
        for start in range(0, len(tickers), args.chunk_size):
            batch = tickers[start : start + args.chunk_size]
            part = service.predict_latest(batch, as_of=effective_as_of)
            parts.append(part)
            print(f"qlib_batch={start // args.chunk_size + 1} tickers={len(batch)} rows={len(part)}", flush=True)
        result = pd.concat(parts, ignore_index=True)
    result["trade_date"] = pd.to_datetime(result["trade_date"])
    result["qlib_rank"] = result.groupby("trade_date")["qlib_score"].rank(method="first", ascending=False).astype("Int64")
    result["qlib_percentile"] = result.groupby("trade_date")["qlib_score"].rank(method="average", pct=True)
    result = result.sort_values(["trade_date", "qlib_rank"]).reset_index(drop=True)
    if not args.reuse_scores:
        persisted = result[["ticker", "trade_date", "model_name", "qlib_score", "qlib_percentile", "model_version"]].rename(
            columns={"qlib_score": "raw_score", "qlib_percentile": "percentile"}
        )
        persisted["source"] = "qlib"
        manager._upsert("model_scores", persisted, ["ticker", "trade_date", "model_name", "model_version"])

    current_rankings["trade_date"] = pd.to_datetime(current_rankings["trade_date"])
    merged = current_rankings.drop(columns=["qlib_score"], errors="ignore").merge(
        result[["ticker", "trade_date", "qlib_score"]], on=["ticker", "trade_date"], how="left"
    )
    merged = ensemble_scores(
        merged,
        factor_weight=float(config["ensemble"]["factor_weight"]),
        qlib_weight=float(config["ensemble"]["qlib_weight"]),
        missing_qlib_policy=config["ensemble"].get("missing_qlib_policy", "factor_only"),
    )
    merged = rank_cross_section(merged)
    merged["source"] = "astocklab_ensemble"
    ranking_columns = [
        "ticker", "trade_date", "rank", "percentile", "final_score", "factor_score", "qlib_score",
        "quality_score", "value_score", "growth_score", "momentum_score", "trend_score", "risk_score",
        "liquidity_score", "strategy_version", "explanation_json", "source",
    ]
    with manager._write_lock, manager.connection() as connection:
        connection.execute(
            "DELETE FROM daily_rankings WHERE trade_date = ? AND strategy_version = ?",
            [effective_as_of, config["project"]["strategy_version"]],
        )
    manager._upsert(
        "daily_rankings",
        merged[[column for column in ranking_columns if column in merged]],
        ["ticker", "trade_date", "strategy_version"],
    )
    output = resolve_project_path(config["database"]["parquet_dir"]) / f"qlib_scores_{result['trade_date'].max().date()}.parquet"
    result.to_parquet(output, index=False)
    print(json.dumps({"status": "success", "rows": len(result), "output": str(output), "top20": result.head(20).to_dict("records")}, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

