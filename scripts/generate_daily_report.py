from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.data_manager import DataManager
from src.reports.daily_report import generate_daily_report
from src.utils.config import load_config
from src.utils.paths import resolve_project_path


def main() -> int:
    config = load_config()
    manager = DataManager(resolve_project_path(config["database"]["path"]))
    output = generate_daily_report(manager, PROJECT_ROOT / "reports")
    print(json.dumps({"status": "success", "report": str(output)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

