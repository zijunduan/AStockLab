from __future__ import annotations

import streamlit as st

from src.portfolio.holdings import HoldingsRepository
from src.utils.ui import app_context, render_terminal_header


render_terminal_header("我的持仓")
config, manager, _ = app_context()
repository = HoldingsRepository(manager)

with st.expander("手动录入持仓", expanded=False):
    with st.form("add_holding", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns(4)
        ticker = c1.text_input("股票代码", placeholder="600000 / SH600000")
        buy_date = c2.date_input("买入日期")
        cost = c3.number_input("成本", min_value=0.0, step=0.01)
        quantity = c4.number_input("数量", min_value=0.0, step=100.0)
        notes = st.text_input("备注")
        if st.form_submit_button("保存持仓", type="primary"):
            try:
                repository.add(ticker, buy_date, cost, quantity, notes)
                st.success("持仓已保存")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

holdings = repository.list()
if holdings.empty:
    st.info("尚未录入持仓。")
else:
    display = holdings.rename(
        columns={
            "ticker": "代码", "name": "名称", "buy_date": "买入日", "cost": "成本", "quantity": "数量",
            "last_price": "现价", "pnl": "盈亏", "pnl_pct": "收益率", "holding_days": "持有天数",
            "buy_rank": "买入时排名", "current_rank": "当前排名", "rank_change": "排名变化", "status": "状态",
        }
    )
    columns = ["代码", "名称", "买入日", "成本", "数量", "现价", "盈亏", "收益率", "持有天数", "买入时排名", "当前排名", "排名变化", "状态"]
    st.dataframe(display[[column for column in columns if column in display]], hide_index=True, use_container_width=True)
    selected = st.selectbox("选择要移除的持仓", [f"{r.ticker} · {r.name or ''} · {r.position_id[:8]}" for r in holdings.itertuples()])
    if st.button("移除所选持仓"):
        index = [f"{r.ticker} · {r.name or ''} · {r.position_id[:8]}" for r in holdings.itertuples()].index(selected)
        repository.remove(holdings.iloc[index]["position_id"])
        st.success("持仓已移除")
        st.rerun()

st.caption("持仓状态是研究辅助信号，不是强制卖出指令；退出判断需要连续确认和多类证据。")

