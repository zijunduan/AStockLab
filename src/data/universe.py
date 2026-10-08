from __future__ import annotations

import re

import pandas as pd


_QLIB_PATTERN = re.compile(r"^(SH|SZ|BJ)(\d{6})$", re.IGNORECASE)
_SUFFIX_PATTERN = re.compile(r"^(\d{6})\.(SH|SZ|BJ)$", re.IGNORECASE)


def infer_exchange(code: str) -> str:
    digits = str(code).strip().upper()
    if _QLIB_PATTERN.match(digits):
        return digits[:2]
    suffix = _SUFFIX_PATTERN.match(digits)
    if suffix:
        return suffix.group(2)
    digits = re.sub(r"\D", "", digits).zfill(6)[-6:]
    if digits.startswith(("4", "8", "92")):
        return "BJ"
    if digits.startswith(("5", "6", "9")):
        return "SH"
    return "SZ"


def normalize_ticker(code: object) -> str:
    raw = str(code).strip().upper()
    match = _QLIB_PATTERN.match(raw)
    if match:
        return f"{match.group(1).upper()}{match.group(2)}"
    match = _SUFFIX_PATTERN.match(raw)
    if match:
        return f"{match.group(2).upper()}{match.group(1)}"
    digits = re.sub(r"\D", "", raw)
    if not digits:
        raise ValueError(f"无法识别股票代码: {code!r}")
    digits = digits.zfill(6)[-6:]
    return f"{infer_exchange(digits)}{digits}"


def to_akshare_symbol(code: object) -> str:
    return normalize_ticker(code)[2:]


def to_suffix_symbol(code: object) -> str:
    ticker = normalize_ticker(code)
    return f"{ticker[2:]}.{ticker[:2]}"


def board_of(code: object) -> str:
    ticker = normalize_ticker(code)
    digits = ticker[2:]
    if ticker.startswith("BJ"):
        return "北交所"
    if digits.startswith("688"):
        return "科创板"
    if digits.startswith(("300", "301")):
        return "创业板"
    if ticker.startswith("SH"):
        return "沪市主板"
    return "深市主板"


def apply_default_universe_filters(
    frame: pd.DataFrame,
    *,
    min_listing_days: int = 120,
    exclude_st: bool = True,
    exclude_delisting: bool = True,
) -> pd.DataFrame:
    result = frame.copy()
    if "name" in result:
        names = result["name"].fillna("").astype(str).str.upper()
        if exclude_st:
            result = result.loc[~names.str.contains(r"\*?ST", regex=True)]
            names = result["name"].fillna("").astype(str).str.upper()
        if exclude_delisting:
            result = result.loc[~names.str.contains("退")]
    if "listing_date" in result:
        listing = pd.to_datetime(result["listing_date"], errors="coerce")
        cutoff = pd.Timestamp.now().normalize() - pd.offsets.BDay(min_listing_days)
        result = result.loc[listing.isna() | listing.le(cutoff)]
    return result.reset_index(drop=True)

