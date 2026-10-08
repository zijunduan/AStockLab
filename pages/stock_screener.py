from __future__ import annotations

import pandas as pd
import streamlit as st

from src.utils.ui import app_context, render_terminal_header


render_terminal_header("全市场选股")
config, manager, research = app_context()
rankings = research.latest_rankings()

if rankings.empty:
    st.info("尚无排名结果。请前往“数据管理”运行今日分析。")
    st.stop()

with st.expander("筛选条件", expanded=True):
    c1, c2, c3, c4 = st.columns(4)
    top_n = c1.selectbox("显示 Top N", [10, 20, 50, 100], index=2)
    boards = ["全部"] + sorted(rankings["board"].dropna().astype(str).unique().tolist())
    board = c2.selectbox("市场/板块", boards)
    industries = ["全部"] + sorted(rankings["industry"].dropna().astype(str).unique().tolist())
    industry = c3.selectbox("行业", industries)
    min_score = c4.slider("最低综合分", 0, 100, 0)
    c5, c6, c7, c8 = st.columns(4)
    pe_range = c5.slider("PE(TTM)", -100.0, 200.0, (-100.0, 200.0))
    pb_range = c6.slider("PB", 0.0, 30.0, (0.0, 30.0))
    max_vol = c7.slider("最低风险防御分", 0, 100, 0)
    min_amount = c8.number_input("最低当日成交额（万元）", min_value=0.0, value=0.0, step=1000.0)

filtered = rankings.copy()
if board != "全部":
    filtered = filtered.loc[filtered["board"] == board]
if industry != "全部":
    filtered = filtered.loc[filtered["industry"] == industry]
filtered = filtered.loc[filtered["final_score"].fillna(-1).ge(min_score)]
if pe_range != (-100.0, 200.0):
    filtered = filtered.loc[filtered["pe_ttm"].between(*pe_range, inclusive="both")]
if pb_range != (0.0, 30.0):
    filtered = filtered.loc[filtered["pb"].between(*pb_range, inclusive="both")]
filtered = filtered.loc[filtered["risk_score"].fillna(-1).ge(max_vol)]
if min_amount > 0:
    filtered = filtered.loc[filtered["amount"].fillna(0).ge(min_amount * 10_000)]
filtered = filtered.sort_values("rank").head(top_n)

st.markdown(f"#### 候选结果 · {len(filtered)} 只")
display_columns = {
    "rank": "排名", "ticker": "代码", "name": "名称", "industry": "行业", "last_price": "最新价",
    "pct_change": "涨跌幅%", "final_score": "综合分", "qlib_score": "Qlib原始分", "factor_score": "多因子",
    "quality_score": "质量", "value_score": "估值", "growth_score": "成长", "momentum_score": "动量",
    "trend_score": "趋势", "risk_score": "风险防御", "liquidity_score": "流动性",
}
shown = filtered[[column for column in display_columns if column in filtered]].rename(columns=display_columns)
event = st.dataframe(
    shown,
    hide_index=True,
    use_container_width=True,
    selection_mode="single-row",
    on_select="rerun",
    column_config={
        name: st.column_config.NumberColumn(name, format="%.2f")
        for name in ["最新价", "涨跌幅%", "综合分", "Qlib原始分", "多因子", "质量", "估值", "成长", "动量", "趋势", "风险防御", "流动性"]
        if name in shown
    },
)
if event.selection.rows:
    selected = filtered.iloc[event.selection.rows[0]]["ticker"]
    st.session_state["selected_ticker"] = selected
    if st.button(f"打开 {selected} 个股分析", type="primary"):
        st.switch_page("pages/stock_detail.py")

st.warning("列表是研究候选排序，不是买入建议。当前因子权重是策略参数，应使用回测与样本外结果验证。")

