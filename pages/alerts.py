from __future__ import annotations

import streamlit as st

from src.utils.ui import app_context, render_terminal_header


render_terminal_header("风险提醒")
_, manager, _ = app_context()
alerts = manager.query("SELECT * FROM alerts ORDER BY created_time DESC LIMIT 500")

if alerts.empty:
    st.info("暂无风险提醒。持仓分析流水线运行后会在这里显示模型、趋势、风险、流动性和基本面变化。")
else:
    severity = st.multiselect("级别", sorted(alerts["severity"].dropna().unique().tolist()), default=sorted(alerts["severity"].dropna().unique().tolist()))
    filtered = alerts.loc[alerts["severity"].isin(severity)] if severity else alerts.iloc[0:0]
    st.dataframe(filtered, hide_index=True, use_container_width=True)

st.markdown("🟢 正常　🟡 注意　🟠 风险上升　🔴 退出候选")
st.caption("提醒只用于辅助复核。单个指标默认不会直接把持仓切换为退出候选。")

