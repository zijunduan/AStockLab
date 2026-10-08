from __future__ import annotations

import streamlit as st

from src.portfolio.watchlist import WatchlistRepository
from src.utils.ui import app_context, render_terminal_header


render_terminal_header("关注列表")
_, manager, _ = app_context()
repository = WatchlistRepository(manager)

with st.form("add_watch", clear_on_submit=True):
    c1, c2 = st.columns([1, 3])
    ticker = c1.text_input("股票代码", placeholder="SZ000001")
    notes = c2.text_input("关注理由/备注")
    if st.form_submit_button("加入关注"):
        try:
            repository.add(ticker, notes)
            st.success("已加入关注")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

items = repository.list()
if items.empty:
    st.info("关注列表为空。")
else:
    st.dataframe(items, hide_index=True, use_container_width=True)
    ticker_to_remove = st.selectbox("移除", items["ticker"].tolist())
    if st.button("从关注列表移除"):
        repository.remove(ticker_to_remove)
        st.rerun()

