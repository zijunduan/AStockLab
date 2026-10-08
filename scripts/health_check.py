from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.akshare_client import AKShareClient
from src.data.data_manager import DataManager
from src.data.qlib_client import QlibDataProvider
from src.utils.config import load_config
from src.utils.paths import ensure_runtime_directories, resolve_project_path


PACKAGES = [
    "pyqlib", "lightgbm", "akshare", "streamlit", "duckdb", "pyarrow", "plotly",
    "apscheduler", "pydantic", "pyyaml", "joblib", "requests", "tenacity", "loguru", "pytest",
]


def dependency_versions() -> tuple[dict[str, str], list[str]]:
    versions: dict[str, str] = {}
    missing: list[str] = []
    for package in PACKAGES:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            missing.append(package)
    return versions, missing


def run_health_check(online: bool = False) -> dict[str, Any]:
    ensure_runtime_directories()
    config = load_config()
    checks: dict[str, Any] = {
        "checked_at": datetime.now().astimezone().isoformat(),
        "python": {"version": platform.python_version(), "executable": sys.executable},
    }
    versions, missing = dependency_versions()
    checks["dependencies"] = {"status": "healthy" if not missing else "error", "versions": versions, "missing": missing}

    qlib_provider = QlibDataProvider(
        config["qlib"]["provider_uri"],
        config["qlib"].get("region", "cn"),
        config["qlib"].get("kernels", 1),
    )
    try:
        calendar = qlib_provider.calendar()
        features = qlib_provider.features(["SH600000"], ["$open", "$close", "$volume"])
        checks["qlib"] = {
            "status": "healthy",
            "provider_uri": config["qlib"]["provider_uri"],
            "calendar_count": len(calendar),
            "calendar_first": str(calendar[0].date()),
            "calendar_last": str(calendar[-1].date()),
            "feature_rows": len(features),
            "feature_non_null_rows": int(features.dropna().shape[0]),
        }
    except Exception as exc:
        checks["qlib"] = {"status": "error", "message": str(exc)}

    database_path = resolve_project_path(config["database"]["path"])
    try:
        manager = DataManager(database_path)
        required_tables = [
            "stock_master", "daily_price", "market_snapshot", "financial_metrics", "valuation_metrics",
            "industry_info", "factor_values", "model_scores", "daily_rankings", "portfolio", "watchlist",
            "alerts", "backtest_results", "experiments",
        ]
        missing_tables = [name for name in required_tables if not manager.table_exists(name)]
        checks["database"] = {
            "status": "healthy" if not missing_tables else "error",
            "path": str(database_path),
            "missing_tables": missing_tables,
        }
    except Exception as exc:
        checks["database"] = {"status": "error", "path": str(database_path), "message": str(exc)}

    if online:
        try:
            client = AKShareClient(
                resolve_project_path(config["data"]["cache_dir"]),
                timeout_seconds=config["data"]["request_timeout_seconds"],
                retries=config["data"]["request_retries"],
                cache_ttl_seconds=config["data"]["cache_ttl_seconds"],
            )
            result = client.stock_master(force_refresh=True)
            checks["akshare"] = {
                "status": "healthy",
                "version": client.version,
                "endpoint": result.endpoint,
                "rows": len(result.frame),
                "from_cache": result.from_cache,
                "warning": result.warning,
            }
        except Exception as exc:
            checks["akshare"] = {"status": "error", "message": str(exc)}
    else:
        checks["akshare"] = {"status": "not_checked", "message": "使用 --online 执行联网检查"}

    statuses = [value.get("status") for value in checks.values() if isinstance(value, dict) and "status" in value]
    checks["overall"] = "error" if "error" in statuses else ("degraded" if "not_checked" in statuses else "healthy")
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description="AStockLab 环境与数据健康检查")
    parser.add_argument("--online", action="store_true", help="联网验证 AKShare")
    parser.add_argument("--output", type=Path, help="可选 JSON 输出路径")
    args = parser.parse_args()
    result = run_health_check(online=args.online)
    text = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    return 1 if result["overall"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())

