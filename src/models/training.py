from __future__ import annotations

from typing import Any

from src.models.qlib_model import QlibLightGBMModel, QlibModelBundle


def train_model(service: QlibLightGBMModel, model_config: dict[str, Any], strategy_version: str, instruments: str = "all") -> QlibModelBundle:
    config = dict(model_config)
    config["model_version"] = strategy_version
    return service.train(config, instruments=instruments)

