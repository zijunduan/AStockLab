from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def now_shanghai() -> datetime:
    return datetime.now(tz=SHANGHAI_TZ)


def today_shanghai() -> date:
    return now_shanghai().date()


def as_trade_date(value: object) -> date:
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp):
        raise ValueError(f"无效交易日期: {value!r}")
    return timestamp.date()

