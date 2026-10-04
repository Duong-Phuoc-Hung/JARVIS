"""New workflow shortcuts must not steal specific screen/note commands."""
import pytest

from tests.eval.no_diacritic_regression import _build_router


@pytest.mark.parametrize('phrase', ['man hinh nghi ngoi', 'cho man hinh nghi ngoi', 'màn hình nghỉ ngơi'])
def test_screen_rest_is_not_relax_workflow(phrase):
    intent = _build_router().parse_intent(phrase, force_llm=False)
    assert intent.action_name == 'system_power'
    assert intent.parameters['action'] == 'screen_off'


@pytest.mark.parametrize('phrase', ['ghi chu lai', 'ghi chú lại', 'tạo ghi chú mới'])
def test_note_without_content_requests_content(phrase):
    intent = _build_router().parse_intent(phrase, force_llm=False)
    assert intent.action_name == 'note_add'
    assert not intent.parameters.get('content')


def test_note_preserves_actual_content():
    intent = _build_router().parse_intent('ghi chú mua sữa', force_llm=False)
    assert intent.action_name == 'note_add'
    assert intent.parameters['content'] == 'mua sữa'
