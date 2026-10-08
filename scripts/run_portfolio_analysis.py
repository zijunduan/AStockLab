from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.data_manager import DataManager
from src.data.qlib_client import QlibDataProvider
from src.portfolio.tracker import PortfolioTracker
from src.services.research import StockResearchService
from src.utils.config import load_config
from src.utils.paths import resolve_project_path


def main() -> int:
    config = load_config()
    manager = DataManager(resolve_project_path(config["database"]["path"]))
    provider = QlibDataProvider(
        config["qlib"]["provider_uri"], config["qlib"].get("region", "cn"), config["qlib"].get("kernels", 1)
    )
    tracker = PortfolioTracker(manager, StockResearchService(manager, provider), config["strategy"], config["risk"])
    results = tracker.evaluate_all()
    print(json.dumps({"status": "success", "positions": len(results), "decisions": results.to_dict("records")}, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

