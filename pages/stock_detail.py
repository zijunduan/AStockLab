from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from src.utils.ui import app_context, parse_explanation, render_terminal_header


render_terminal_header("个股分析")
config, manager, research = app_context()
universe = manager.query("SELECT ticker, name FROM stock_master WHERE is_active = true ORDER BY ticker")
if universe.empty:
    st.info("股票主表为空，请先更新数据。")
    st.stop()

labels = {f"{row.ticker} · {row.name}": row.ticker for row in universe.itertuples()}
initial = st.session_state.get("selected_ticker")
label_list = list(labels)
default_index = next((i for i, label in enumerate(label_list) if labels[label] == initial), 0)
selection = st.selectbox("股票", label_list, index=default_index)
ticker = labels[selection]
st.session_state["selected_ticker"] = ticker
summary = research.stock_summary(ticker)

if not summary.empty:
    row = summary.iloc[0]
    cols = st.columns(6)
    cols[0].metric("最新价", "—" if row["last_price"] is None else f"{row['last_price']:.2f}")
    cols[1].metric("综合排名", f"#{int(row['rank'])}" if row["rank"] is not None else "—")
    cols[2].metric("综合分", f"{row['final_score']:.2f}" if row["final_score"] is not None else "—")
    cols[3].metric("Qlib 分", f"{row['qlib_score']:.4f}" if row["qlib_score"] is not None else "未接入")
    cols[4].metric("PE(TTM)", f"{row['pe_ttm']:.2f}" if row["pe_ttm"] is not None else "—")
    cols[5].metric("PB", f"{row['pb']:.2f}" if row["pb"] is not None else "—")
    st.caption(f"行业：{row.get('industry') or '待补全'} · 板块：{row.get('board') or '—'} · 市值：{(row.get('market_cap') or 0)/1e8:,.1f} 亿元")

try:
    prices = research.price_history(ticker, 320)
except Exception as exc:
    prices = None
    st.error(f"价格历史读取失败：{exc}")

if prices is not None and not prices.empty:
    chart = go.Figure()
    chart.add_trace(
        go.Candlestick(
            x=prices["trade_date"], open=prices["open"], high=prices["high"], low=prices["low"], close=prices["close"],
            name="价格",
        )
    )
    colors = {20: "#5ea1ff", 60: "#e7a74e", 120: "#b16ae8", 250: "#46b980"}
    for window, color in colors.items():
        column = f"ma{window}"
        if column in prices:
            chart.add_trace(go.Scatter(x=prices["trade_date"], y=prices[column], name=f"MA{window}", line={"width": 1.2, "color": color}))
    chart.update_layout(height=520, xaxis_rangeslider_visible=False, margin={"l": 10, "r": 10, "t": 35, "b": 10})
    st.plotly_chart(chart, use_container_width=True)
    last = prices.iloc[-1]
    perf = st.columns(4)
    for index, window in enumerate((20, 60, 120, 250)):
        value = last.get(f"momentum_{window}")
        perf[index].metric(f"{window} 日表现", "—" if value is None else f"{value:.2%}")

if not summary.empty:
    row = summary.iloc[0]
    st.markdown("### 量化评分拆解")
    dimension_map = {
        "质量": row.get("quality_score"), "估值": row.get("value_score"), "成长": row.get("growth_score"),
        "动量": row.get("momentum_score"), "趋势": row.get("trend_score"), "风险防御": row.get("risk_score"),
        "流动性": row.get("liquidity_score"),
    }
    st.bar_chart({key: value for key, value in dimension_map.items() if value is not None})
    explanation = parse_explanation(row.get("explanation_json"))
    pos, neg = st.columns(2)
    with pos:
        st.markdown("#### 为什么排名较高")
        for reason in explanation.get("positive", []) or ["暂无达到显著阈值的正贡献"]:
            st.success(reason)
    with neg:
        st.markdown("#### 哪些因素拖累排名")
        for reason in explanation.get("negative", []) or ["暂无达到显著阈值的负贡献"]:
            st.warning(reason)
    st.caption(f"因子覆盖率：{explanation.get('coverage') if explanation.get('coverage') is not None else '未知'}。缺失财务数据时会按可用维度重归一化，并明确显示覆盖率。")

