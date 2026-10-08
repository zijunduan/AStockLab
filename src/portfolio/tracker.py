from __future__ import annotations

import hashlib
import json

import pandas as pd

from src.data.data_manager import DataManager
from src.portfolio.holdings import HoldingsRepository
from src.services.research import StockResearchService
from src.strategy.exit import ExitRuleEngine
from src.utils.dates import now_shanghai


class PortfolioTracker:
    def __init__(self, manager: DataManager, research: StockResearchService, strategy_config: dict, risk_config: dict):
        self.manager = manager
        self.research = research
        self.engine = ExitRuleEngine(strategy_config, risk_config)

    def evaluate_all(self) -> pd.DataFrame:
        holdings = HoldingsRepository(self.manager).list()
        decisions: list[dict] = []
        for holding in holdings.itertuples():
            ranking = self.research.rank_history(holding.ticker)
            prices = self.research.price_history(holding.ticker, 320)
            financials = self.manager.query(
                "SELECT * FROM financial_metrics WHERE ticker = ? ORDER BY report_period, announcement_date", [holding.ticker]
            )
            as_of = prices["trade_date"].max() if not prices.empty else pd.Timestamp.today()
            decision = self.engine.evaluate(ranking, prices, financials, as_of=as_of)
            decisions.append({"position_id": holding.position_id, "ticker": holding.ticker, **decision.to_dict()})
            with self.manager._write_lock, self.manager.connection() as connection:
                connection.execute(
                    "UPDATE portfolio SET status = ?, update_time = ? WHERE position_id = ?",
                    [decision.label, now_shanghai().replace(tzinfo=None), holding.position_id],
                )
            for reason in decision.reasons:
                identity = f"{holding.ticker}|{as_of}|{reason.code}"
                alert_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]
                now = now_shanghai().replace(tzinfo=None)
                alert = pd.DataFrame(
                    [{
                        "alert_id": alert_id, "ticker": holding.ticker, "trade_date": pd.Timestamp(as_of).date(),
                        "alert_type": reason.category, "severity": decision.label, "status": "OPEN",
                        "title": reason.code, "reason": reason.message,
                        "details_json": json.dumps(decision.to_dict(), ensure_ascii=False),
                        "created_time": now, "update_time": now, "source": "portfolio_tracker",
                    }]
                )
                self.manager._upsert("alerts", alert, ["alert_id"])
        return pd.DataFrame(decisions)

