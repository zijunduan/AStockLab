from __future__ import annotations

import pickle
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import joblib
import pandas as pd

from src.data.qlib_client import QlibDataProvider
from src.data.universe import normalize_ticker
from src.utils.logger import get_logger


@dataclass
class QlibModelBundle:
    model: Any
    model_name: str
    model_version: str
    trained_at: str
    training_config: dict[str, Any]
    provenance: str


class QlibLightGBMModel:
    def __init__(self, provider: QlibDataProvider, artifact_path: str | Path):
        self.provider = provider
        self.artifact_path = Path(artifact_path)
        self.log = get_logger("model")

    def exists(self) -> bool:
        return self.artifact_path.exists()

    def load(self) -> QlibModelBundle:
        if not self.artifact_path.exists():
            raise FileNotFoundError(f"Qlib 模型不存在: {self.artifact_path}")
        bundle = joblib.load(self.artifact_path)
        if not isinstance(bundle, QlibModelBundle):
            raise TypeError(f"模型文件格式无效: {self.artifact_path}")
        return bundle

    def import_trusted_qlib_artifact(
        self,
        source_path: str | Path,
        *,
        model_version: str,
        training_config: dict[str, Any] | None = None,
    ) -> QlibModelBundle:
        """Import a local Qlib recorder model produced by this user's environment."""
        source = Path(source_path).resolve()
        if not source.exists():
            raise FileNotFoundError(source)
        with source.open("rb") as handle:
            model = pickle.load(handle)
        if model.__class__.__name__ != "LGBModel":
            raise TypeError(f"仅支持 Qlib LGBModel，实际为 {model.__class__.__name__}")
        bundle = QlibModelBundle(
            model=model,
            model_name="Alpha158_LightGBM",
            model_version=model_version,
            trained_at=datetime.fromtimestamp(source.stat().st_mtime).astimezone().isoformat(),
            training_config=training_config or {},
            provenance=f"imported:{source}",
        )
        self.artifact_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(bundle, self.artifact_path)
        self.log.info("导入 Qlib LGBModel source={} target={}", source, self.artifact_path)
        return bundle

    def train(self, config: dict[str, Any], instruments: str | list[str] = "all") -> QlibModelBundle:
        """Train Alpha158 + LightGBM with strict time segments and no shuffle."""
        self.provider.initialize()
        from qlib.contrib.data.handler import Alpha158
        from qlib.contrib.model.gbdt import LGBModel
        from qlib.data.dataset import DatasetH

        model_config = dict(config["parameters"])
        model = LGBModel(**model_config)
        handler = Alpha158(
            instruments=instruments,
            start_time=config["train_start"],
            end_time=config["test_end"],
            fit_start_time=config["train_start"],
            fit_end_time=config["train_end"],
            label=([config["label"]], ["LABEL0"]),
        )
        dataset = DatasetH(
            handler=handler,
            segments={
                "train": (config["train_start"], config["train_end"]),
                "valid": (config["valid_start"], config["valid_end"]),
                "test": (config["test_start"], config["test_end"]),
            },
        )
        # LGBModel.fit reads only train/valid. The test segment is never passed to fit.
        model.fit(dataset)
        bundle = QlibModelBundle(
            model=model,
            model_name="Alpha158_LightGBM",
            model_version=config.get("model_version", "unversioned"),
            trained_at=datetime.now().astimezone().isoformat(),
            training_config=config,
            provenance="trained_by_astocklab",
        )
        self.artifact_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(bundle, self.artifact_path)
        self.log.info("Qlib 模型训练并保存 target={}", self.artifact_path)
        return bundle

    def predict_latest(
        self,
        instruments: Iterable[str],
        *,
        as_of: str | None = None,
        history_days: int = 100,
    ) -> pd.DataFrame:
        """Score the latest feature row; raw score is not interpreted as a return."""
        bundle = self.load()
        self.provider.initialize()
        from qlib.contrib.data.handler import Alpha158
        from qlib.data.dataset import DatasetH

        calendar = self.provider.calendar(end_time=as_of)
        if len(calendar) == 0:
            raise RuntimeError("Qlib 交易日历为空")
        end = calendar[-1]
        start = calendar[-min(history_days, len(calendar))]
        tickers = sorted({normalize_ticker(ticker) for ticker in instruments})
        handler = Alpha158(
            instruments=tickers,
            start_time=str(start.date()),
            end_time=str(end.date()),
            fit_start_time=str(start.date()),
            fit_end_time=str(end.date()),
        )
        dataset = DatasetH(handler=handler, segments={"predict": (str(end.date()), str(end.date()))})
        prediction = bundle.model.predict(dataset, segment="predict")
        if isinstance(prediction, pd.DataFrame):
            score = prediction.iloc[:, 0]
        else:
            score = prediction
        output = score.rename("qlib_score").reset_index()
        output = output.rename(columns={"instrument": "ticker", "datetime": "trade_date"})
        output["ticker"] = output["ticker"].map(normalize_ticker)
        output["trade_date"] = pd.to_datetime(output["trade_date"]).dt.date
        output["qlib_rank"] = output.groupby("trade_date")["qlib_score"].rank(method="first", ascending=False).astype("Int64")
        output["qlib_percentile"] = output.groupby("trade_date")["qlib_score"].rank(method="average", pct=True)
        output["model_name"] = bundle.model_name
        output["model_version"] = bundle.model_version
        return output.sort_values(["trade_date", "qlib_rank"]).reset_index(drop=True)

