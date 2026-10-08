from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config import load_config


def run_pipeline() -> None:
    subprocess.run([sys.executable, str(PROJECT_ROOT / "scripts" / "run_today_pipeline.py")], cwd=PROJECT_ROOT, check=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="AStockLab 可选盘后调度器")
    parser.add_argument("--force-enable", action="store_true", help="忽略 config 中 enabled=false")
    args = parser.parse_args()
    config = load_config()["scheduler"]
    if not config.get("enabled", False) and not args.force_enable:
        print("调度器未启用。修改 config.yaml scheduler.enabled 或使用 --force-enable。")
        return 0
    scheduler = BlockingScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(
        run_pipeline,
        "cron",
        day_of_week=config.get("weekdays", "mon-fri"),
        hour=int(config.get("hour", 18)),
        minute=int(config.get("minute", 0)),
        max_instances=1,
        coalesce=True,
    )
    print(f"盘后调度器已启动：{config.get('weekdays', 'mon-fri')} {int(config.get('hour', 18)):02d}:{int(config.get('minute', 0)):02d}")
    scheduler.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

