from types import SimpleNamespace
from pathlib import Path
from uuid import uuid4

import pandas as pd
import pytest

from src.data.akshare_client import AKShareClient, FetchResult


def _runtime_dir(name: str) -> Path:
    path = Path(__file__).resolve().parents[1] / "data" / "test_artifacts" / f"{name}_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_stock_master_normalizes_codes(monkeypatch):
    client = AKShareClient(_runtime_dir("ak_master"), retries=1)
    client.ak = SimpleNamespace(stock_info_a_code_name=lambda: pd.DataFrame())
    raw = pd.DataFrame({"code": ["600000", "000001", "920000"], "name": ["浦发银行", "平安银行", "安徽凤凰"]})
    monkeypatch.setattr(client, "_fetch", lambda *args, **kwargs: FetchResult(raw, "mock", False))

    result = client.stock_master(force_refresh=True)

    assert result.frame["ticker"].tolist() == ["BJ920000", "SH600000", "SZ000001"]
    assert set(result.frame["exchange"]) == {"BJ", "SH", "SZ"}


def test_market_snapshot_supports_chinese_fallback_schema(monkeypatch):
    client = AKShareClient(_runtime_dir("ak_snapshot"), retries=1)
    client.ak = SimpleNamespace(stock_zh_a_spot=lambda: pd.DataFrame())
    raw = pd.DataFrame(
        {
            "代码": ["600000"], "名称": ["浦发银行"], "最新价": [12.3], "涨跌幅": [1.2],
            "今开": [12.0], "最高": [12.5], "最低": [11.9], "昨收": [12.15], "成交量": [1000], "成交额": [12300],
        }
    )
    monkeypatch.setattr(client, "_fetch", lambda *args, **kwargs: FetchResult(raw, "stock_zh_a_spot", False))

    result = client.market_snapshot(force_refresh=True)

    assert result.frame.loc[0, "ticker"] == "SH600000"
    assert result.frame.loc[0, "last_price"] == pytest.approx(12.3)
