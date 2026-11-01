"""Read-only, access-scoped LangGraph workflow for the Synthetic XY case.

Graph state contains only pseudonymous identifiers and validated analytical
results. Neither untrusted source text nor customer PII enter graph state.
Model-backed steps can be added behind an independently reviewed boundary.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, TypedDict

from .case import CaseAnalyzer, CaseRepository
from .security import AccessGateway, AuditSink


class AgentState(TypedDict, total=False):
    advisor_id: str
    household_id: str
    question: str
    intent: str
    case: dict[str, Any]
    portfolio: dict[str, Any]
    transcript_findings: list[dict[str, Any]]
    compliance_findings: list[dict[str, Any]]
    quality_findings: list[dict[str, Any]]
    answer: str
    verified: bool
    verification_checks: list[str]


QUALITY = frozenset({
    'ACCOUNT_RECONCILIATION', 'MISSING_FEE', 'MISSING_RISK_PROFILE',
    'SUITABILITY_INCOMPLETE', 'REVIEW_OVERDUE', 'PENSION_DATA_GAP',
    'FUTURE_VALUATION', 'ISIN_FORMAT',
})
CONDUCT = frozenset({
    'RETURN_ASSURANCE', 'RISK_PROFILE_CONFLICT', 'CONDUCT_RISK_CONFLICT',
    'LOWER_RISK_EXPRESSED', 'PROMPT_INJECTION',
})
TRANSCRIPT = frozenset({
    'RETURN_ASSURANCE', 'RISK_PROFILE_CONFLICT', 'CONDUCT_RISK_CONFLICT',
    'LOWER_RISK_EXPRESSED', 'PLANNED_EXPENDITURE', 'LIFE_EVENT',
    'PROMPT_INJECTION',
})


def classify_intent(question: str) -> str:
    """Deterministic, non-privileged router. Unrecognized prompts get a summary."""
    q = question.casefold()
    options = (
        ('fees', r'avgift|fee|cost|kostnad|weighted|förvaltnings'),
        ('portfolio', r'portf|holdings|innehav|allok|koncentr|hhi|asset|tillgång|\bisk\b|\bkf\b|kapital'),
        ('security', r'inject|säker|security|phish|prompt|quarant|karantän'),
        ('conduct', r'risk|lämplig|suitab|compliance|conduct|garant|avkastning|kundens önsk'),
        ('transcripts', r'transkript|möte|meeting|livshänd|familj|utgift|anteck|evidence|källa'),
        ('quality', r'kvalit|quality|missing|sakna|avstäm|reconcil|overdue|förfall|pension|data'),
    )
    return next((name for name, pattern in options if re.search(pattern, q)), 'summary')


def fmt_sek(value: str | None) -> str:
    if value is None:
        return 'unknown'
    return f'{Decimal(value):,.0f} SEK'


def evidence_list(findings: list[dict[str, Any]], limit: int = 12) -> list[str]:
    lines = []
    for finding in findings[:limit]:
        pointers = ', '.join(finding['evidence']) or 'not recorded'
        lines.append(f"- **{finding['code']}** ({finding['severity']}): {finding['detail']}  \n  Evidence: `{pointers}`")
    if len(findings) > limit:
        lines.append(f'- {len(findings) - limit} additional finding(s) omitted; inspect the Findings tab.')
    return lines


class AdvisorGraphNodes:
    """Node implementations depend on a repository and an audit policy, not UI."""

    def __init__(self, repository: CaseRepository, audit: AuditSink):
        self.repo = repository
        self.gateway = AccessGateway(audit)
        self.analyzer = CaseAnalyzer(repository, self.gateway)

    def authorize(self, state: AgentState) -> dict[str, Any]:
        principal = self.repo.principal(state['advisor_id'])
        self.gateway.require(principal, state['household_id'], 'graph_read')
        if state['household_id'] not in self.repo.households:
            # Do not distinguish an unknown household from an inaccessible one.
            from .security import Forbidden
            raise Forbidden('Household access denied')
        return {'intent': classify_intent(state.get('question', ''))}

    def analyze(self, state: AgentState) -> dict[str, Any]:
        principal = self.repo.principal(state['advisor_id'])
        return {'case': self.analyzer.analyze(principal, state['household_id'])}

    def portfolio(self, state: AgentState) -> dict[str, Any]:
        result = state['case']
        return {'portfolio': {'assets': result['assets'], 'holdings': result['holdings']}}

    def transcript(self, state: AgentState) -> dict[str, Any]:
        # Only validated finding metadata; raw transcripts remain inside repository.
        return {'transcript_findings': [f for f in state['case']['findings']
                                        if f['code'] in TRANSCRIPT and
                                        any('.txt' in e for e in f['evidence'])]}

    def compliance(self, state: AgentState) -> dict[str, Any]:
        return {'compliance_findings': [f for f in state['case']['findings']
                                       if f['code'] in CONDUCT]}

    def quality(self, state: AgentState) -> dict[str, Any]:
        return {'quality_findings': [f for f in state['case']['findings']
                                    if f['code'] in QUALITY]}

    def compose(self, state: AgentState) -> dict[str, Any]:
        result = state['case']
        assets = result['assets']; holds = result['holdings']
        intent = state['intent']; household = state['household_id']
        title = f'### {household} · {result["as_of"]}'
        summary = [
            f'- Reported assets: **{fmt_sek(assets["total_sek"])}** '
            f'(cash {fmt_sek(assets["cash_sek"])}, ISK {fmt_sek(assets["isk_sek"])}, KF {fmt_sek(assets["kf_sek"])})',
            f'- Holdings: **{holds["count"]}**, valuation {fmt_sek(holds["valuation_sek"])}',
            f'- Recorded risk: **{result["recorded_risk_profile"] or "missing"}**; '
            f'suitability complete: **{result["suitability_complete"]}**',
            f'- Findings: **{len(result["findings"])}** (including warnings and evidence flags)',
        ]
        fee = [
            f'- Known annual fee (SEK, known-fee holdings only): **{fmt_sek(holds["annual_fee_known_sek"])}**',
            f'- Weighted annual fee on known-fee exposure: **{float(holds["known_exposure_weighted_fee_pct"]):.3f}%**'
            if holds['known_exposure_weighted_fee_pct'] is not None else '- Weighted annual fee: **unknown**',
            f'- Fee-known exposure: {fmt_sek(holds["fee_known_exposure_sek"])}; '
            f'fee-unknown exposure: {fmt_sek(holds["fee_unknown_exposure_sek"])}',
            '- Do not interpret the known-only fee as the total portfolio cost when coverage is incomplete.',
        ]
        if intent == 'fees':
            body = ['**Fee analysis**', *fee, *evidence_list([f for f in result['findings'] if f['code'] == 'MISSING_FEE'])]
        elif intent == 'portfolio':
            hhi = f"{float(holds['holding_row_hhi']):.4f}" if holds['holding_row_hhi'] is not None else 'n/a'
            body = ['**Portfolio analysis**', *summary[:2], f'- Holding-row HHI: **{hhi}** '
                    '(not underlying-fund economic exposure).', *fee]
        elif intent == 'security':
            body = ['**Untrusted-content screening**', *evidence_list([
                f for f in result['findings'] if f['code'] == 'PROMPT_INJECTION'])]
        elif intent == 'conduct':
            body = ['**Risk, suitability and conduct**', summary[2],
                    *evidence_list(state['compliance_findings'] + [f for f in state['quality_findings']
                                                                   if f['code'] in {'SUITABILITY_INCOMPLETE', 'MISSING_RISK_PROFILE'}])]
        elif intent == 'transcripts':
            body = ['**Transcript-derived evidence**', *evidence_list(state['transcript_findings'])]
        elif intent == 'quality':
            body = ['**Data-quality findings**', *evidence_list(state['quality_findings'])]
        else:
            body = ['**Household overview**', *summary, '**Priority findings**',
                    *evidence_list(result['findings']),
                    'Ask about fees, portfolio, suitability, transcripts, or data quality to focus the report.']
        if (intent in {'security', 'conduct', 'transcripts', 'quality'}
                and not any(line.startswith('- **') for line in body)):
            body.append('No matching findings were detected by the implemented rules. This does not prove absence of risk.')
        return {'answer': '\n\n'.join([title, '\n'.join(body),
                    '\n*Read-only analytical prototype. Findings are not financial advice or automatic CRM updates.*'])}

    def verify(self, state: AgentState) -> dict[str, Any]:
        """Independent numerical cross-check; fail closed even with Python -O."""
        case = state['case']; assets = case['assets']; holdings = case['holdings']
        checks: list[str] = []

        def require(condition: bool, message: str) -> None:
            if not condition:
                raise ValueError('Verification failed: ' + message)
            checks.append(message)

        require(all(case['household_id'] == f['household_id'] for f in case['findings']),
                'All findings scoped to requested household')
        require(Decimal(assets['cash_sek']) + Decimal(assets['isk_sek']) +
                Decimal(assets['kf_sek']) == Decimal(assets['total_sek']),
                'Reported total assets reconcile across cash, ISK and KF')
        require(Decimal(holdings['fee_known_exposure_sek']) +
                Decimal(holdings['fee_unknown_exposure_sek']) == Decimal(holdings['valuation_sek']),
                'Known and unknown fee exposure reconcile to total holdings valuation')
        require(holdings['full_fee_coverage'] ==
                (Decimal(holdings['fee_unknown_exposure_sek']) == 0),
                'Fee coverage flag matches missing-fee exposure')
        require(case['write_actions'] == [], 'No write actions were proposed or executed')
        require(state['advisor_id'] in self.repo.advisors,
                'Advisor exists (demo identity: authenticate before production use)')
        return {'verified': True, 'verification_checks': checks}


def build_graph(repository: CaseRepository, audit: AuditSink):
    """Create a real compiled LangGraph (requires the optional dashboard extra)."""
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:
        raise RuntimeError('Install the dashboard extra: pip install -e ".[dashboard]"') from exc

    nodes = AdvisorGraphNodes(repository, audit)
    builder = StateGraph(AgentState)
    for name in ('authorize', 'analyze', 'portfolio', 'transcript', 'compliance',
                 'quality', 'compose', 'verify'):
        builder.add_node(name, getattr(nodes, name))
    builder.add_edge(START, 'authorize')
    for first, second in zip(
        ('authorize', 'analyze', 'portfolio', 'transcript', 'compliance', 'quality', 'compose'),
        ('analyze', 'portfolio', 'transcript', 'compliance', 'quality', 'compose', 'verify'),
    ):
        builder.add_edge(first, second)
    builder.add_edge('verify', END)
    return builder.compile()


@dataclass(frozen=True)
class GraphRun:
    answer: str
    report: dict[str, Any]
    trace: tuple[str, ...]
    checks: tuple[str, ...]


def run_graph(graph: Any, advisor: str, household: str, question: str) -> GraphRun:
    """Stream actual node updates and expose only node names in the execution trace."""
    data: AgentState = {'advisor_id': advisor, 'household_id': household,
                        'question': question[:2000]}
    observed: list[str] = []
    for event in graph.stream(data, stream_mode='updates'):
        for node, update in event.items():
            observed.append(node)
            data.update(update)
    if not data.get('verified') or not data.get('answer'):
        raise RuntimeError('Graph did not produce a verified answer')
    return GraphRun(data['answer'], data['case'], tuple(observed),
                    tuple(data['verification_checks']))
