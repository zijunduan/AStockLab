from __future__ import annotations


def equal_weight_positions(tickers: list[str], gross_exposure: float = 1.0, max_position: float = 0.10) -> dict[str, float]:
    if not tickers:
        return {}
    weight = min(gross_exposure / len(tickers), max_position)
    return {ticker: weight for ticker in tickers}

