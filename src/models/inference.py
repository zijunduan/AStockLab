from __future__ import annotations

import pandas as pd

from src.models.qlib_model import QlibLightGBMModel


def predict_latest(model: QlibLightGBMModel, tickers: list[str], as_of: str | None = None) -> pd.DataFrame:
    return model.predict_latest(tickers, as_of=as_of)

