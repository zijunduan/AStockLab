from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.data.data_manager import DataManager
from src.reports.market_report import market_summary


def generate_daily_report(manager: DataManager, output_dir: str | Path, trade_date: str | None = None) -> Path:
    rankings = manager.query(
        "SELECT * FROM daily_rankings WHERE trade_date = COALESCE(?, (SELECT max(trade_date) FROM daily_rankings)) ORDER BY rank",
        [trade_date],
    )
    if rankings.empty:
        raise RuntimeError("没有可用于日报的排名")
    report_date = pd.Timestamp(rankings["trade_date"].max()).date()
    snapshot = manager.query("SELECT * FROM market_snapshot WHERE trade_date = ?", [report_date])
    market = market_summary(snapshot)
    previous = manager.query(
        """
        SELECT * FROM daily_rankings
        WHERE trade_date = (SELECT max(trade_date) FROM daily_rankings WHERE trade_date < ?)
        ORDER BY rank
        """,
        [report_date],
    )
    current_top = set(rankings.head(20)["ticker"])
    previous_top = set(previous.head(20)["ticker"]) if not previous.empty else set()
    entered = current_top - previous_top if previous_top else set()
    exited = previous_top - current_top if previous_top else set()
    holdings = manager.query(
        """
        SELECT p.ticker, m.name, p.status, p.buy_date, p.cost, p.quantity
        FROM portfolio p LEFT JOIN stock_master m USING (ticker) ORDER BY p.created_time
        """
    )
    alerts = manager.query("SELECT ticker, severity, title, reason FROM alerts WHERE status = 'OPEN' ORDER BY created_time DESC LIMIT 50")
    health_path = Path(output_dir).resolve().parent / "models" / "model_health.json"
    model_health = json.loads(health_path.read_text(encoding="utf-8")) if health_path.exists() else {"status": "not_evaluated"}
    quality = manager.data_health_summary()

    lines = [
        f"# AStockLab 日报 · {report_date}",
        "",
        "> 本报告用于量化研究和投资决策辅助，不构成投资建议。Market Regime 是分类，不是预测。",
        "",
        "## 市场概况",
        "",
        f"- 股票快照：{market['count']} 只",
        f"- 上涨 / 下跌：{market['up']} / {market['down']}",
        f"- 涨停 / 跌停近似：{market.get('limit_up_approx', 0)} / {market.get('limit_down_approx', 0)}",
        f"- 全市场成交额：{market['amount'] / 1e8:,.0f} 亿元",
        f"- Market Regime：{market['regime']}（仅量化分类）",
        "",
        "## Top 20",
        "",
        "|排名|代码|综合分|多因子|Qlib 原始分|",
        "|---:|---|---:|---:|---:|",
    ]
    for row in rankings.head(20).itertuples():
        qlib = "—" if pd.isna(row.qlib_score) else f"{row.qlib_score:.6f}"
        lines.append(f"|{row.rank}|{row.ticker}|{row.final_score:.2f}|{row.factor_score:.2f}|{qlib}|")
    lines.extend(["", "## Top 20 变化", "", f"- 新进入：{', '.join(sorted(entered)) if entered else '无/暂无上一期'}", f"- 退出：{', '.join(sorted(exited)) if exited else '无/暂无上一期'}", ""])
    lines.extend(["## 持仓状态", ""])
    if holdings.empty:
        lines.append("- 尚未录入持仓。")
    else:
        lines.extend(f"- {row.ticker} {row.name or ''}：{row.status}" for row in holdings.itertuples())
    lines.extend(["", "## 风险提示", ""])
    if alerts.empty:
        lines.append("- 当前无开放风险提醒。")
    else:
        lines.extend(f"- [{row.severity}] {row.ticker} {row.title}：{row.reason}" for row in alerts.itertuples())
    lines.extend(
        [
            "", "## 模型状态", "",
            f"- 状态：{model_health.get('status', 'unknown')}",
            f"- 历史 Rank IC：{model_health.get('rank_ic_mean', '—')}",
            f"- 最近 20 日 Rank IC：{model_health.get('recent_20_rank_ic', '—')}",
            f"- 说明：{model_health.get('message', '尚未评估')}",
            "", "## 数据异常", "",
        ]
    )
    if quality.empty:
        lines.append("- 暂无数据质量报告。")
    else:
        lines.extend(f"- {row.dataset}：{row.status}，{row.row_count} 行，检查时间 {row.created_time}" for row in quality.itertuples())
    lines.extend(["", "## 方法提醒", "", "- 当前权重是策略参数，需要回测验证。", "- Qlib 原始分只用于横截面排序，不是预期收益率。", "- 财务因子只有在公告日之后才允许进入历史信号。"])

    output = Path(output_dir) / f"{report_date}.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output

