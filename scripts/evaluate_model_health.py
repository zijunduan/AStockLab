from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models.health import calculate_model_health


RUN_ARTIFACTS = Path(
    r"D:\Quant\qlib-source\examples\benchmarks\LightGBM\mlruns\617139966901327605\989fa225d1074f6fa6a64c1183b5a52b\artifacts"
)


def main() -> int:
    parser = argparse.ArgumentParser(description="计算 Qlib 模型 IC / Rank IC / ICIR")
    parser.add_argument("--predictions", type=Path, default=RUN_ARTIFACTS / "pred.pkl")
    parser.add_argument("--labels", type=Path, default=RUN_ARTIFACTS / "label.pkl")
    args = parser.parse_args()
    predictions = pd.read_pickle(args.predictions)
    labels = pd.read_pickle(args.labels)
    result = calculate_model_health(predictions, labels)
    output_dir = PROJECT_ROOT / "models"
    output_dir.mkdir(parents=True, exist_ok=True)
    result.daily.reset_index().to_parquet(output_dir / "model_health_daily.parquet", index=False)
    (output_dir / "model_health.json").write_text(json.dumps(result.summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result.summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

