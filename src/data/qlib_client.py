from __future__ import annotations

import threading
from pathlib import Path
from typing import Iterable

import pandas as pd

from src.data.universe import normalize_ticker
from src.utils.logger import get_logger


class QlibDataError(RuntimeError):
    pass


class QlibDataProvider:
    _lock = threading.Lock()
    _initialized_uri: str | None = None

    def __init__(self, provider_uri: str | Path, region: str = "cn", kernels: int = 1):
        self.provider_uri = str(Path(provider_uri).resolve())
        self.region = region.lower()
        self.kernels = max(int(kernels), 1)
        self.log = get_logger("data")

    def initialize(self) -> None:
        if self.__class__._initialized_uri == self.provider_uri:
            return
        with self._lock:
            if self.__class__._initialized_uri == self.provider_uri:
                return
            try:
                import qlib
                from qlib.constant import REG_CN, REG_US

                # Qlib defaults to the Windows multiprocessing backend. Named-pipe
                # creation is unavailable in some locked-down desktop sessions, so
                # the local terminal defaults to one deterministic reader worker.
                qlib.init(
                    provider_uri=self.provider_uri,
                    region=REG_CN if self.region == "cn" else REG_US,
                    kernels=self.kernels,
                )
                self.__class__._initialized_uri = self.provider_uri
                self.log.info("Qlib 初始化成功 provider_uri={}", self.provider_uri)
            except Exception as exc:
                self.log.exception("Qlib 初始化失败: {}", exc)
                raise QlibDataError(f"Qlib 初始化失败 {self.provider_uri}: {exc}") from exc

    def calendar(self, start_time: str | None = None, end_time: str | None = None, freq: str = "day") -> pd.DatetimeIndex:
        self.initialize()
        from qlib.data import D

        try:
            values = D.calendar(start_time=start_time, end_time=end_time, freq=freq)
            return pd.DatetimeIndex(values)
        except Exception as exc:
            raise QlibDataError(f"读取 Qlib 交易日历失败: {exc}") from exc

    def features(
        self,
        instruments: Iterable[str],
        fields: Iterable[str],
        start_time: str | None = None,
        end_time: str | None = None,
        freq: str = "day",
    ) -> pd.DataFrame:
        self.initialize()
        from qlib.data import D

        tickers = [normalize_ticker(item) for item in instruments]
        try:
            return D.features(tickers, list(fields), start_time=start_time, end_time=end_time, freq=freq)
        except Exception as exc:
            raise QlibDataError(f"读取 Qlib 特征失败 instruments={len(tickers)} fields={list(fields)}: {exc}") from exc

    def instruments(
        self,
        market: str = "all",
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> list[str]:
        self.initialize()
        from qlib.data import D

        try:
            config = D.instruments(market=market)
            values = D.list_instruments(config, start_time=start_time, end_time=end_time, as_list=True)
            return sorted(normalize_ticker(value) for value in values)
        except Exception as exc:
            raise QlibDataError(f"读取 Qlib 股票池失败 market={market}: {exc}") from exc

    def daily_prices(
        self,
        instruments: Iterable[str],
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> pd.DataFrame:
        mapping = {
            "$open": "open", "$high": "high", "$low": "low", "$close": "close",
            "$volume": "volume", "$amount": "amount", "$factor": "factor", "$change": "pct_change",
        }
        frame = self.features(instruments, mapping.keys(), start_time, end_time)
        if frame.empty:
            return pd.DataFrame(columns=["ticker", "trade_date", *mapping.values(), "amount", "turnover_rate", "adjustment", "source"])
        frame = frame.rename(columns=mapping).reset_index()
        frame = frame.rename(columns={"instrument": "ticker", "datetime": "trade_date"})
        frame["ticker"] = frame["ticker"].map(normalize_ticker)
        frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.date
        frame["turnover_rate"] = pd.NA
        frame["adjustment"] = "qlib_normalized"
        frame["source"] = "qlib"
        return frame

