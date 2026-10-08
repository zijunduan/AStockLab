from __future__ import annotations

import concurrent.futures
import importlib.metadata
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable

import pandas as pd
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from src.data.cache import ParquetCache
from src.data.universe import board_of, normalize_ticker
from src.data.validators import SchemaValidationError, require_columns
from src.utils.logger import get_logger


class DataSourceError(RuntimeError):
    pass


@dataclass(frozen=True)
class FetchResult:
    frame: pd.DataFrame
    endpoint: str
    from_cache: bool
    cache_time: str | None = None
    warning: str | None = None


class AKShareClient:
    """The only module allowed to call AKShare directly.

    Each public method validates and normalizes its schema. Fresh-cache fallback is
    automatic; stale cache is used only after all live retries fail.
    """

    def __init__(
        self,
        cache_dir: str | Path,
        *,
        timeout_seconds: int = 30,
        retries: int = 3,
        cache_ttl_seconds: int = 3600,
    ):
        import akshare as ak

        self.ak = ak
        self.version = importlib.metadata.version("akshare")
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.cache = ParquetCache(cache_dir, cache_ttl_seconds)
        self.log = get_logger("data")

    def _timed_call(self, func: Callable[..., pd.DataFrame], **kwargs: Any) -> pd.DataFrame:
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="akshare")
        future = executor.submit(func, **kwargs)
        try:
            return future.result(timeout=self.timeout_seconds)
        except concurrent.futures.TimeoutError as exc:
            future.cancel()
            raise TimeoutError(f"AKShare 接口 {func.__name__} 超过 {self.timeout_seconds}s") from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _fetch(
        self,
        endpoint: str,
        func: Callable[..., pd.DataFrame],
        *,
        params: dict[str, Any] | None = None,
        ttl_seconds: int | None = None,
        kwargs: dict[str, Any] | None = None,
    ) -> FetchResult:
        params = params or {}
        kwargs = kwargs or {}
        fresh = self.cache.get(endpoint, params, ttl_seconds=ttl_seconds)
        if fresh is not None:
            return FetchResult(fresh.frame, endpoint, True, fresh.created_at.isoformat())
        try:
            for attempt in Retrying(
                stop=stop_after_attempt(self.retries),
                wait=wait_exponential_jitter(initial=1, max=8),
                retry=retry_if_exception_type((Exception,)),
                reraise=True,
            ):
                with attempt:
                    self.log.info("调用 AKShare endpoint={} params={}", endpoint, params)
                    frame = self._timed_call(func, **kwargs)
                    if not isinstance(frame, pd.DataFrame) or frame.empty:
                        raise DataSourceError(f"AKShare {endpoint} 返回空数据")
            record = self.cache.set(endpoint, frame, params)
            return FetchResult(record.frame, endpoint, False, record.created_at.isoformat())
        except Exception as exc:
            self.log.exception("AKShare endpoint={} 失败: {}", endpoint, exc)
            stale = self.cache.get(endpoint, params, allow_stale=True)
            if stale is not None:
                warning = f"实时接口失败，使用缓存（{stale.created_at.isoformat()}）：{exc}"
                return FetchResult(stale.frame, endpoint, True, stale.created_at.isoformat(), warning)
            raise DataSourceError(f"AKShare 接口 {endpoint} 失败且无缓存: {exc}") from exc

    @staticmethod
    def _numeric(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
        for column in columns:
            if column in frame:
                frame[column] = pd.to_numeric(frame[column], errors="coerce")
        return frame

    def stock_master(self, *, force_refresh: bool = False) -> FetchResult:
        ttl = 0 if force_refresh else 86_400
        endpoints: list[tuple[str, Callable[..., pd.DataFrame]]] = []
        if hasattr(self.ak, "stock_info_a_code_name"):
            endpoints.append(("stock_info_a_code_name", self.ak.stock_info_a_code_name))
        if hasattr(self.ak, "stock_zh_a_spot_em"):
            endpoints.append(("stock_zh_a_spot_em_master_fallback", self.ak.stock_zh_a_spot_em))
        errors: list[str] = []
        for endpoint, func in endpoints:
            try:
                result = self._fetch(endpoint, func, ttl_seconds=ttl)
                raw = result.frame.copy()
                rename = {"code": "code", "name": "name", "代码": "code", "名称": "name"}
                raw = raw.rename(columns=rename)
                require_columns(raw, ["code", "name"], endpoint)
                output = raw[["code", "name"]].dropna(subset=["code"]).copy()
                output["ticker"] = output["code"].map(normalize_ticker)
                output["exchange"] = output["ticker"].str[:2]
                output["board"] = output["ticker"].map(board_of)
                output["listing_date"] = pd.NaT
                output["is_active"] = True
                output["source"] = "akshare"
                output = output[["ticker", "code", "name", "exchange", "board", "listing_date", "is_active", "source"]]
                output = output.drop_duplicates("ticker").sort_values("ticker").reset_index(drop=True)
                return FetchResult(output, endpoint, result.from_cache, result.cache_time, result.warning)
            except (DataSourceError, SchemaValidationError, ValueError) as exc:
                errors.append(f"{endpoint}: {exc}")
        raise DataSourceError("股票列表接口全部失败: " + " | ".join(errors))

    def market_snapshot(self, *, force_refresh: bool = False) -> FetchResult:
        ttl = 0 if force_refresh else 300
        endpoints: list[tuple[str, Callable[..., pd.DataFrame]]] = []
        if hasattr(self.ak, "stock_zh_a_spot_em"):
            endpoints.append(("stock_zh_a_spot_em", self.ak.stock_zh_a_spot_em))
        if hasattr(self.ak, "stock_zh_a_spot"):
            endpoints.append(("stock_zh_a_spot", self.ak.stock_zh_a_spot))
        if not force_refresh:
            # Prefer an endpoint with a valid local cache, avoiding repeated waits on a
            # provider that is known to be temporarily unreachable.
            endpoints.sort(key=lambda item: self.cache.get(item[0], {}, ttl_seconds=ttl) is None)
        errors: list[str] = []
        for endpoint, func in endpoints:
            try:
                result = self._fetch(endpoint, func, ttl_seconds=ttl)
                raw = result.frame.copy()
                if endpoint == "stock_zh_a_spot_em":
                    raw = raw.rename(
                        columns={
                            "代码": "code", "名称": "name", "最新价": "last_price", "涨跌幅": "pct_change",
                            "今开": "open", "最高": "high", "最低": "low", "昨收": "prev_close",
                            "成交量": "volume", "成交额": "amount", "换手率": "turnover_rate",
                            "市盈率-动态": "pe_ttm", "市净率": "pb", "总市值": "market_cap",
                            "流通市值": "float_market_cap", "量比": "volume_ratio",
                        }
                    )
                else:
                    raw = raw.rename(
                        columns={
                            "code": "code", "symbol": "code", "name": "name", "trade": "last_price",
                            "changepercent": "pct_change", "open": "open", "high": "high", "low": "low",
                            "settlement": "prev_close", "volume": "volume", "amount": "amount",
                            "turnoverratio": "turnover_rate", "per": "pe_ttm", "pb": "pb",
                            "mktcap": "market_cap", "nmc": "float_market_cap",
                            # AKShare 1.19.x may expose the Sina fallback with Chinese columns.
                            "代码": "code", "名称": "name", "最新价": "last_price", "涨跌幅": "pct_change",
                            "今开": "open", "最高": "high", "最低": "low", "昨收": "prev_close",
                            "成交量": "volume", "成交额": "amount",
                        }
                    )
                require_columns(raw, ["code", "name", "last_price"], endpoint)
                output = raw.copy()
                output["ticker"] = output["code"].map(normalize_ticker)
                numeric_columns = [
                    "last_price", "pct_change", "open", "high", "low", "prev_close", "volume", "amount",
                    "turnover_rate", "pe_ttm", "pb", "market_cap", "float_market_cap", "volume_ratio",
                ]
                output = self._numeric(output, numeric_columns)
                for column in numeric_columns:
                    if column not in output:
                        output[column] = pd.NA
                output["trade_date"] = pd.Timestamp.now(tz="Asia/Shanghai").date()
                output["source"] = "akshare"
                columns = ["ticker", "trade_date", "name", *numeric_columns, "source"]
                output = output[columns].drop_duplicates("ticker").reset_index(drop=True)
                return FetchResult(output, endpoint, result.from_cache, result.cache_time, result.warning)
            except (DataSourceError, SchemaValidationError, ValueError) as exc:
                errors.append(f"{endpoint}: {exc}")
        raise DataSourceError("全市场快照接口全部失败: " + " | ".join(errors))

    def daily_history(
        self,
        ticker: str,
        start_date: str | date,
        end_date: str | date,
        *,
        adjustment: str = "qfq",
        force_refresh: bool = False,
    ) -> FetchResult:
        if not hasattr(self.ak, "stock_zh_a_hist"):
            raise DataSourceError("当前 AKShare 版本没有 stock_zh_a_hist")
        normalized = normalize_ticker(ticker)
        start = pd.Timestamp(start_date).strftime("%Y%m%d")
        end = pd.Timestamp(end_date).strftime("%Y%m%d")
        params = {"ticker": normalized, "start": start, "end": end, "adjust": adjustment}
        result = self._fetch(
            "stock_zh_a_hist",
            self.ak.stock_zh_a_hist,
            params=params,
            ttl_seconds=0 if force_refresh else 86_400,
            kwargs={"symbol": normalized[2:], "period": "daily", "start_date": start, "end_date": end, "adjust": adjustment},
        )
        raw = result.frame.rename(
            columns={
                "日期": "trade_date", "股票代码": "code", "开盘": "open", "收盘": "close", "最高": "high",
                "最低": "low", "成交量": "volume", "成交额": "amount", "振幅": "amplitude",
                "涨跌幅": "pct_change", "涨跌额": "price_change", "换手率": "turnover_rate",
            }
        ).copy()
        require_columns(raw, ["trade_date", "open", "high", "low", "close", "volume"], "stock_zh_a_hist")
        raw["ticker"] = normalized
        raw["trade_date"] = pd.to_datetime(raw["trade_date"], errors="coerce").dt.date
        numeric = ["open", "high", "low", "close", "volume", "amount", "amplitude", "pct_change", "price_change", "turnover_rate"]
        raw = self._numeric(raw, numeric)
        for column in numeric:
            if column not in raw:
                raw[column] = pd.NA
        raw["adjustment"] = adjustment
        raw["source"] = "akshare"
        columns = ["ticker", "trade_date", *numeric, "adjustment", "source"]
        output = raw[columns].dropna(subset=["trade_date"]).drop_duplicates(["ticker", "trade_date"])
        return FetchResult(output.reset_index(drop=True), result.endpoint, result.from_cache, result.cache_time, result.warning)

    def financial_report(self, report_period: str | date, *, force_refresh: bool = False) -> FetchResult:
        """Batch performance report with announcement dates (no per-stock HTTP loop)."""
        if not hasattr(self.ak, "stock_yjbb_em"):
            raise DataSourceError("当前 AKShare 版本没有 stock_yjbb_em")
        period = pd.Timestamp(report_period).strftime("%Y%m%d")
        result = self._fetch(
            "stock_yjbb_em",
            self.ak.stock_yjbb_em,
            params={"date": period},
            ttl_seconds=0 if force_refresh else 7 * 86_400,
            kwargs={"date": period},
        )
        raw = result.frame.rename(
            columns={
                "股票代码": "code", "股票简称": "name", "净资产收益率": "roe", "销售毛利率": "gross_margin",
                "营业收入-同比增长": "revenue_yoy", "营业总收入-同比增长": "revenue_yoy",
                "净利润-同比增长": "profit_yoy",
                "最新公告日期": "announcement_date", "所处行业": "industry", "每股收益": "eps",
                "每股经营现金流量": "ocf_per_share", "每股净资产": "book_value_per_share",
            }
        ).copy()
        require_columns(raw, ["code", "announcement_date"], "stock_yjbb_em")
        raw["ticker"] = raw["code"].map(normalize_ticker)
        raw["report_period"] = pd.Timestamp(period).date()
        raw["announcement_date"] = pd.to_datetime(raw["announcement_date"], errors="coerce").dt.date
        for column in ["roe", "gross_margin", "revenue_yoy", "profit_yoy", "eps", "ocf_per_share", "book_value_per_share"]:
            if column not in raw:
                raw[column] = pd.NA
            raw[column] = pd.to_numeric(raw[column], errors="coerce")
        # AKShare fields are percentages; store ratios consistently.
        for column in ["roe", "gross_margin", "revenue_yoy", "profit_yoy"]:
            raw[column] = raw[column] / 100.0
        raw["trade_date"] = raw["announcement_date"]
        raw["source"] = "akshare"
        output_columns = [
            "ticker", "trade_date", "report_period", "announcement_date", "roe", "gross_margin",
            "revenue_yoy", "profit_yoy", "eps", "ocf_per_share", "book_value_per_share", "industry", "source",
        ]
        output = raw[output_columns].dropna(subset=["announcement_date"]).drop_duplicates(
            ["ticker", "report_period", "announcement_date"], keep="last"
        )
        return FetchResult(output.reset_index(drop=True), result.endpoint, result.from_cache, result.cache_time, result.warning)

    def industry_boards(self, *, force_refresh: bool = False) -> FetchResult:
        if not hasattr(self.ak, "stock_board_industry_name_em"):
            raise DataSourceError("当前 AKShare 版本没有 stock_board_industry_name_em")
        return self._fetch(
            "stock_board_industry_name_em",
            self.ak.stock_board_industry_name_em,
            ttl_seconds=0 if force_refresh else 7 * 86_400,
        )

    def industry_constituents(self, industry: str, *, force_refresh: bool = False) -> FetchResult:
        if not hasattr(self.ak, "stock_board_industry_cons_em"):
            raise DataSourceError("当前 AKShare 版本没有 stock_board_industry_cons_em")
        result = self._fetch(
            "stock_board_industry_cons_em",
            self.ak.stock_board_industry_cons_em,
            params={"industry": industry},
            ttl_seconds=0 if force_refresh else 30 * 86_400,
            kwargs={"symbol": industry},
        )
        raw = result.frame.rename(columns={"代码": "code", "名称": "name"}).copy()
        require_columns(raw, ["code"], "stock_board_industry_cons_em")
        raw["ticker"] = raw["code"].map(normalize_ticker)
        raw["industry_name"] = industry
        raw["industry_code"] = pd.NA
        raw["classification"] = "eastmoney_industry"
        raw["trade_date"] = pd.Timestamp.now(tz="Asia/Shanghai").date()
        raw["source"] = "akshare"
        output = raw[["ticker", "trade_date", "industry_code", "industry_name", "classification", "source"]].drop_duplicates("ticker")
        return FetchResult(output.reset_index(drop=True), result.endpoint, result.from_cache, result.cache_time, result.warning)

