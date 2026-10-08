from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import streamlit as st

from src.data.data_manager import DataManager
from src.data.qlib_client import QlibDataProvider
from src.services.research import StockResearchService
from src.utils.config import load_config
from src.utils.paths import PROJECT_ROOT, resolve_project_path


@st.cache_resource
def app_context() -> tuple[dict[str, Any], DataManager, StockResearchService]:
    config = load_config()
    manager = DataManager(resolve_project_path(config["database"]["path"]))
    provider = QlibDataProvider(
        config["qlib"]["provider_uri"], config["qlib"].get("region", "cn"), config["qlib"].get("kernels", 1)
    )
    return config, manager, StockResearchService(manager, provider)


def render_terminal_header(section: str) -> None:
    config, manager, _ = app_context()
    status = manager.query(
        """
        SELECT
          (SELECT max(update_time) FROM market_snapshot) AS data_time,
          (SELECT max(trade_date) FROM daily_rankings) AS model_date,
          (SELECT count(*) FROM stock_master WHERE is_active = true) AS stock_count
        """
    ).iloc[0]
    st.markdown(f"## {section}")
    col1, col2, col3 = st.columns(3)
    col1.metric("数据最后更新", str(status["data_time"])[:19] if status["data_time"] else "未更新")
    col2.metric("最新排名日", str(status["model_date"])[:10] if status["model_date"] else "未运行")
    col3.metric("股票主表", f"{int(status['stock_count']):,} 只")
    st.caption(
        f"策略版本 {config['project']['strategy_version']} · 当前评分权重是策略参数，必须通过历史回测验证；量化分类不是收益预测。"
    )


def run_project_script(script: str, arguments: list[str] | None = None, timeout: int = 1800) -> dict[str, Any]:
    command = [sys.executable, str(PROJECT_ROOT / "scripts" / script), *(arguments or [])]
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    return {"returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr, "command": command}


def parse_explanation(value: str | None) -> dict[str, Any]:
    if not value:
        return {"positive": [], "negative": [], "coverage": None}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {"positive": [], "negative": [], "coverage": None}
    except (TypeError, json.JSONDecodeError):
        return {"positive": [], "negative": ["解释字段无法解析"], "coverage": None}

