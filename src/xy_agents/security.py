"""Fail-closed access enforcement and tokenization boundaries."""
from __future__ import annotations
import hashlib
import hmac
import re
from dataclasses import dataclass
from typing import Protocol

class Forbidden(PermissionError):
    pass

@dataclass(frozen=True)
class Principal:
    advisor_id: str
    allowed_households: frozenset[str]

class AuditSink(Protocol):
    def record(self, actor: str, household: str, action: str, allowed: bool) -> None: ...

class AccessGateway:
    def __init__(self, audit: AuditSink):
        self.audit = audit

    def require(self, principal: Principal, household: str, action: str = "read") -> None:
        allowed = household in principal.allowed_households
        self.audit.record(principal.advisor_id, household, action, allowed)
        if not allowed:
            raise Forbidden("Household access denied")

class InMemoryAudit:
    """Test-only sink; replace with append-only production audit storage."""
    def __init__(self):
        self.events: list[tuple[str, str, str, bool]] = []

    def record(self, actor: str, household: str, action: str, allowed: bool) -> None:
        self.events.append((actor, household, action, allowed))

class Tokenizer:
    """Stable pseudonyms for explicit identifiers; not a general PII detector."""
    def __init__(self, secret: bytes):
        if len(secret) < 32:
            raise ValueError("Use at least 32 random bytes")
        self.secret = secret

    def token(self, category: str, value: str) -> str:
        digest = hmac.new(self.secret, f"{category}:{value}".encode(), hashlib.sha256).hexdigest()[:20]
        return f"<{category}_{digest}>"

    def replace_known(self, text: str, identifiers: dict[str, str]) -> str:
        """Longest-first exact replacements; use DLP/NER review for unknown PII."""
        result = text
        for value, category in sorted(identifiers.items(), key=lambda x: -len(x[0])):
            if value:
                result = result.replace(value, self.token(category, value))
        return result

INJECTION_PATTERNS = [
    re.compile(p, re.I) for p in [
        r"ignore (all )?(previous|system) instructions",
        r"(system|developer)\s*(prompt|message|instruction)",
        r"(set|change|update).{0,60}(risk.profile|suitability).{0,40}(aggressive|complete)",
        r"ignorera (alla )?(tidigare|föregående) instruktioner",
        r"(ändra|uppdatera).{0,60}(riskprofil|lämplighetsbedömning)",
    ]
]

def heuristic_injection(text: str) -> bool:
    """Defense-in-depth indicator; never a sole security boundary."""
    return any(pattern.search(text) for pattern in INJECTION_PATTERNS)
