from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.backtest.bias_audit import audit_inputs, audit_to_dict
from src.backtest.engine import BacktestEngine
from src.data.data_manager import DataManager
from src.data.qlib_client import QlibDataProvider
from src.data.universe import normalize_ticker
from src.utils.config import load_config
from src.utils.dates import now_shanghai
from src.utils.paths import resolve_project_path


DEFAULT_PREDICTIONS = Path(
    r"D:\Quant\qlib-source\examples\benchmarks\LightGBM\mlruns\617139966901327605\989fa225d1074f6fa6a64c1183b5a52b\artifacts\pred.pkl"
)


def load_signals(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".pkl", ".pickle"}:
        frame = pd.read_pickle(path)
    elif path.suffix.lower() == ".parquet":
        frame = pd.read_parquet(path)
    else:
        frame = pd.read_csv(path)
    if isinstance(frame, pd.Series):
        frame = frame.rename("score").to_frame()
    if isinstance(frame.index, pd.MultiIndex):
        frame = frame.reset_index()
    frame = frame.rename(columns={"datetime": "trade_date", "instrument": "ticker", "qlib_score": "score", "final_score": "score"})
    if "score" not in frame:
        numeric = frame.select_dtypes("number").columns
        if len(numeric) != 1:
            raise ValueError("无法自动识别信号分数字段")
        frame = frame.rename(columns={numeric[0]: "score"})
    frame["ticker"] = frame["ticker"].map(normalize_ticker)
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    return frame[["trade_date", "ticker", "score"]].dropna(subset=["score"])


def git_commit() -> str | None:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=10)
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="AStockLab T+1 科学回测")
    parser.add_argument("--signals", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--rebalance", choices=["daily", "weekly", "monthly"], default="weekly")
    parser.add_argument("--commission-rate", type=float)
    parser.add_argument("--slippage-rate", type=float)
    parser.add_argument("--stamp-duty-rate", type=float)
    parser.add_argument("--note", default="Bootstrap Qlib Alpha158 LightGBM 样本外预测；T+1 开盘执行")
    args = parser.parse_args()

    config = load_config()
    signals = load_signals(args.signals)
    provider = QlibDataProvider(
        config["qlib"]["provider_uri"], config["qlib"].get("region", "cn"), config["qlib"].get("kernels", 1)
    )
    signal_start = signals["trade_date"].min()
    signal_end = signals["trade_date"].max()
    calendar = provider.calendar(start_time=str(signal_start.date()))
    future_dates = calendar[calendar > signal_end]
    price_end = future_dates[0] if len(future_dates) else signal_end
    prices = provider.daily_prices(
        sorted(signals["ticker"].unique()), str(signal_start.date()), str(price_end.date())
    ).dropna(subset=["open", "close"])
    benchmark = provider.daily_prices(
        [config["backtest"]["benchmark"]], str(signal_start.date()), str(price_end.date())
    ).dropna(subset=["close"])
    benchmark_returns = benchmark.sort_values("trade_date").set_index("trade_date")["close"].pct_change(fill_method=None)

    trading_config = dict(config["trading"])
    if args.commission_rate is not None:
        trading_config["commission_rate"] = args.commission_rate
    if args.slippage_rate is not None:
        trading_config["slippage_rate"] = args.slippage_rate
    if args.stamp_duty_rate is not None:
        trading_config["stamp_duty_rate"] = args.stamp_duty_rate
    engine = BacktestEngine(trading_config)
    result = engine.run(
        signals,
        prices,
        top_n=args.top_n,
        rebalance=args.rebalance,
        score_column="score",
        benchmark_returns=benchmark_returns,
    )
    checks = audit_inputs(signals, prices, execution_delay_days=1, universe_is_point_in_time=True)
    audit = audit_to_dict(checks)
    if any(check["status"] == "fail" for check in audit):
        raise RuntimeError(f"Bias Audit 失败: {audit}")

    backtest_id = uuid.uuid4().hex
    experiment_dir = PROJECT_ROOT / "experiments" / backtest_id
    experiment_dir.mkdir(parents=True, exist_ok=False)
    equity_path = experiment_dir / "equity_curve.parquet"
    trades_path = experiment_dir / "trades.parquet"
    result.equity_curve.to_parquet(equity_path, index=False)
    result.trades.to_parquet(trades_path, index=False)
    run_config = {
        "signals": str(args.signals), "top_n": args.top_n, "rebalance": args.rebalance,
        "trading": trading_config, "execution_assumption": result.execution_assumption,
        "price_adjustment": "Qlib normalized prices; corporate-action return continuity preserved",
        "bias_audit": audit,
    }
    (experiment_dir / "config.json").write_text(json.dumps(run_config, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (experiment_dir / "metrics.json").write_text(json.dumps(result.metrics, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    manager = DataManager(resolve_project_path(config["database"]["path"]))
    now = now_shanghai().replace(tzinfo=None)
    backtest_row = pd.DataFrame(
        [{
            "backtest_id": backtest_id, "strategy_version": config["project"]["strategy_version"],
            "start_date": signal_start.date(), "end_date": signal_end.date(),
            "config_json": json.dumps(run_config, ensure_ascii=False, default=str),
            "metrics_json": json.dumps(result.metrics, ensure_ascii=False, default=str),
            "equity_curve_path": str(equity_path), "trades_path": str(trades_path),
            "created_time": now, "update_time": now, "source": "astocklab_backtest",
        }]
    )
    manager._upsert("backtest_results", backtest_row, ["backtest_id"])
    experiment_row = pd.DataFrame(
        [{
            "experiment_id": backtest_id, "strategy_version": config["project"]["strategy_version"],
            "experiment_type": "backtest", "status": "completed",
            "config_json": json.dumps(run_config, ensure_ascii=False, default=str),
            "results_json": json.dumps(result.metrics, ensure_ascii=False, default=str),
            "notes": args.note, "git_commit": git_commit(), "created_time": now, "update_time": now,
            "source": "astocklab_backtest",
        }]
    )
    manager._upsert("experiments", experiment_row, ["experiment_id"])
    print(
        json.dumps(
            {"status": "success", "backtest_id": backtest_id, "metrics": result.metrics, "bias_audit": audit, "directory": str(experiment_dir)},
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

