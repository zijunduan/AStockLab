from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from src.factors.growth import ensure_growth_factors
from src.factors.normalization import normalize_cross_section, weighted_available_mean
from src.factors.quality import ensure_quality_factors
from src.factors.valuation import add_valuation_factors


DIMENSION_LABELS = {
    "quality": "质量",
    "value": "估值",
    "growth": "成长",
    "momentum": "动量",
    "trend": "趋势",
    "risk": "风险防御",
    "liquidity": "流动性",
}

FACTOR_LABELS = {
    "roe": "ROE", "roa": "ROA", "roic": "ROIC", "gross_margin": "毛利率",
    "net_margin": "净利率", "ocf_to_profit": "经营现金流/净利润", "debt_ratio": "资产负债率",
    "revenue_yoy": "营收同比", "profit_yoy": "利润同比", "eps_growth": "EPS 增速",
    "ep": "盈利收益率", "bp": "账面市值比", "dividend_yield": "股息率",
    "momentum_20": "20 日动量", "momentum_60": "60 日动量", "momentum_120": "120 日动量",
    "momentum_250": "250 日动量", "momentum_12_1": "12-1 动量",
    "price_ma20": "价格/MA20", "price_ma60": "价格/MA60", "price_ma120": "价格/MA120",
    "price_ma250": "价格/MA250", "ma60_slope": "MA60 斜率", "trend_consistency": "趋势一致性",
    "volatility_20": "20 日波动", "volatility_60": "60 日波动", "downside_volatility_60": "下行波动",
    "max_drawdown_120": "120 日最大回撤", "atr_14": "ATR", "extreme_move_20": "极端波动",
    "average_amount_20": "20 日平均成交额", "average_turnover_20": "20 日平均换手率", "amihud_20": "Amihud 非流动性",
}


def select_point_in_time_financials(financials: pd.DataFrame, as_of: str | pd.Timestamp) -> pd.DataFrame:
    """Return the newest report actually announced by `as_of` for each ticker."""
    if financials.empty:
        return financials.copy()
    data = financials.copy()
    data["report_period"] = pd.to_datetime(data["report_period"], errors="coerce")
    data["announcement_date"] = pd.to_datetime(data["announcement_date"], errors="coerce")
    cutoff = pd.Timestamp(as_of)
    eligible = data.loc[data["announcement_date"].notna() & data["announcement_date"].le(cutoff)].copy()
    eligible = eligible.sort_values(["ticker", "report_period", "announcement_date"])
    return eligible.groupby("ticker", as_index=False, sort=False).tail(1).reset_index(drop=True)


def attach_point_in_time_financials(observations: pd.DataFrame, financials: pd.DataFrame) -> pd.DataFrame:
    """As-of join by announcement date; never joins on report period alone."""
    if financials.empty:
        return observations.copy()
    left = observations.copy()
    right = financials.copy()
    left["trade_date"] = pd.to_datetime(left["trade_date"], errors="coerce")
    right["announcement_date"] = pd.to_datetime(right["announcement_date"], errors="coerce")
    right = right.loc[right["announcement_date"].notna()].copy()
    left = left.sort_values(["trade_date", "ticker"])
    right = right.sort_values(["announcement_date", "ticker"])
    return pd.merge_asof(
        left,
        right,
        left_on="trade_date",
        right_on="announcement_date",
        by="ticker",
        direction="backward",
        allow_exact_matches=True,
        suffixes=("", "_financial"),
    )


@dataclass
class FactorModelResult:
    scores: pd.DataFrame
    factor_columns: list[str]


class FactorModel:
    def __init__(self, factor_config: dict[str, Any]):
        self.config = factor_config
        self.dimension_weights: dict[str, float] = dict(factor_config.get("weights", {}))
        self.dimension_weights.update(factor_config.get("auxiliary_weights", {}))
        self.dimensions: dict[str, dict[str, float]] = factor_config.get("dimensions", {})
        self.lower = float(factor_config.get("winsor_lower", 0.01))
        self.upper = float(factor_config.get("winsor_upper", 0.99))

    def score_cross_section(self, frame: pd.DataFrame, *, industry_neutral: bool = False) -> FactorModelResult:
        if "ticker" not in frame or "trade_date" not in frame:
            raise ValueError("因子评分需要 ticker 和 trade_date")
        data = add_valuation_factors(frame)
        data = ensure_quality_factors(data)
        data = ensure_growth_factors(data)
        raw_factors = sorted({factor for factors in self.dimensions.values() for factor in factors if factor in data})
        group_columns = ["industry"] if industry_neutral and "industry" in data else []
        data = normalize_cross_section(
            data,
            raw_factors,
            group_columns=group_columns,
            winsor_lower=self.lower,
            winsor_upper=self.upper,
        )

        oriented_values: dict[str, pd.Series] = {}
        dimension_component_weights: dict[str, dict[str, float]] = {}
        for dimension, factors in self.dimensions.items():
            component_weights: dict[str, float] = {}
            for factor, weight in factors.items():
                percentile = f"{factor}_percentile"
                if percentile not in data or weight == 0:
                    continue
                oriented = f"{factor}_oriented"
                oriented_values[oriented] = data[percentile] if weight > 0 else 1.0 - data[percentile]
                component_weights[oriented] = abs(float(weight))
            dimension_component_weights[dimension] = component_weights
        data = pd.concat([data, pd.DataFrame(oriented_values, index=data.index)], axis=1)
        for dimension, component_weights in dimension_component_weights.items():
            data[f"{dimension}_score"] = weighted_available_mean(data, component_weights) * 100.0

        score_weights = {
            f"{dimension}_score": abs(float(weight))
            for dimension, weight in self.dimension_weights.items()
            if weight != 0 and f"{dimension}_score" in data
        }
        normalized_scores = data[[column for column in score_weights]].div(100.0)
        data["factor_score"] = weighted_available_mean(normalized_scores, score_weights) * 100.0
        data["factor_coverage"] = data[list(score_weights)].notna().sum(axis=1).div(max(len(score_weights), 1))
        data["factor_explanation"] = data.apply(self._explain_row, axis=1)
        return FactorModelResult(data, raw_factors)

    def _explain_row(self, row: pd.Series) -> str:
        positive: list[tuple[float, str]] = []
        negative: list[tuple[float, str]] = []
        for dimension, factors in self.dimensions.items():
            dimension_score = row.get(f"{dimension}_score")
            if pd.notna(dimension_score):
                label = DIMENSION_LABELS.get(dimension, dimension)
                if dimension_score >= 80:
                    positive.append((float(dimension_score), f"{label}维度位于横截面前 {max(1, round(100 - dimension_score))}%"))
                elif dimension_score <= 20:
                    negative.append((float(100 - dimension_score), f"{label}维度位于横截面后 {max(1, round(dimension_score))}%"))
            for factor, weight in factors.items():
                percentile = row.get(f"{factor}_percentile")
                if pd.isna(percentile):
                    continue
                oriented = float(percentile) if weight > 0 else 1.0 - float(percentile)
                label = FACTOR_LABELS.get(factor, factor)
                if oriented >= 0.90:
                    positive.append((oriented * abs(weight), f"{label}方向性排名 Top {max(1, round((1-oriented)*100))}%"))
                elif oriented <= 0.10:
                    negative.append(((1-oriented) * abs(weight), f"{label}方向性排名 Bottom {max(1, round(oriented*100))}%"))
        payload = {
            "positive": [text for _, text in sorted(positive, reverse=True)[:4]],
            "negative": [text for _, text in sorted(negative, reverse=True)[:4]],
            "coverage": None if pd.isna(row.get("factor_coverage")) else round(float(row["factor_coverage"]), 3),
        }
        return json.dumps(payload, ensure_ascii=False)

