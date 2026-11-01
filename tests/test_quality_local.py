from pathlib import Path
import json
from unittest.mock import patch

from xy_agents.case import analyze_folder
from xy_agents.local_models import summarize

DATA = Path(__file__).resolve().parents[1] / 'fixtures'


def test_agent_planner_uses_bounded_tool_selection():
    from xy_agents.local_models import plan_review
    report = {'household_id': 'H012', 'findings': []}
    with patch('xy_agents.local_models.load_decision_model') as loader:
        loader.return_value.system_one.return_value = {'answers': {'next_tool': {
            'choice': 'report_only', 'probabilities': {'report_only': .95, 'source_review': .05}}}}
        assert plan_review('Show fees', report, 'unused')['action'] == 'report_only'
        loader.return_value.system_one.return_value['answers']['next_tool']['probabilities'] = {
            'report_only': .6, 'source_review': .4}
        assert plan_review('Explain risk', report, 'unused')['action'] == 'source_review'


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
            return StringIO('\n'.join(json.dumps(v) for v in [
                {'response': 'Review '}, {'response': 'evidence.'}, {'done': True}]))
        def __exit__(self, *args):
            pass
    with patch('xy_agents.local_models.build_opener') as opener:
        opener.return_value.open.return_value = Response()
        assert summarize({'household_id': 'H001'}, [], 'Explain') == 'Review evidence.'
        request = opener.return_value.open.call_args.args[0]
        assert request.full_url == 'http://127.0.0.1:11434/api/generate'
        body = json.loads(request.data)
        assert 'verified_report' in body['prompt']
        assert body['stream'] is True


def test_stream_yields_before_completion_and_reports_interruption():
    from io import BytesIO
    import pytest
    from xy_agents.local_models import stream_summary
    with patch('xy_agents.local_models.build_opener') as opener:
        opener.return_value.open.return_value = BytesIO(b'{"response":"First"}\n')
        stream = stream_summary({}, [], 'Explain')
        assert next(stream) == 'First'
        with pytest.raises(RuntimeError, match='before completion'):
            next(stream)


def test_agent_chat_streams_and_hides_empty_decisions():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(DATA.parent / 'dashboard.py')).run(timeout=60)
    app.sidebar.toggle[0].set_value(True).run(timeout=60)
    with patch('xy_agents.local_models.plan_review', return_value={'action': 'report_only'}), patch(
        'xy_agents.local_models.stream_summary', return_value=iter(['Review ', 'evidence.'])):
        app.chat_input[0].set_value('Explain fees').run(timeout=60)
    assert not app.exception
    assert any(m.value == 'Review evidence.' for m in app.markdown)
    assert not any(s.value == 'Decision model results · d3-edge' for s in app.subheader)
    assert app.session_state.last_trace[-2:] == ('agent_plan', 'answer_agent')


def test_agent_chat_preserves_decisions_on_stream_failure():
    from streamlit.testing.v1 import AppTest
    def interrupted(*args):
        yield 'Partial explanation'
        raise RuntimeError('Connection lost')
    app = AppTest.from_file(str(DATA.parent / 'dashboard.py')).run(timeout=60)
    app.sidebar.toggle[0].set_value(True).run(timeout=60)
    app.sidebar.selectbox[1].select('H012').run(timeout=60)
    rows = [{'source': 'M105', 'decision': 'review_required'}]
    with patch('xy_agents.local_models.plan_review', return_value={'action': 'source_review'}), patch(
        'xy_agents.local_models.decide_sources', return_value=rows), patch(
        'xy_agents.local_models.stream_summary', side_effect=interrupted):
        app.chat_input[0].set_value('Explain risk').run(timeout=60)
    assert not app.exception
    message = app.session_state.history[-1]
    assert message['generated_answer'] == 'Partial explanation'
    assert message['decisions'] == tuple(rows)
    assert message['model_errors']
    assert app.session_state.last_trace[-3:] == ('agent_plan', 'decision_tool', 'answer_agent')
    app.run(timeout=60)
    assert any('Explanation incomplete' in w.value for w in app.warning)

def test_dashboard_renders_and_switches_scope():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(DATA.parent / 'dashboard.py')).run(timeout=60)
    assert not app.exception
    app.selectbox[0].select('R09').run(timeout=60)
    assert not app.exception
    assert 'H001' not in app.selectbox[1].options
    audit_table = app.dataframe[-1].value
    assert set(audit_table['Advisor']) == {'R09'}
