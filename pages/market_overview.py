from __future__ import annotations

import pandas as pd
import streamlit as st

from src.utils.ui import app_context, render_terminal_header


render_terminal_header("市场总览")
config, manager, _ = app_context()
snapshot = manager.latest_snapshot()

if snapshot.empty:
    st.info("尚无市场快照。请前往“数据管理”执行更新。")
    st.stop()

valid = snapshot.loc[pd.to_numeric(snapshot["last_price"], errors="coerce").gt(0)].copy()
pct = pd.to_numeric(valid["pct_change"], errors="coerce")
up_count = int((pct > 0).sum())
down_count = int((pct < 0).sum())
flat_count = int((pct == 0).sum())
limit_up = int((pct >= 9.8).sum())
limit_down = int((pct <= -9.8).sum())
amount = pd.to_numeric(valid["amount"], errors="coerce").sum()
up_ratio = up_count / max(up_count + down_count, 1)
regime = "Bull" if up_ratio >= 0.60 else ("Bear" if up_ratio <= 0.40 else "Neutral")

cols = st.columns(6)
cols[0].metric("上涨", f"{up_count:,}")
cols[1].metric("下跌", f"{down_count:,}")
cols[2].metric("平盘", f"{flat_count:,}")
cols[3].metric("涨停近似", f"{limit_up:,}")
cols[4].metric("跌停近似", f"{limit_down:,}")
cols[5].metric("全市场成交额", f"{amount / 1e8:,.0f} 亿元")

st.markdown(f"### Market Regime：`{regime}`")
st.caption("该标签仅基于当日上涨家数占比的量化分类，不是市场预测；涨跌停数量为未按板块差异精细校正的近似值。")

left, right = st.columns([1.3, 1])
with left:
    breadth = pd.DataFrame({"状态": ["上涨", "下跌", "平盘"], "数量": [up_count, down_count, flat_count]}).set_index("状态")
    st.bar_chart(breadth, horizontal=True)
with right:
    st.markdown("#### 数据覆盖")
    st.dataframe(
        pd.DataFrame(
            {
                "项目": ["快照总数", "有效价格", "涨跌幅覆盖", "成交额覆盖", "PE 覆盖", "PB 覆盖"],
                "值": [
                    len(snapshot), len(valid), f"{snapshot['pct_change'].notna().mean():.1%}",
                    f"{snapshot['amount'].notna().mean():.1%}", f"{snapshot['pe_ttm'].notna().mean():.1%}",
                    f"{snapshot['pb'].notna().mean():.1%}",
                ],
            }
        ),
        hide_index=True,
        use_container_width=True,
    )

