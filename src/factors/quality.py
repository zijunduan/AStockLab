from __future__ import annotations

import numpy as np
import pandas as pd


QUALITY_COLUMNS = ["roe", "roa", "roic", "gross_margin", "net_margin", "ocf_to_profit", "debt_ratio", "interest_coverage"]


def ensure_quality_factors(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in QUALITY_COLUMNS:
        if column not in result:
            result[column] = np.nan
        result[column] = pd.to_numeric(result[column], errors="coerce")
    return result

