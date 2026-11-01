"""Typed domain contracts; money is SEK and fees are annual percentages."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field

AS_OF = date(2026, 9, 29)

class DecisionKind(str, Enum):
    INJECTION = "injection"
    CONDUCT = "conduct"
    RISK = "risk"
    TOPIC = "topic"

class Decision(BaseModel):
    kind: DecisionKind
    label: str
    confidence: float = Field(ge=0, le=1)
    backend: str

class Evidence(BaseModel):
    source_id: str
    household_id: str
    excerpt: str
    timestamp: str | None = None

class Proposal(BaseModel):
    household_id: str
    field: Literal["risk_profile", "suitability_status"]
    proposed_value: str
    evidence: list[Evidence]
    status: Literal["pending_approval"] = "pending_approval"

@dataclass(frozen=True)
class Holding:
    household_id: str
    account_type: str
    isin: str
    market_value_sek: Decimal
    annual_fee_pct: Decimal | None

@dataclass(frozen=True)
class PortfolioSummary:
    household_id: str
    total_value_sek: Decimal
    known_fee_value_sek: Decimal
    unknown_fee_value_sek: Decimal
    annual_fee_sek_known: Decimal
    weighted_fee_pct: Decimal | None
    concentration_hhi: Decimal | None
    by_account_sek: dict[str, Decimal]
    complete_fee_coverage: bool
