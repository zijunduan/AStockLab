from __future__ import annotations


def trailing_stop_price(highest_close_since_entry: float, trailing_stop: float) -> float:
    if highest_close_since_entry <= 0:
        raise ValueError("最高收盘价必须大于 0")
    if not 0 < trailing_stop < 1:
        raise ValueError("trailing_stop 必须在 0 和 1 之间")
    return highest_close_since_entry * (1.0 - trailing_stop)


def position_weight_from_volatility(volatility: float, target_volatility: float, max_weight: float) -> float:
    if volatility <= 0:
        return max_weight
    return min(max_weight, target_volatility / volatility * max_weight)

