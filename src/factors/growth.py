from __future__ import annotations

import numpy as np
import pandas as pd


GROWTH_COLUMNS = ["revenue_yoy", "profit_yoy", "eps_growth", "revenue_cagr_3y"]


def ensure_growth_factors(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in GROWTH_COLUMNS:
        if column not in result:
            result[column] = np.nan
        result[column] = pd.to_numeric(result[column], errors="coerce")
    return result

