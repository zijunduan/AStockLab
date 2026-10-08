from __future__ import annotations

import pandas as pd


def market_summary(snapshot: pd.DataFrame) -> dict:
    if snapshot.empty:
        return {"count": 0, "up": 0, "down": 0, "amount": 0.0, "regime": "Unknown"}
    pct = pd.to_numeric(snapshot["pct_change"], errors="coerce")
    up = int((pct > 0).sum())
    down = int((pct < 0).sum())
    ratio = up / max(up + down, 1)
    regime = "Bull" if ratio >= 0.60 else ("Bear" if ratio <= 0.40 else "Neutral")
    return {
        "count": int(len(snapshot)), "up": up, "down": down,
        "limit_up_approx": int((pct >= 9.8).sum()), "limit_down_approx": int((pct <= -9.8).sum()),
        "amount": float(pd.to_numeric(snapshot["amount"], errors="coerce").sum()), "regime": regime,
    }

