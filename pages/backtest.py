from __future__ import annotations

import json
import pandas as pd
import streamlit as st

from src.utils.ui import app_context, render_terminal_header, run_project_script


render_terminal_header("策略回测")
config, manager, _ = app_context()
st.warning("回测必须使用 T 日收盘信号、T+1 成交，并显式计入成本、滑点、印花税、停牌与涨跌停约束。")

c1, c2, c3, c4 = st.columns(4)
universe = c1.selectbox("股票池", config["market"]["universes"])
top_n = c2.selectbox("Top N", [10, 20, 50, 100], index=1)
rebalance = c3.selectbox("调仓频率", ["daily", "weekly", "monthly"], index=1)
c4.text_input("历史信号", "Qlib 示例样本外预测", disabled=True)
c5, c6, c7 = st.columns(3)
commission = c5.number_input("佣金率", value=float(config["trading"]["commission_rate"]), format="%.5f")
slippage = c6.number_input("滑点率", value=float(config["trading"]["slippage_rate"]), format="%.5f")
stamp = c7.number_input("卖出印花税", value=float(config["trading"]["stamp_duty_rate"]), format="%.5f")

if st.button("运行回测", type="primary"):
    with st.spinner("正在运行 T+1 回测并执行 Bias Audit…"):
        result = run_project_script(
            "run_backtest.py",
            [
                "--top-n", str(top_n), "--rebalance", rebalance,
                "--commission-rate", str(commission), "--slippage-rate", str(slippage),
                "--stamp-duty-rate", str(stamp),
            ],
            timeout=3600,
        )
    if result["returncode"] == 0:
        st.success("回测完成")
        st.code(result["stdout"][-12000:])
        st.cache_resource.clear()
    else:
        st.error("回测失败")
        st.code((result["stdout"] + "\n" + result["stderr"])[-12000:])

results = manager.query("SELECT * FROM backtest_results ORDER BY created_time DESC")
st.caption("当前可直接运行的是用户已完成的 Qlib 示例样本外预测（2017–2020）。历史 Ensemble 需要完成 walk-forward 因子快照后才会开放权重调整，避免拿当前横截面倒填历史。")
if not results.empty:
    st.markdown("### 历史回测实验")
    metric_rows = []
    for row in results.itertuples():
        try:
            metrics = json.loads(row.metrics_json)
        except (TypeError, json.JSONDecodeError):
            metrics = {}
        metric_rows.append(
            {
                "backtest_id": row.backtest_id, "策略版本": row.strategy_version,
                "开始": row.start_date, "结束": row.end_date,
                "累计收益": metrics.get("cumulative_return"), "年化收益": metrics.get("annualized_return"),
                "基准收益": metrics.get("benchmark_return"), "超额收益": metrics.get("excess_return"),
                "Sharpe": metrics.get("sharpe"), "Sortino": metrics.get("sortino"),
                "最大回撤": metrics.get("max_drawdown"), "Calmar": metrics.get("calmar"),
                "胜率": metrics.get("win_rate"), "换手率": metrics.get("turnover"),
                "交易次数": metrics.get("trade_count"), "平均持仓天数": metrics.get("average_holding_days"),
            }
        )
    metrics_frame = pd.DataFrame(metric_rows)
    st.dataframe(metrics_frame, hide_index=True, use_container_width=True)
    if len(metrics_frame) >= 2:
        selected = st.multiselect("选择两个实验比较", metrics_frame["backtest_id"].tolist(), max_selections=2)
        if len(selected) == 2:
            st.dataframe(metrics_frame.loc[metrics_frame["backtest_id"].isin(selected)].set_index("backtest_id").T, use_container_width=True)

