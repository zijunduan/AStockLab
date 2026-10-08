from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from src.utils.ui import app_context, render_terminal_header


render_terminal_header("模型实验室")
config, manager, _ = app_context()
st.markdown("### 当前模型")
st.json(
    {
        "type": config["model"]["type"],
        "train": [config["model"]["train_start"], config["model"]["train_end"]],
        "valid": [config["model"]["valid_start"], config["model"]["valid_end"]],
        "test": [config["model"]["test_start"], config["model"]["test_end"]],
        "ensemble": config["ensemble"],
    }
)
st.caption("Qlib 原始分仅用于同日横截面排序，不解释为预期收益率。训练集、验证集和测试集按时间严格分开，禁止 shuffle。")
health_path = Path(__file__).resolve().parents[1] / "models" / "model_health.json"
if health_path.exists():
    health = json.loads(health_path.read_text(encoding="utf-8"))
    st.markdown("### 模型健康")
    h1, h2, h3, h4 = st.columns(4)
    h1.metric("状态", health.get("status", "unknown"))
    h2.metric("Rank IC", f"{health.get('rank_ic_mean', 0):.4f}")
    h3.metric("Rank ICIR", f"{health.get('rank_icir', 0):.4f}")
    h4.metric("近 20 日 Rank IC", f"{health.get('recent_20_rank_ic', 0):.4f}")
    if health.get("status") == "degraded":
        st.error("模型近期预测能力下降：当前候选结论应降低置信度并复核。")
    else:
        st.success(health.get("message", "模型健康指标未触发告警"))
experiments = manager.query("SELECT * FROM experiments ORDER BY created_time DESC")
if experiments.empty:
    st.info("尚无已保存模型实验。")
else:
    st.dataframe(experiments, hide_index=True, use_container_width=True)

