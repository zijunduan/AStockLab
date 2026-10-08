from __future__ import annotations

import streamlit as st

from src.utils.ui import app_context, render_terminal_header


render_terminal_header("设置")
config, _, _ = app_context()
st.info("当前页面以只读方式展示配置。修改 `config.yaml` 后重启应用生效，避免在运行中写入半完成配置。")
st.markdown("### 因子权重")
st.json(config["factors"]["weights"])
st.markdown("### Ensemble")
st.json(config["ensemble"])
st.markdown("### 退出与风险")
st.json({"strategy": config["strategy"], "risk": config["risk"]})
st.markdown("### 交易与回测假设")
st.json(config["trading"])

