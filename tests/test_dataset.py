from pathlib import Path
import pytest
from xy_agents.case import CaseRepository, CaseAnalyzer, DataContractError
from xy_agents.security import AccessGateway, InMemoryAudit, Forbidden

DATA = Path(__file__).resolve().parents[1] / "fixtures"

def test_case_contract_and_counts():
    r = CaseRepository(DATA)
    assert len(r.households) == 20
    assert len(r.rows['holdings']) == 62  # Actual CSV differs from README's 63
    assert len(r.rows['meetings']) == 11
    assert len(r.advisors) == 3

def test_r09_cannot_read_h018():
    r = CaseRepository(DATA); audit = InMemoryAudit()
    with pytest.raises(Forbidden):
        CaseAnalyzer(r,AccessGateway(audit)).analyze(r.principal('R09'),'H018')
    assert audit.events[-1] == ('R09','H018','read',False)

def test_injection_and_conduct():
    r = CaseRepository(DATA); a = CaseAnalyzer(r,AccessGateway(InMemoryAudit()))
    cases = [('R09','H016','PROMPT_INJECTION'),('R07','H018','PROMPT_INJECTION'),
             ('R02','H012','RETURN_ASSURANCE'),('R02','H012','RISK_PROFILE_CONFLICT'),
             ('R07','H009','MISSING_FEE'),('R07','H002','SUITABILITY_INCOMPLETE')]
    for advisor,hid,code in cases:
        result=a.analyze(r.principal(advisor),hid)
        assert code in {f['code'] for f in result['findings']},(hid,code)
        assert result['write_actions'] == []

def test_no_pii_in_reports():
    r=CaseRepository(DATA); a=CaseAnalyzer(r,AccessGateway(InMemoryAudit()))
    import json
    for advisor in r.advisors:
        for hid in r.principal(advisor).allowed_households:
            result=json.dumps(a.analyze(r.principal(advisor),hid))
            assert '@' not in result
            assert 'personnummer' not in result
