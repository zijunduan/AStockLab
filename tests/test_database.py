from pathlib import Path
from uuid import uuid4

import pandas as pd

from src.data.data_manager import DataManager


def test_schema_and_upsert_are_idempotent():
    directory = Path(__file__).resolve().parents[1] / "data" / "test_artifacts"
    directory.mkdir(parents=True, exist_ok=True)
    manager = DataManager(directory / f"database_{uuid4().hex}.duckdb")
    required = ["stock_master", "daily_price", "market_snapshot", "daily_rankings", "experiments"]
    assert all(manager.table_exists(table) for table in required)

    frame = pd.DataFrame(
        [{
            "ticker": "SH600000", "code": "600000", "name": "浦发银行", "exchange": "SH",
            "board": "沪市主板", "listing_date": pd.NaT, "is_active": True,
            "trade_date": pd.Timestamp("2026-10-08").date(), "source": "test",
        }]
    )
    manager._upsert("stock_master", frame, ["ticker"])
    frame.loc[0, "name"] = "浦发银行更新"
    manager._upsert("stock_master", frame, ["ticker"])

    assert manager.row_count("stock_master") == 1
    assert manager.query("SELECT name FROM stock_master").iloc[0, 0] == "浦发银行更新"

