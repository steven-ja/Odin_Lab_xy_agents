"""Exact decimal-based descriptive portfolio analytics."""
from __future__ import annotations
from collections import defaultdict
from decimal import Decimal
from .domain import Holding, PortfolioSummary

HUNDRED = Decimal("100")

class PortfolioAnalyzer:
    def summarize(self, household: str, holdings: list[Holding]) -> PortfolioSummary:
        selected = [h for h in holdings if h.household_id == household]
        if any(h.market_value_sek < 0 for h in selected):
            raise ValueError("Negative market value requires explicit handling")
        if any(h.annual_fee_pct is not None and h.annual_fee_pct < 0 for h in selected):
            raise ValueError("Negative fee requires explicit handling")
        total = sum((h.market_value_sek for h in selected), Decimal(0))
        known = sum((h.market_value_sek for h in selected if h.annual_fee_pct is not None), Decimal(0))
        unknown = total - known
        fee = sum((h.market_value_sek * h.annual_fee_pct / HUNDRED
                   for h in selected if h.annual_fee_pct is not None), Decimal(0))
        by_account: dict[str, Decimal] = defaultdict(Decimal)
        for h in selected:
            by_account[h.account_type] += h.market_value_sek
        # HHI computed over holdings, not issuers or economic exposure.
        hhi = sum(((h.market_value_sek / total) ** 2 for h in selected), Decimal(0)) if total else None
        weighted = (fee / known * HUNDRED) if known else None
        return PortfolioSummary(household, total, known, unknown, fee,
                                weighted, hhi, dict(by_account), unknown == 0)
