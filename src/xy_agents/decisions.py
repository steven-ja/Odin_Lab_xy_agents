"""Interchangeable typed decision providers; Jev integration is an adapter stub."""
from __future__ import annotations
from typing import Protocol
from .domain import Decision, DecisionKind
from .security import heuristic_injection

class DecisionProvider(Protocol):
    def decide(self, state: str, kind: DecisionKind) -> Decision: ...

class RuleDecisionProvider:
    """Offline baseline. Confidence is NOT calibrated probability."""
    def decide(self, state: str, kind: DecisionKind) -> Decision:
        if kind != DecisionKind.INJECTION:
            return Decision(kind=kind, label="review_required", confidence=0, backend="rules")
        flagged = heuristic_injection(state)
        return Decision(kind=kind, label="suspicious" if flagged else "unclassified",
                        confidence=1 if flagged else 0, backend="rules")

class JevDecisionProvider:
    """Fail-closed integration boundary; wire only after verifying official SDK/API.

    No API request/response format is assumed. The actual client must be supplied
    and its output mapped into Decision, with calibration performed externally.
    """
    def __init__(self, client: object):
        self.client = client

    def decide(self, state: str, kind: DecisionKind) -> Decision:
        raise NotImplementedError("Implement against verified Jev API documentation")

class ScreeningService:
    def __init__(self, provider: DecisionProvider, threshold: float = 0.8):
        self.provider = provider
        self.threshold = threshold

    def screen(self, text: str) -> tuple[bool, Decision]:
        decision = self.provider.decide(text, DecisionKind.INJECTION)
        # Unknown and unsupported classifications require manual review.
        quarantine = heuristic_injection(text) or decision.label != "safe" or (
            decision.label == "suspicious" and decision.confidence >= self.threshold
        )
        return quarantine, decision
