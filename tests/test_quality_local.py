from pathlib import Path
import json
from unittest.mock import patch

from xy_agents.case import analyze_folder
from xy_agents.local_models import summarize

DATA = Path(__file__).resolve().parents[1] / 'fixtures'


def test_decision_model_abstains_and_preserves_context():
    from xy_agents.local_models import decide_sources, QUESTIONS
    with patch('xy_agents.local_models.load_decision_model') as loader:
        loader.return_value.system_one.return_value = {'answers': {
            'conduct': {'choice': 'review_conduct', 'probabilities':
                        {'review_conduct': .64, 'not_established': .36}}}}
        text = 'Advisor: future returns.\nClient: please be cautious.'
        result = decide_sources([('T2', text)], 'unused')
        assert all(r['decision'] == 'review_required' for r in result)
        assert loader.return_value.system_one.call_args.kwargs == {
            'state': {'source': 'T2', 'evidence': text}, 'questions': QUESTIONS}


def test_decision_model_rejects_invalid_probabilities():
    from xy_agents.local_models import decide_sources
    with patch('xy_agents.local_models.load_decision_model') as loader:
        loader.return_value.system_one.return_value = {'answers': {
            'conduct': {'choice': 'review_conduct', 'probabilities':
                        {'review_conduct': float('nan'), 'not_established': .5}}}}
        assert all(r['decision'] == 'review_required' for r in decide_sources([('T2', 'text')], 'unused'))


def codes(advisor, household):
    return {f['code'] for f in analyze_folder(DATA, advisor, household)['findings']}


def test_source_inconsistencies_and_unchanged_risk():
    assert 'STALE_LAST_MEETING' in codes('R07', 'H001')
    assert 'LOWER_RISK_EXPRESSED' not in codes('R07', 'H001')
    assert 'FUTURE_LAST_MEETING' in codes('R07', 'H013')
    assert 'LOWER_RISK_EXPRESSED' in codes('R09', 'H014')
    assert 'RISK_PROFILE_CONFLICT' in codes('R02', 'H012')


def test_gemma_uses_loopback_and_verified_report_only():
    class Response:
        def __enter__(self):
            from io import StringIO
            return StringIO(json.dumps({'response': 'Review evidence.'}))
        def __exit__(self, *args):
            pass
    with patch('xy_agents.local_models.build_opener') as opener:
        opener.return_value.open.return_value = Response()
        assert summarize({'household_id': 'H001'}, [], 'Explain') == 'Review evidence.'
        request = opener.return_value.open.call_args.args[0]
        assert request.full_url == 'http://127.0.0.1:11434/api/generate'
        body = json.loads(request.data)
        assert 'verified_report' in body['prompt']


def test_dashboard_renders_and_switches_scope():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(DATA.parent / 'dashboard.py')).run(timeout=60)
    assert not app.exception
    app.selectbox[0].select('R09').run(timeout=60)
    assert not app.exception
    assert 'H001' not in app.selectbox[1].options
    audit_table = app.dataframe[-1].value
    assert set(audit_table['Advisor']) == {'R09'}
