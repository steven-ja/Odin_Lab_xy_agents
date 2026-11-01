"""Policy-controlled application service; no write-capable agent tools."""
from __future__ import annotations
from dataclasses import dataclass
from .analytics import PortfolioAnalyzer
from .decisions import ScreeningService
from .domain import Holding, PortfolioSummary
from .security import AccessGateway, Principal

@dataclass(frozen=True)
class Brief:
    household_id: str
    portfolio: PortfolioSummary
    safe_notes: tuple[str, ...]
    quarantined_note_ids: tuple[str, ...]
    warnings: tuple[str, ...]

class BriefService:
    def __init__(self, gateway: AccessGateway, analyzer: PortfolioAnalyzer,
                 screening: ScreeningService):
        self.gateway = gateway
        self.analyzer = analyzer
        self.screening = screening

    def build(self, principal: Principal, household: str, holdings: list[Holding],
              notes: list[tuple[str, str]]) -> Brief:
        self.gateway.require(principal, household)
        # Callers must retrieve holdings and notes through a household-scoped repository.
        # This explicit filter is an additional defense, not a replacement for DB RLS.
        portfolio = self.analyzer.summarize(household, holdings)
        safe, quarantined = [], []
        for note_id, text in notes:
            flagged, _ = self.screening.screen(text)
            (quarantined if flagged else safe).append(note_id if flagged else text)
        warnings = []
        if not portfolio.complete_fee_coverage:
            warnings.append("Portfolio annual fee is incomplete; weighted fee covers known fees only")
        if quarantined:
            warnings.append("Untrusted notes require human review")
        return Brief(household, portfolio, tuple(safe), tuple(quarantined), tuple(warnings))
