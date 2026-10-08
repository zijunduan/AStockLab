from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import IntEnum
from typing import Any

import pandas as pd


class ExitState(IntEnum):
    HOLD = 0
    WATCH = 1
    REDUCE_CANDIDATE = 2
    EXIT_CANDIDATE = 3


@dataclass(frozen=True)
class ExitReason:
    category: str
    code: str
    severity: int
    message: str
    persistent: bool = False


@dataclass(frozen=True)
class ExitDecision:
    state: ExitState
    reasons: tuple[ExitReason, ...]

    @property
    def label(self) -> str:
        return self.state.name

    def to_dict(self) -> dict[str, Any]:
        return {"state": self.label, "reasons": [asdict(reason) for reason in self.reasons]}


def _consecutive_true(mask: pd.Series, days: int) -> bool:
    if days <= 0 or len(mask) < days:
        return False
    return bool(mask.fillna(False).tail(days).all())


class ExitRuleEngine:
    """Multi-evidence state machine; one isolated indicator cannot trigger EXIT."""

    def __init__(self, strategy: dict[str, Any], risk: dict[str, Any]):
        self.strategy = strategy
        self.risk = risk.get("thresholds", risk)

    def evaluate(
        self,
        ranking_history: pd.DataFrame,
        price_history: pd.DataFrame,
        financial_history: pd.DataFrame | None = None,
        *,
        as_of: str | pd.Timestamp | None = None,
    ) -> ExitDecision:
        reasons: list[ExitReason] = []
        confirmation = int(self.strategy.get("confirmation_days", 5))

        if not ranking_history.empty and "percentile" in ranking_history:
            ranking = ranking_history.sort_values("trade_date")
            weak = pd.to_numeric(ranking["percentile"], errors="coerce") < float(self.strategy.get("model_exit_percentile", 0.40))
            if _consecutive_true(weak, confirmation):
                reasons.append(
                    ExitReason("model", "MODEL_DETERIORATION", 2, f"综合排名连续 {confirmation} 日低于设定分位", persistent=True)
                )

        if not price_history.empty:
            price = price_history.sort_values("trade_date")
            primary_window = min(3, confirmation)
            if {"close", "ma60", "ma60_slope"}.issubset(price.columns):
                primary_break = (price["close"] < price["ma60"]) & (price["ma60_slope"] < 0)
                if _consecutive_true(primary_break, primary_window):
                    reasons.append(
                        ExitReason("trend", "MA60_BREAK", 2, f"跌破 MA60 且斜率转负，连续 {primary_window} 日确认", persistent=True)
                    )
            if {"close", "ma120"}.issubset(price.columns):
                hard_break = price["close"] < price["ma120"]
                if _consecutive_true(hard_break, primary_window):
                    reasons.append(ExitReason("trend", "MA120_BREAK", 2, f"跌破 MA120，连续 {primary_window} 日确认", persistent=True))

            latest = price.iloc[-1]
            drawdown_limit = float(self.strategy.get("trailing_stop", self.risk.get("max_drawdown", 0.25)))
            if pd.notna(latest.get("max_drawdown_120")) and float(latest["max_drawdown_120"]) >= drawdown_limit:
                reasons.append(ExitReason("risk", "DRAWDOWN", 2, f"120 日最大回撤达到 {float(latest['max_drawdown_120']):.1%}"))
            vol_limit = float(self.risk.get("volatility_20_annualized", 0.55))
            if pd.notna(latest.get("volatility_20")) and float(latest["volatility_20"]) >= vol_limit:
                reasons.append(ExitReason("risk", "VOLATILITY_SPIKE", 1, f"20 日年化波动率升至 {float(latest['volatility_20']):.1%}"))
            if "amount" in price and len(price) >= 21:
                baseline = pd.to_numeric(price["amount"], errors="coerce").iloc[-21:-1].median()
                latest_amount = pd.to_numeric(pd.Series([latest.get("amount")]), errors="coerce").iloc[0]
                drop_ratio = float(self.risk.get("amount_drop_ratio", 0.35))
                if pd.notna(baseline) and baseline > 0 and pd.notna(latest_amount) and latest_amount / baseline < drop_ratio:
                    reasons.append(ExitReason("liquidity", "AMOUNT_DROP", 1, "成交额较近 20 日中位数显著下降"))

        if financial_history is not None and not financial_history.empty:
            financials = financial_history.copy()
            financials["announcement_date"] = pd.to_datetime(financials["announcement_date"], errors="coerce")
            cutoff = pd.Timestamp(as_of) if as_of is not None else pd.Timestamp.today()
            available = financials.loc[financials["announcement_date"].notna() & financials["announcement_date"].le(cutoff)]
            available = available.sort_values(["report_period", "announcement_date"])
            if len(available) >= 2:
                previous, latest_financial = available.iloc[-2], available.iloc[-1]
                if pd.notna(previous.get("roe")) and pd.notna(latest_financial.get("roe")) and previous["roe"] > 0:
                    if latest_financial["roe"] / previous["roe"] < 0.70:
                        reasons.append(ExitReason("fundamental", "ROE_DETERIORATION", 2, "已公告 ROE 较上一报告期下降超过 30%"))
                if pd.notna(latest_financial.get("profit_yoy")) and latest_financial["profit_yoy"] < 0:
                    reasons.append(ExitReason("fundamental", "PROFIT_NEGATIVE_GROWTH", 1, "最新已公告利润同比为负"))
                if pd.notna(previous.get("debt_ratio")) and pd.notna(latest_financial.get("debt_ratio")):
                    if latest_financial["debt_ratio"] - previous["debt_ratio"] > 0.10:
                        reasons.append(ExitReason("fundamental", "DEBT_RISE", 1, "最新已公告资产负债率明显上升"))

        categories = {reason.category for reason in reasons}
        severity_sum = sum(reason.severity for reason in reasons)
        persistent_categories = {reason.category for reason in reasons if reason.persistent}
        if len(categories) >= 3 or ("model" in persistent_categories and "trend" in persistent_categories):
            state = ExitState.EXIT_CANDIDATE
        elif len(categories) >= 2 or severity_sum >= 4:
            state = ExitState.REDUCE_CANDIDATE
        elif reasons:
            state = ExitState.WATCH
        else:
            state = ExitState.HOLD
        return ExitDecision(state, tuple(reasons))

