from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd


@dataclass(frozen=True)
class BiasCheck:
    name: str
    status: str
    message: str


def audit_inputs(
    signals: pd.DataFrame,
    prices: pd.DataFrame,
    financials: pd.DataFrame | None = None,
    *,
    execution_delay_days: int = 1,
    universe_is_point_in_time: bool | None = None,
) -> list[BiasCheck]:
    checks: list[BiasCheck] = []
    checks.append(
        BiasCheck(
            "look_ahead",
            "pass" if execution_delay_days >= 1 else "fail",
            f"信号后延迟 {execution_delay_days} 个交易日成交" if execution_delay_days >= 1 else "信号与成交发生在同一日",
        )
    )
    duplicate_signals = int(signals.duplicated(["trade_date", "ticker"]).sum()) if not signals.empty else 0
    checks.append(BiasCheck("signal_duplicates", "pass" if duplicate_signals == 0 else "fail", f"重复信号 {duplicate_signals} 行"))
    if financials is not None and not financials.empty:
        missing = int(pd.to_datetime(financials["announcement_date"], errors="coerce").isna().sum())
        checks.append(
            BiasCheck(
                "financial_point_in_time",
                "pass" if missing == 0 else "warning",
                "所有财务记录均有公告日" if missing == 0 else f"{missing} 行公告日缺失，相关因子存在潜在 point-in-time bias",
            )
        )
    else:
        checks.append(BiasCheck("financial_point_in_time", "not_applicable", "本次信号未使用财务字段"))
    if universe_is_point_in_time is True:
        checks.append(BiasCheck("survivorship", "pass", "使用时点股票池"))
    elif universe_is_point_in_time is False:
        checks.append(BiasCheck("survivorship", "warning", "使用当前成分股，可能存在幸存者偏差"))
    else:
        checks.append(BiasCheck("survivorship", "warning", "股票池时点属性未证明，结果不得视为无幸存者偏差"))
    checks.append(BiasCheck("selection_bias", "warning", "策略/参数若根据本次结果选择，必须用独立样本外区间复核"))
    checks.append(BiasCheck("overfitting", "warning", "单次回测不能排除过拟合；应使用 walk-forward 与多版本对比"))
    return checks


def audit_to_dict(checks: list[BiasCheck]) -> list[dict]:
    return [asdict(check) for check in checks]

