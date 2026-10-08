from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class WalkForwardFold:
    fold: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    predict_start: pd.Timestamp
    predict_end: pd.Timestamp


def expanding_year_folds(
    start_year: int,
    first_predict_year: int,
    last_predict_year: int,
) -> list[WalkForwardFold]:
    if first_predict_year <= start_year:
        raise ValueError("首个预测年必须晚于训练起始年")
    folds: list[WalkForwardFold] = []
    for index, year in enumerate(range(first_predict_year, last_predict_year + 1), start=1):
        folds.append(
            WalkForwardFold(
                fold=index,
                train_start=pd.Timestamp(f"{start_year}-01-01"),
                train_end=pd.Timestamp(f"{year - 1}-12-31"),
                predict_start=pd.Timestamp(f"{year}-01-01"),
                predict_end=pd.Timestamp(f"{year}-12-31"),
            )
        )
    return folds


def rolling_year_folds(
    train_years: int,
    first_predict_year: int,
    last_predict_year: int,
) -> list[WalkForwardFold]:
    if train_years < 1:
        raise ValueError("train_years 至少为 1")
    return [
        WalkForwardFold(
            fold=index,
            train_start=pd.Timestamp(f"{year - train_years}-01-01"),
            train_end=pd.Timestamp(f"{year - 1}-12-31"),
            predict_start=pd.Timestamp(f"{year}-01-01"),
            predict_end=pd.Timestamp(f"{year}-12-31"),
        )
        for index, year in enumerate(range(first_predict_year, last_predict_year + 1), start=1)
    ]

