from __future__ import annotations

import streamlit as st

from src.utils.ui import app_context, render_terminal_header, run_project_script


render_terminal_header("数据管理")
_, manager, _ = app_context()

c1, c2, c3 = st.columns(3)
if c1.button("检查本地数据健康", use_container_width=True):
    with st.spinner("检查中…"):
        result = run_project_script("health_check.py", timeout=180)
    (st.success if result["returncode"] == 0 else st.error)(result["stdout"] or result["stderr"])
if c2.button("更新市场数据", use_container_width=True):
    with st.spinner("正在更新 AKShare 批量数据…"):
        result = run_project_script("update_data.py", timeout=900)
    (st.success if result["returncode"] == 0 else st.error)(result["stdout"] or result["stderr"])
if c3.button("更新数据并运行今日分析", type="primary", use_container_width=True):
    with st.spinner("更新数据、因子、Qlib、持仓、模型健康并生成日报；首次运行可能需要较长时间…"):
        pipeline = run_project_script("run_today_pipeline.py", timeout=14400)
    if pipeline["returncode"] == 0:
        st.success("今日分析流水线完成（请查看各步骤状态）")
        st.code(pipeline["stdout"][-16000:])
        st.cache_resource.clear()
    else:
        st.error("流水线未能完成；成功步骤未回滚。")
        st.code((pipeline["stdout"] + "\n" + pipeline["stderr"])[-16000:])

st.markdown("### Data Health")
health = manager.data_health_summary()
if health.empty:
    st.info("暂无数据质量报告。")
else:
    st.dataframe(health, hide_index=True, use_container_width=True)

counts = manager.query(
    """
    SELECT 'stock_master' table_name, count(*) rows FROM stock_master UNION ALL
    SELECT 'market_snapshot', count(*) FROM market_snapshot UNION ALL
    SELECT 'daily_price', count(*) FROM daily_price UNION ALL
    SELECT 'factor_values', count(*) FROM factor_values UNION ALL
    SELECT 'daily_rankings', count(*) FROM daily_rankings UNION ALL
    SELECT 'portfolio', count(*) FROM portfolio UNION ALL
    SELECT 'alerts', count(*) FROM alerts UNION ALL
    SELECT 'experiments', count(*) FROM experiments
    """
)
st.markdown("### 本地表行数")
st.dataframe(counts, hide_index=True, use_container_width=True)

