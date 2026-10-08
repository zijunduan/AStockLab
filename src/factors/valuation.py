from __future__ import annotations

import numpy as np
import pandas as pd


def add_valuation_factors(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    pe = pd.to_numeric(result.get("pe_ttm"), errors="coerce")
    pb = pd.to_numeric(result.get("pb"), errors="coerce")
    ps = pd.to_numeric(result.get("ps"), errors="coerce")
    result["ep"] = np.where(pe > 0, 1.0 / pe, np.nan)
    result["bp"] = np.where(pb > 0, 1.0 / pb, np.nan)
    result["sales_yield"] = np.where(ps > 0, 1.0 / ps, np.nan)
    if "dividend_yield" not in result:
        result["dividend_yield"] = np.nan
    if "fcf_yield" not in result:
        result["fcf_yield"] = np.nan
    return result

