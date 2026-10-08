from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class ModelHealthResult:
    daily: pd.DataFrame
    summary: dict


def calculate_model_health(predictions: pd.DataFrame | pd.Series, labels: pd.DataFrame | pd.Series) -> ModelHealthResult:
    pred = predictions.iloc[:, 0] if isinstance(predictions, pd.DataFrame) else predictions
    label = labels.iloc[:, 0] if isinstance(labels, pd.DataFrame) else labels
    aligned = pd.concat([pred.rename("score"), label.rename("label")], axis=1).dropna()
    if aligned.empty:
        return ModelHealthResult(pd.DataFrame(), {"status": "insufficient_data"})
    date_level = "datetime" if "datetime" in aligned.index.names else aligned.index.names[0]
    daily_ic = aligned.groupby(level=date_level).apply(lambda x: x["score"].corr(x["label"], method="pearson"))
    daily_rank_ic = aligned.groupby(level=date_level).apply(lambda x: x["score"].corr(x["label"], method="spearman"))
    daily = pd.DataFrame({"ic": daily_ic, "rank_ic": daily_rank_ic}).dropna(how="all")
    for window in (20, 60):
        daily[f"ic_mean_{window}"] = daily["ic"].rolling(window, min_periods=max(5, window // 2)).mean()
        daily[f"rank_ic_mean_{window}"] = daily["rank_ic"].rolling(window, min_periods=max(5, window // 2)).mean()
    ic_std = daily["ic"].std(ddof=0)
    rank_std = daily["rank_ic"].std(ddof=0)
    recent_20 = daily["rank_ic"].tail(20).mean()
    long_term = daily["rank_ic"].mean()
    degraded = bool(pd.notna(recent_20) and (recent_20 < 0 or (long_term > 0 and recent_20 < long_term * 0.5)))
    summary = {
        "status": "degraded" if degraded else "healthy",
        "observations": int(len(daily)),
        "ic_mean": float(daily["ic"].mean()),
        "rank_ic_mean": float(long_term),
        "icir": None if not ic_std else float(daily["ic"].mean() / ic_std),
        "rank_icir": None if not rank_std else float(long_term / rank_std),
        "recent_20_ic": float(daily["ic"].tail(20).mean()),
        "recent_20_rank_ic": float(recent_20),
        "recent_60_ic": float(daily["ic"].tail(60).mean()),
        "recent_60_rank_ic": float(daily["rank_ic"].tail(60).mean()),
        "message": "模型近期预测能力下降" if degraded else "模型历史 IC 未触发下降阈值",
    }
    return ModelHealthResult(daily, summary)

