from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Iterable

import numpy as np
import pandas as pd


class SchemaValidationError(ValueError):
    pass


def require_columns(frame: pd.DataFrame, columns: Iterable[str], context: str) -> None:
    required = set(columns)
    missing = required.difference(frame.columns)
    if missing:
        raise SchemaValidationError(f"{context} 缺少字段: {sorted(missing)}; 实际字段: {list(frame.columns)}")


@dataclass
class DataQualityIssue:
    severity: str
    check: str
    message: str
    affected_rows: int = 0


@dataclass
class DataQualityReport:
    dataset: str
    row_count: int
    issues: list[DataQualityIssue] = field(default_factory=list)
    latest_trade_date: str | None = None
    coverage: dict[str, float] = field(default_factory=dict)

    @property
    def status(self) -> str:
        severities = {issue.severity for issue in self.issues}
        if "error" in severities:
            return "error"
        if "warning" in severities:
            return "warning"
        return "healthy"

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["status"] = self.status
        return payload


def validate_stock_master(frame: pd.DataFrame) -> DataQualityReport:
    require_columns(frame, ["ticker", "name", "exchange"], "stock_master")
    report = DataQualityReport("stock_master", len(frame))
    duplicate_count = int(frame["ticker"].duplicated().sum())
    invalid_count = int((~frame["ticker"].astype(str).str.match(r"^(SH|SZ|BJ)\d{6}$")).sum())
    if duplicate_count:
        report.issues.append(DataQualityIssue("error", "duplicate_ticker", "股票代码存在重复", duplicate_count))
    if invalid_count:
        report.issues.append(DataQualityIssue("error", "ticker_format", "股票代码格式无效", invalid_count))
    return report


def validate_daily_price(frame: pd.DataFrame) -> DataQualityReport:
    required = ["ticker", "trade_date", "open", "high", "low", "close", "volume"]
    require_columns(frame, required, "daily_price")
    report = DataQualityReport("daily_price", len(frame))
    if frame.empty:
        report.issues.append(DataQualityIssue("error", "empty", "行情数据为空"))
        return report
    duplicate_count = int(frame.duplicated(["ticker", "trade_date"]).sum())
    if duplicate_count:
        report.issues.append(DataQualityIssue("error", "duplicates", "代码和交易日重复", duplicate_count))
    numeric = frame[["open", "high", "low", "close", "volume"]].apply(pd.to_numeric, errors="coerce")
    bad_price = int(((numeric[["open", "high", "low", "close"]] <= 0).any(axis=1)).sum())
    high_low = int((numeric["high"] < numeric["low"]).sum())
    zero_volume = int((numeric["volume"] <= 0).sum())
    if bad_price:
        report.issues.append(DataQualityIssue("error", "non_positive_price", "价格小于等于零", bad_price))
    if high_low:
        report.issues.append(DataQualityIssue("error", "high_below_low", "最高价低于最低价", high_low))
    if zero_volume:
        report.issues.append(DataQualityIssue("warning", "zero_volume", "成交量为零，可能停牌", zero_volume))
    sorted_frame = frame.sort_values(["ticker", "trade_date"])
    returns = sorted_frame.groupby("ticker", sort=False)["close"].pct_change(fill_method=None)
    extreme = int((returns.abs() > 0.31).sum())
    if extreme:
        report.issues.append(DataQualityIssue("warning", "extreme_return", "存在绝对涨跌超过 31% 的记录", extreme))
    report.latest_trade_date = str(pd.to_datetime(frame["trade_date"]).max().date())
    report.coverage = {column: float(frame[column].notna().mean()) for column in required}
    return report


def validate_market_snapshot(frame: pd.DataFrame) -> DataQualityReport:
    require_columns(frame, ["ticker", "trade_date", "last_price", "volume"], "market_snapshot")
    report = DataQualityReport("market_snapshot", len(frame))
    if frame.empty:
        report.issues.append(DataQualityIssue("error", "empty", "市场快照为空"))
        return report
    duplicate_count = int(frame["ticker"].duplicated().sum())
    if duplicate_count:
        report.issues.append(DataQualityIssue("error", "duplicate_ticker", "快照股票代码重复", duplicate_count))
    price = pd.to_numeric(frame["last_price"], errors="coerce")
    volume = pd.to_numeric(frame["volume"], errors="coerce")
    unavailable = int((price.isna() | price.le(0)).sum())
    zero_volume = int((volume.fillna(0) <= 0).sum())
    if unavailable:
        report.issues.append(DataQualityIssue("warning", "unavailable_price", "价格不可用，通常为停牌或数据暂缺", unavailable))
    if zero_volume:
        report.issues.append(DataQualityIssue("warning", "zero_volume", "成交量为零，通常为停牌", zero_volume))
    report.latest_trade_date = str(pd.to_datetime(frame["trade_date"]).max().date())
    columns = [column for column in ["last_price", "pct_change", "volume", "amount"] if column in frame]
    report.coverage = {column: float(frame[column].notna().mean()) for column in columns}
    return report


def validate_financial_point_in_time(frame: pd.DataFrame) -> DataQualityReport:
    require_columns(frame, ["ticker", "report_period", "announcement_date"], "financial_metrics")
    report = DataQualityReport("financial_metrics", len(frame))
    report_period = pd.to_datetime(frame["report_period"], errors="coerce")
    announcement = pd.to_datetime(frame["announcement_date"], errors="coerce")
    missing_announcement = int(announcement.isna().sum())
    impossible = int((announcement < report_period).fillna(False).sum())
    if missing_announcement:
        report.issues.append(
            DataQualityIssue("warning", "missing_announcement_date", "公告日期缺失；回测时必须排除或标记潜在 PIT 偏差", missing_announcement)
        )
    if impossible:
        report.issues.append(DataQualityIssue("error", "announcement_before_period", "公告日期早于报告期", impossible))
    return report


def finite_or_nan(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    return values.where(np.isfinite(values), np.nan)

