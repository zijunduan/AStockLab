from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.qlib_client import QlibDataProvider
from src.data.data_manager import DataManager
from src.models.qlib_model import QlibLightGBMModel
from src.models.training import train_model
from src.utils.config import load_config
from src.utils.paths import resolve_project_path


DEFAULT_EXISTING = Path(
    r"D:\Quant\qlib-source\examples\benchmarks\LightGBM\mlruns\617139966901327605\989fa225d1074f6fa6a64c1183b5a52b\artifacts\params.pkl"
)


def main() -> int:
    parser = argparse.ArgumentParser(description="训练或导入 Alpha158 + LightGBM")
    parser.add_argument("--import-existing", nargs="?", const=str(DEFAULT_EXISTING), help="导入已成功运行的 Qlib recorder LGBModel")
    parser.add_argument("--market", default="all", help="新训练使用的 Qlib 股票池")
    args = parser.parse_args()
    config = load_config()
    provider = QlibDataProvider(
        config["qlib"]["provider_uri"], config["qlib"].get("region", "cn"), config["qlib"].get("kernels", 1)
    )
    service = QlibLightGBMModel(provider, resolve_project_path(config["model"]["artifact_path"]))
    if args.import_existing:
        bundle = service.import_trusted_qlib_artifact(
            args.import_existing,
            model_version=config["project"]["strategy_version"] + "-bootstrap",
            training_config={"note": "用户先前成功运行的官方 Alpha158 LightGBM 示例", "source": args.import_existing},
        )
    else:
        bundle = train_model(service, config["model"], config["project"]["strategy_version"], instruments=args.market)
    now = pd.Timestamp.now(tz="Asia/Shanghai").tz_localize(None)
    experiment = pd.DataFrame(
        [{
            "experiment_id": uuid.uuid4().hex,
            "strategy_version": bundle.model_version,
            "experiment_type": "qlib_model_import" if args.import_existing else "qlib_model_train",
            "status": "completed",
            "config_json": json.dumps(bundle.training_config, ensure_ascii=False, default=str),
            "results_json": json.dumps(
                {"artifact": str(service.artifact_path), "provenance": bundle.provenance},
                ensure_ascii=False,
                default=str,
            ),
            "notes": "严格时间切分；导入模式复用用户已完成的官方 Alpha158 + LightGBM 实验。",
            "git_commit": None,
            "created_time": now,
            "update_time": now,
            "source": "astocklab_model",
        }]
    )
    manager = DataManager(resolve_project_path(config["database"]["path"]))
    manager._upsert("experiments", experiment, ["experiment_id"])
    print(json.dumps({"status": "success", "artifact": str(service.artifact_path), "metadata": bundle.__dict__ | {"model": type(bundle.model).__name__}}, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

