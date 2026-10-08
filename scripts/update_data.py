from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.akshare_client import AKShareClient
from src.data.data_manager import DataManager
from src.utils.config import load_config
from src.utils.paths import resolve_project_path


def latest_completed_report_period(today: date | None = None) -> str:
    today = today or date.today()
    if today.month >= 11:
        return f"{today.year}0930"
    if today.month >= 9:
        return f"{today.year}0630"
    if today.month >= 5:
        return f"{today.year}0331"
    return f"{today.year - 1}1231"


def main() -> int:
    parser = argparse.ArgumentParser(description="增量更新 AStockLab 市场基础数据")
    parser.add_argument("--force", action="store_true", help="忽略有效缓存")
    parser.add_argument("--skip-snapshot", action="store_true", help="跳过全市场行情快照")
    parser.add_argument("--skip-financial", action="store_true", help="跳过最近已完成报告期的批量财务数据")
    parser.add_argument("--financial-period", help="覆盖自动报告期，例如 20260630")
    args = parser.parse_args()

    config = load_config()
    client = AKShareClient(
        resolve_project_path(config["data"]["cache_dir"]),
        timeout_seconds=config["data"]["request_timeout_seconds"],
        retries=config["data"]["request_retries"],
        cache_ttl_seconds=config["data"]["cache_ttl_seconds"],
    )
    manager = DataManager(resolve_project_path(config["database"]["path"]))
    summary: dict[str, object] = {"akshare_version": client.version, "steps": {}}

    try:
        result, report = manager.update_stock_master(client, force_refresh=args.force)
        summary["steps"]["stock_master"] = {
            "status": "success", "rows": len(result.frame), "endpoint": result.endpoint,
            "from_cache": result.from_cache, "warning": result.warning, "quality": report.to_dict(),
        }
    except Exception as exc:
        summary["steps"]["stock_master"] = {"status": "failed", "message": str(exc)}

    if not args.skip_snapshot:
        try:
            result, report = manager.update_market_snapshot(client, force_refresh=args.force)
            summary["steps"]["market_snapshot"] = {
                "status": "success", "rows": len(result.frame), "endpoint": result.endpoint,
                "from_cache": result.from_cache, "warning": result.warning, "quality": report.to_dict(),
            }
        except Exception as exc:
            summary["steps"]["market_snapshot"] = {"status": "failed", "message": str(exc)}

    if not args.skip_financial:
        period = args.financial_period or latest_completed_report_period()
        try:
            result, report = manager.update_financial_report(client, period, force_refresh=args.force)
            summary["steps"]["financial_report"] = {
                "status": "success", "report_period": period, "rows": report.row_count,
                "raw_rows": len(result.frame),
                "endpoint": result.endpoint, "from_cache": result.from_cache, "warning": result.warning,
                "quality": report.to_dict(),
            }
        except Exception as exc:
            summary["steps"]["financial_report"] = {"status": "failed", "report_period": period, "message": str(exc)}

    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    failed = [step for step in summary["steps"].values() if step["status"] == "failed"]
    return 1 if len(failed) == len(summary["steps"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())

