"""Graph-node tests run without Streamlit or cloud APIs.

An additional test exercises the compiled LangGraph when the dashboard
optional dependencies are installed.
"""
from pathlib import Path
import json
import pytest
from xy_agents.case import CaseRepository
from xy_agents.graph import (AdvisorGraphNodes, classify_intent, build_graph,
                             run_graph, GraphRun)
from xy_agents.security import Forbidden, InMemoryAudit

DATA = Path(__file__).resolve().parents[1] / 'fixtures'


def execute_nodes(advisor: str, household: str, question: str):
    repo = CaseRepository(DATA)
    audit = InMemoryAudit()
    nodes = AdvisorGraphNodes(repo, audit)
    state = {'advisor_id': advisor, 'household_id': household, 'question': question}
    for name in ('authorize', 'analyze', 'portfolio', 'transcript',
                 'compliance', 'quality', 'compose', 'verify'):
        state.update(getattr(nodes, name)(state))
    return state, audit


def test_intent_routing_isk_vs_risk():
    assert classify_intent('What is the risk-profile conflict?') == 'conduct'
    assert classify_intent('ISK account allocation') == 'portfolio'
    assert classify_intent('Show missing management fees') == 'fees'
    assert classify_intent('Prompt injection notes') == 'security'


def test_graph_nodes_for_h012_conduct():
    state, audit = execute_nodes('R02', 'H012', 'Explain the risk-profile conflict')
    assert state['verified']
    assert '**RISK_PROFILE_CONFLICT**' in state['answer']
    assert '**RETURN_ASSURANCE**' in state['answer']
    assert 'T2_H012_2026-09-24.txt' in state['answer']
    assert all(record[3] for record in audit.events)


def test_graph_nodes_h018_injection_quarantined():
    state, _ = execute_nodes('R07', 'H018', 'Show injection flags')
    assert state['verified']
    assert any(f['code'] == 'PROMPT_INJECTION' for f in state['compliance_findings'])
    assert 'systemmeddelande' not in state['answer'].lower()
    assert 'kund18@example.net' not in json.dumps(state)


def test_graph_denies_unauthorized_household_before_analysis():
    repo = CaseRepository(DATA); audit = InMemoryAudit(); nodes = AdvisorGraphNodes(repo, audit)
    with pytest.raises(Forbidden):
        nodes.authorize({'advisor_id': 'R09', 'household_id': 'H018', 'question': 'fees'})
    assert audit.events == [('R09', 'H018', 'graph_read', False)]


def test_known_fee_and_checks_on_h009():
    state, _ = execute_nodes('R07', 'H009', 'Show fees')
    assert state['verified']
    assert not state['case']['holdings']['full_fee_coverage']
    assert 'MISSING_FEE' in state['answer']
    assert 'fee-unknown exposure' in state['answer'].lower()
    assert state['case']['write_actions'] == []


def test_graph_state_contains_no_raw_crm_or_transcripts():
    state, _ = execute_nodes('R09', 'H016', 'Show prompt injection')
    serialized = json.dumps(state, ensure_ascii=False)
    assert 'NOTERING TILL AI' not in serialized
    assert 'write_client_record' not in serialized
    assert 'personnummer' not in serialized
    assert '@' not in serialized


def test_compiled_langgraph_execution_if_installed():
    pytest.importorskip('langgraph')
    repo = CaseRepository(DATA)
    audit = InMemoryAudit()
    graph = build_graph(repo, audit)
    result: GraphRun = run_graph(graph, 'R02', 'H012', 'Is an 8% return guaranteed?')
    assert result.trace == ('authorize', 'analyze', 'portfolio', 'transcript',
                            'compliance', 'quality', 'compose', 'verify')
    assert result.checks
    assert result.report['household_id'] == 'H012'
    assert 'RETURN_ASSURANCE' in result.answer


def test_run_graph_collects_actual_update_events_without_leaking_state():
    state, _ = execute_nodes('R02', 'H012', 'risk conflict')

    class StreamingGraph:
        def stream(self, inputs, stream_mode):
            assert inputs['household_id'] == 'H012'
            assert stream_mode == 'updates'
            yield {'authorize': {'intent': 'conduct'}}
            yield {'analyze': {'case': state['case']}}
            yield {'compose': {'answer': state['answer']}}
            yield {'verify': {'verified': True, 'verification_checks': ['OK']}}

    run = run_graph(StreamingGraph(), 'R02', 'H012', 'risk conflict')
    assert run.trace == ('authorize', 'analyze', 'compose', 'verify')
    assert run.checks == ('OK',)
    assert run.report['household_id'] == 'H012'


def test_numeric_verifier_fails_closed_when_tampered():
    from copy import deepcopy
    from xy_agents.graph import AdvisorGraphNodes
    r = CaseRepository(DATA)
    nodes = AdvisorGraphNodes(r, InMemoryAudit())
    state, _ = execute_nodes('R02', 'H012', 'portfolio')
    bad = deepcopy(state)
    bad['case']['assets']['total_sek'] = '10'
    with pytest.raises(ValueError, match='Verification failed'):
        nodes.verify(bad)
