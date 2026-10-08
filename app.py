from __future__ import annotations

import streamlit as st

from src.utils.ui import app_context, render_terminal_header, run_project_script


st.set_page_config(page_title="AStockLab", page_icon="📈", layout="wide", initial_sidebar_state="expanded")

st.markdown(
    """
    <style>
      .block-container {padding-top: 1.5rem; padding-bottom: 2rem;}
      [data-testid="stMetric"] {background: rgba(40, 80, 120, 0.08); border: 1px solid rgba(120, 150, 180, .18); padding: .8rem; border-radius: .45rem;}
      .risk-note {border-left: 3px solid #d5a021; padding: .6rem .9rem; background: rgba(213,160,33,.08);}
    </style>
    """,
    unsafe_allow_html=True,
)

pages = {
    "研究终端": [
        st.Page("pages/market_overview.py", title="市场总览", icon="📊"),
        st.Page("pages/stock_screener.py", title="全市场选股", icon="🔎"),
        st.Page("pages/stock_detail.py", title="个股分析", icon="📈"),
    ],
    "组合与风险": [
        st.Page("pages/portfolio.py", title="我的持仓", icon="💼"),
        st.Page("pages/watchlist.py", title="关注列表", icon="⭐"),
        st.Page("pages/alerts.py", title="风险提醒", icon="⚠️"),
    ],
    "研究工具": [
        st.Page("pages/backtest.py", title="策略回测", icon="🧪"),
        st.Page("pages/model_lab.py", title="模型实验室", icon="🧠"),
        st.Page("pages/data_manager.py", title="数据管理", icon="🗄️"),
        st.Page("pages/settings.py", title="设置", icon="⚙️"),
    ],
}

navigation = st.navigation(pages)
navigation.run()

