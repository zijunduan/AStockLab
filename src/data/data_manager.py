from __future__ import annotations

import json
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

import duckdb
import pandas as pd

from src.data.akshare_client import AKShareClient, FetchResult
from src.data.validators import (
    DataQualityReport,
    validate_daily_price,
    validate_financial_point_in_time,
    validate_market_snapshot,
    validate_stock_master,
)
from src.utils.dates import now_shanghai
from src.utils.logger import get_logger


SCHEMA_SQL = r"""
CREATE TABLE IF NOT EXISTS stock_master (
    ticker VARCHAR PRIMARY KEY,
    code VARCHAR,
    name VARCHAR,
    exchange VARCHAR,
    board VARCHAR,
    industry VARCHAR,
    listing_date DATE,
    is_active BOOLEAN,
    trade_date DATE,
    update_time TIMESTAMP,
    source VARCHAR
);
CREATE TABLE IF NOT EXISTS daily_price (
    ticker VARCHAR,
    trade_date DATE,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE,
    volume DOUBLE,
    amount DOUBLE,
    turnover_rate DOUBLE,
    factor DOUBLE,
    pct_change DOUBLE,
    amplitude DOUBLE,
    price_change DOUBLE,
    adjustment VARCHAR,
    update_time TIMESTAMP,
    source VARCHAR,
    PRIMARY KEY (ticker, trade_date)
);
CREATE TABLE IF NOT EXISTS market_snapshot (
    ticker VARCHAR,
    trade_date DATE,
    name VARCHAR,
    last_price DOUBLE,
    pct_change DOUBLE,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    prev_close DOUBLE,
    volume DOUBLE,
    amount DOUBLE,
    turnover_rate DOUBLE,
    pe_ttm DOUBLE,
    pb DOUBLE,
    market_cap DOUBLE,
    float_market_cap DOUBLE,
    volume_ratio DOUBLE,
    update_time TIMESTAMP,
    source VARCHAR,
    PRIMARY KEY (ticker, trade_date)
);
CREATE TABLE IF NOT EXISTS financial_metrics (
    ticker VARCHAR,
    trade_date DATE,
    report_period DATE,
    announcement_date DATE,
    roe DOUBLE,
    roa DOUBLE,
    roic DOUBLE,
    gross_margin DOUBLE,
    net_margin DOUBLE,
    ocf_to_profit DOUBLE,
    debt_ratio DOUBLE,
    interest_coverage DOUBLE,
    revenue_yoy DOUBLE,
    profit_yoy DOUBLE,
    eps_growth DOUBLE,
    revenue_cagr_3y DOUBLE,
    update_time TIMESTAMP,
    source VARCHAR,
    PRIMARY KEY (ticker, report_period, announcement_date)
);
CREATE TABLE IF NOT EXISTS valuation_metrics (
    ticker VARCHAR,
    trade_date DATE,
    pe_ttm DOUBLE,
    pb DOUBLE,
    ps DOUBLE,
    dividend_yield DOUBLE,
    fcf_yield DOUBLE,
    market_cap DOUBLE,
    update_time TIMESTAMP,
    source VARCHAR,
    PRIMARY KEY (ticker, trade_date)
);
CREATE TABLE IF NOT EXISTS industry_info (
    ticker VARCHAR,
    trade_date DATE,
    industry_code VARCHAR,
    industry_name VARCHAR,
    classification VARCHAR,
    update_time TIMESTAMP,
    source VARCHAR,
    PRIMARY KEY (ticker, trade_date, classification)
);
CREATE TABLE IF NOT EXISTS factor_values (
    ticker VARCHAR,
    trade_date DATE,
    factor_name VARCHAR,
    factor_value DOUBLE,
    percentile DOUBLE,
    zscore DOUBLE,
    strategy_version VARCHAR,
    update_time TIMESTAMP,
    source VARCHAR,
    PRIMARY KEY (ticker, trade_date, factor_name, strategy_version)
);
CREATE TABLE IF NOT EXISTS model_scores (
    ticker VARCHAR,
    trade_date DATE,
    model_name VARCHAR,
    raw_score DOUBLE,
    percentile DOUBLE,
    model_version VARCHAR,
    update_time TIMESTAMP,
    source VARCHAR,
    PRIMARY KEY (ticker, trade_date, model_name, model_version)
);
CREATE TABLE IF NOT EXISTS daily_rankings (
    ticker VARCHAR,
    trade_date DATE,
    rank INTEGER,
    percentile DOUBLE,
    final_score DOUBLE,
    factor_score DOUBLE,
    qlib_score DOUBLE,
    quality_score DOUBLE,
    value_score DOUBLE,
    growth_score DOUBLE,
    momentum_score DOUBLE,
    trend_score DOUBLE,
    risk_score DOUBLE,
    liquidity_score DOUBLE,
    strategy_version VARCHAR,
    explanation_json VARCHAR,
    update_time TIMESTAMP,
    source VARCHAR,
    PRIMARY KEY (ticker, trade_date, strategy_version)
);
CREATE TABLE IF NOT EXISTS portfolio (
    position_id VARCHAR PRIMARY KEY,
    ticker VARCHAR,
    buy_date DATE,
    cost DOUBLE,
    quantity DOUBLE,
    buy_rank INTEGER,
    status VARCHAR,
    notes VARCHAR,
    created_time TIMESTAMP,
    update_time TIMESTAMP,
    source VARCHAR
);
CREATE TABLE IF NOT EXISTS watchlist (
    ticker VARCHAR PRIMARY KEY,
    added_date DATE,
    notes VARCHAR,
    update_time TIMESTAMP,
    source VARCHAR
);
CREATE TABLE IF NOT EXISTS alerts (
    alert_id VARCHAR PRIMARY KEY,
    ticker VARCHAR,
    trade_date DATE,
    alert_type VARCHAR,
    severity VARCHAR,
    status VARCHAR,
    title VARCHAR,
    reason VARCHAR,
    details_json VARCHAR,
    created_time TIMESTAMP,
    update_time TIMESTAMP,
    source VARCHAR
);
CREATE TABLE IF NOT EXISTS backtest_results (
    backtest_id VARCHAR PRIMARY KEY,
    strategy_version VARCHAR,
    start_date DATE,
    end_date DATE,
    config_json VARCHAR,
    metrics_json VARCHAR,
    equity_curve_path VARCHAR,
    trades_path VARCHAR,
    created_time TIMESTAMP,
    update_time TIMESTAMP,
    source VARCHAR
);
CREATE TABLE IF NOT EXISTS experiments (
    experiment_id VARCHAR PRIMARY KEY,
    strategy_version VARCHAR,
    experiment_type VARCHAR,
    status VARCHAR,
    config_json VARCHAR,
    results_json VARCHAR,
    notes VARCHAR,
    git_commit VARCHAR,
    created_time TIMESTAMP,
    update_time TIMESTAMP,
    source VARCHAR
);
CREATE TABLE IF NOT EXISTS data_quality_reports (
    report_id VARCHAR PRIMARY KEY,
    dataset VARCHAR,
    trade_date DATE,
    status VARCHAR,
    row_count BIGINT,
    report_json VARCHAR,
    created_time TIMESTAMP,
    update_time TIMESTAMP,
    source VARCHAR
);
"""


class DataManager:
    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.RLock()
        self.log = get_logger("data")
        self.initialize_database()

    @contextmanager
    def connection(self, read_only: bool = False) -> Iterator[duckdb.DuckDBPyConnection]:
        connection = duckdb.connect(str(self.database_path), read_only=read_only)
        try:
            yield connection
        finally:
            connection.close()

    def initialize_database(self) -> None:
        with self._write_lock, self.connection() as connection:
            connection.execute(SCHEMA_SQL)
        self.log.info("DuckDB 初始化完成 path={}", self.database_path)

    def table_exists(self, table: str) -> bool:
        with self.connection(read_only=True) as connection:
            return bool(connection.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [table]).fetchone()[0])

    def row_count(self, table: str) -> int:
        if not table.replace("_", "").isalnum():
            raise ValueError(f"非法表名: {table}")
        with self.connection(read_only=True) as connection:
            return int(connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0])

    def query(self, sql: str, parameters: list | tuple | None = None) -> pd.DataFrame:
        with self.connection(read_only=True) as connection:
            return connection.execute(sql, parameters or []).fetchdf()

    def _upsert(self, table: str, frame: pd.DataFrame, keys: list[str]) -> int:
        if frame.empty:
            return 0
        data = frame.copy()
        if "update_time" not in data:
            data["update_time"] = now_shanghai().replace(tzinfo=None)
        relation_name = f"incoming_{uuid.uuid4().hex}"
        key_condition = " AND ".join(f't."{key}" = s."{key}"' for key in keys)
        with self._write_lock, self.connection() as connection:
            connection.register(relation_name, data)
            try:
                connection.begin()
                connection.execute(f'DELETE FROM "{table}" AS t USING "{relation_name}" AS s WHERE {key_condition}')
                connection.execute(f'INSERT INTO "{table}" BY NAME SELECT * FROM "{relation_name}"')
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.unregister(relation_name)
        self.log.info("upsert table={} rows={}", table, len(data))
        return len(data)

    def save_quality_report(self, report: DataQualityReport) -> str:
        report_id = uuid.uuid4().hex
        now = now_shanghai().replace(tzinfo=None)
        payload = pd.DataFrame(
            [{
                "report_id": report_id,
                "dataset": report.dataset,
                "trade_date": pd.Timestamp.now(tz="Asia/Shanghai").date(),
                "status": report.status,
                "row_count": report.row_count,
                "report_json": json.dumps(report.to_dict(), ensure_ascii=False, default=str),
                "created_time": now,
                "update_time": now,
                "source": "astocklab",
            }]
        )
        self._upsert("data_quality_reports", payload, ["report_id"])
        return report_id

    def update_stock_master(self, client: AKShareClient, *, force_refresh: bool = False) -> tuple[FetchResult, DataQualityReport]:
        result = client.stock_master(force_refresh=force_refresh)
        frame = result.frame.copy()
        # The real-time stock-list endpoint often omits industry/listing date.
        # Preserve those slowly changing fields learned from financial batches
        # instead of erasing them during a routine master refresh.
        existing = self.query("SELECT ticker, industry, listing_date FROM stock_master")
        if not existing.empty:
            frame = frame.merge(existing, on="ticker", how="left", suffixes=("", "_existing"))
            for column in ("industry", "listing_date"):
                fallback = f"{column}_existing"
                if fallback not in frame.columns:
                    continue
                if column in frame.columns:
                    frame[column] = frame[column].where(frame[column].notna(), frame[fallback])
                else:
                    frame[column] = frame[fallback]
                frame = frame.drop(columns=[fallback])
        frame["trade_date"] = pd.Timestamp.now(tz="Asia/Shanghai").date()
        report = validate_stock_master(frame)
        if report.status == "error":
            raise ValueError(f"股票列表质量检查失败: {report.to_dict()}")
        self._upsert("stock_master", frame, ["ticker"])
        self.save_quality_report(report)
        return result, report

    def update_market_snapshot(self, client: AKShareClient, *, force_refresh: bool = False) -> tuple[FetchResult, DataQualityReport]:
        result = client.market_snapshot(force_refresh=force_refresh)
        frame = result.frame.copy()
        report = validate_market_snapshot(frame)
        self._upsert("market_snapshot", frame, ["ticker", "trade_date"])
        self.save_quality_report(report)
        valuations = frame[["ticker", "trade_date", "pe_ttm", "pb", "market_cap", "source"]].copy()
        valuations["ps"] = pd.NA
        valuations["dividend_yield"] = pd.NA
        valuations["fcf_yield"] = pd.NA
        self._upsert("valuation_metrics", valuations, ["ticker", "trade_date"])
        return result, report

    def upsert_daily_prices(self, frame: pd.DataFrame) -> DataQualityReport:
        report = validate_daily_price(frame)
        if report.status == "error":
            raise ValueError(f"日线行情质量检查失败: {report.to_dict()}")
        self._upsert("daily_price", frame, ["ticker", "trade_date"])
        self.save_quality_report(report)
        return report

    def update_financial_report(
        self, client: AKShareClient, report_period: str, *, force_refresh: bool = False
    ) -> tuple[FetchResult, DataQualityReport]:
        result = client.financial_report(report_period, force_refresh=force_refresh)
        source = result.frame.copy()
        active_tickers = set(self.query("SELECT ticker FROM stock_master WHERE is_active = true")["ticker"])
        source = source.loc[source["ticker"].isin(active_tickers)].copy()
        report = validate_financial_point_in_time(source)
        schema_columns = [
            "ticker", "trade_date", "report_period", "announcement_date", "roe", "gross_margin",
            "revenue_yoy", "profit_yoy", "source",
        ]
        frame = source[[column for column in schema_columns if column in source]].copy()
        self._upsert("financial_metrics", frame, ["ticker", "report_period", "announcement_date"])
        industry = source.loc[source["industry"].notna(), ["ticker", "trade_date", "industry", "source"]].copy()
        if not industry.empty:
            industry = industry.rename(columns={"industry": "industry_name"})
            industry["industry_code"] = pd.NA
            industry["classification"] = "eastmoney_report"
            self._upsert("industry_info", industry, ["ticker", "trade_date", "classification"])
            latest_names = industry.sort_values("trade_date").drop_duplicates("ticker", keep="last")
            with self._write_lock, self.connection() as connection:
                relation = "latest_industry_update"
                connection.register(relation, latest_names[["ticker", "industry_name"]])
                try:
                    connection.execute(
                        f"UPDATE stock_master AS m SET industry = i.industry_name FROM {relation} AS i WHERE m.ticker = i.ticker"
                    )
                finally:
                    connection.unregister(relation)
        self.save_quality_report(report)
        return result, report

    def latest_snapshot(self) -> pd.DataFrame:
        return self.query(
            """
            SELECT * EXCLUDE (rn) FROM (
                SELECT *, row_number() OVER (PARTITION BY ticker ORDER BY trade_date DESC, update_time DESC) AS rn
                FROM market_snapshot
            ) WHERE rn = 1
            ORDER BY ticker
            """
        )

    def data_health_summary(self) -> pd.DataFrame:
        return self.query(
            """
            SELECT dataset, status, row_count, trade_date, created_time
            FROM (
                SELECT *, row_number() OVER (PARTITION BY dataset ORDER BY created_time DESC) AS rn
                FROM data_quality_reports
            ) WHERE rn = 1
            ORDER BY dataset
            """
        )

