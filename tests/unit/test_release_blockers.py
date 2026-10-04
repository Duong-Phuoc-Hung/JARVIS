"""Release regressions: truthful results and confirmation before side effects."""
import traceback
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import requests

from jarvis.core.app import JarvisApp
from jarvis.core.dispatcher import ActionDispatcher
from jarvis.llm.client import ChatMessage, LLMClient, LLMProvider, LLMResponse
from jarvis.planner.safety_interceptor import SafetyGateInterceptor
from jarvis.tts.base import TTSError
from jarvis.tts.edge import _mp3_to_pcm


def bare_app():
    app = JarvisApp.__new__(JarvisApp)
    app.tts_manager = None
    app.overlay = None
    app.skill_registry = None
    app.proactive_engine = None
    app.computer_controller = None
    return app


@pytest.mark.parametrize('name,payload', [
    ('healing_watchdog_heal', {'auto_kill': True}),
    ('dialog_resolve', {'auto_dismiss': True, 'action': 'ok'}),
])
def test_new_destructive_actions_require_confirmation(name, payload):
    dispatcher = ActionDispatcher()
    dispatcher.set_safety_interceptor(SafetyGateInterceptor())
    handler = Mock(return_value={'success': True})
    dispatcher.register_action(name=name, handler=handler)
    result = dispatcher.dispatch_action(name, payload=payload)
    assert not result.success
    handler.assert_not_called()


@pytest.mark.parametrize('method,kwargs', [
    ('_handle_note_add', {'content': 'must be persisted'}),
    ('_handle_routine_schedule', {'action_name': 'note_list'}),
    ('_handle_workflow_preset', {'preset': 'work'}),
    ('_handle_workflow_preset', {'preset': 'relax'}),
])
def test_missing_backend_never_reports_success(method, kwargs):
    assert not getattr(bare_app(), method)(**kwargs)['success']


def test_note_backend_failure_is_propagated():
    app = bare_app()
    app.skill_registry = Mock()
    app.skill_registry.invoke_skill.return_value = SimpleNamespace(success=False, data=None, error='disk unavailable')
    assert not app._handle_note_add(content='must be persisted')['success']


def test_research_backend_failure_is_propagated():
    app = bare_app()
    app.web_hub = Mock()
    app.web_hub.conduct_deep_research.return_value = {'success': False, 'spoken_summary': 'No sources'}
    assert not app._handle_deep_research(topic='test')['success']


def test_partial_briefing_is_not_promoted_to_success():
    app = bare_app()
    app.web_hub = Mock()
    app.web_hub.generate_morning_briefing.return_value = {
        'success': False, 'status': 'LIMITED', 'spoken_summary': 'Market unavailable'
    }
    assert app._handle_morning_briefing()['success'] is False


def test_decoder_failure_does_not_return_mp3_as_pcm():
    with patch.dict('sys.modules', {'soundfile': None, 'av': None}):
        with pytest.raises(TTSError):
            _mp3_to_pcm(b'ID3-invalid-audio')


@pytest.mark.parametrize('error_type', [requests.ConnectionError, requests.Timeout])
def test_cloud_transport_failure_uses_local_fallback(error_type):
    client = LLMClient(provider=LLMProvider.GEMINI, api_key='test-key', max_retries=0, fallback_to_ollama=True)
    with patch.object(client, '_call_gemini', side_effect=error_type('offline')), patch.object(
        client, '_call_ollama', return_value=LLMResponse(content='local reply', model='llama3.2')
    ) as fallback:
        assert client.chat([ChatMessage(role='user', content='hello')]).content == 'local reply'
        fallback.assert_called_once()


def test_cloud_exception_traceback_redacts_original_credentials():
    secret = 'release-test-secret'
    client = LLMClient(provider=LLMProvider.GEMINI, api_key=secret, max_retries=0)
    with patch.object(client, '_call_gemini', side_effect=requests.ConnectionError('url?key=' + secret)):
        try:
            client.chat([ChatMessage(role='user', content='hello')])
        except Exception:
            assert secret not in traceback.format_exc()
        else:
            pytest.fail('Transport failure must not succeed')


def test_healing_probe_failure_is_not_success():
    app = bare_app()
    with patch('jarvis.healing.terminator.HealingEngine', side_effect=RuntimeError('probe unavailable')):
        assert not app._handle_healing_watchdog_heal()['success']


def test_screen_off_failed_native_call_is_not_success():
    app = bare_app()
    app.config = {}
    with patch('jarvis.core.app.ctypes.windll', create=True) as native:
        native.user32.PostMessageW.return_value = 0
        assert not app._handle_system_power(action='screen_off')['success']


def test_brightness_zero_is_a_successful_workflow_result():
    app = bare_app()
    app.computer_controller = Mock()
    app.computer_controller.change_brightness.return_value = 0
    assert app._handle_workflow_preset(preset='relax')['success']


def test_dialog_native_failure_does_not_report_dismissed():
    from jarvis.vision.dialog_detector import ErrorDialogDetector
    detector = ErrorDialogDetector()
    detector._is_windows = True
    with patch('jarvis.vision.dialog_detector.ctypes.windll', create=True) as native:
        native.user32.PostMessageW.return_value = 0
        assert not detector.dismiss_dialog(1234)


def test_ollama_fallback_uses_local_model_and_url():
    client = LLMClient(provider=LLMProvider.GEMINI, api_key='test-key', model='cloud-model', base_url='https://cloud.invalid')
    client.session = Mock()
    client.session.post.return_value.json.return_value = {'message': {'content': 'hello'}}
    client._call_ollama([ChatMessage(role='user', content='hello')], None, 0.0, 10)
    args, kwargs = client.session.post.call_args
    assert args[0] == 'http://localhost:11434/api/chat'
    assert kwargs['json']['model'] == 'llama3.2'


def test_dialog_handler_propagates_failed_dismissal():
    app = bare_app()
    with patch('jarvis.vision.dialog_detector.ErrorDialogDetector') as detector:
        detector.return_value.resolve_error_dialogs.return_value = [{'title': 'Warning', 'dismissed': False}]
        assert not app._handle_dialog_resolve()['success']


def test_failed_window_action_does_not_speak_success():
    app = bare_app()
    app.tts_manager = Mock()
    app.computer_controller = Mock()
    app.computer_controller.get_active_window.return_value = {'hwnd': 1234, 'title': 'Editor'}
    app.computer_controller.snap_window.return_value = False
    result = app._handle_window_active(action='snap_left')
    assert not result['success']
    assert 'Đã xếp' not in result['message']
    assert all('Đã xếp' not in str(call) for call in app.tts_manager.speak.call_args_list)


def test_calculator_vietnamese_decimal_phay():
    from jarvis.skills.calculator import evaluate_expression
    assert evaluate_expression("10 phẩy 5 + 2 phẩy 5") == 13.0
    assert evaluate_expression("7 phay 25 x 4") == 29.0


def test_control_snap_and_scroll_vietnamese_diacritics():
    from jarvis.automation.control import ComputerController
    ctrl = ComputerController()
    ctrl.win32 = Mock()
    ctrl.win32.send_hotkey.return_value = True

    # Test snap with Vietnamese diacritics
    assert ctrl.snap_window("phải") is True
    ctrl.win32.send_hotkey.assert_called_with("win", "right")

    assert ctrl.snap_window("trái") is True
    ctrl.win32.send_hotkey.assert_called_with("win", "left")

    # Test scroll with Vietnamese diacritics
    assert ctrl.scroll_page("xuống") is True
    ctrl.win32.send_hotkey.assert_called_with("pagedown")


def test_routine_reminder_dispatch_suppresses_vocal_for_routines():
    from jarvis.proactive.reminders import ReminderScheduler, ScheduledReminder
    scheduler = ReminderScheduler()
    tts_mock = Mock()
    scheduler.tts_callback = tts_mock

    # Routine with action_name should NOT invoke TTS callback
    routine = ScheduledReminder(
        trigger_timestamp=0.0,
        reminder_id="test_routine",
        text="Auto cleanup",
        action_name="healing_watchdog_heal",
    )
    scheduler._dispatch_reminder(routine)
    tts_mock.assert_not_called()

    # Pure reminder without action_name SHOULD invoke TTS callback
    reminder = ScheduledReminder(
        trigger_timestamp=0.0,
        reminder_id="test_rem",
        text="Drink water",
        action_name=None,
    )
    scheduler._dispatch_reminder(reminder)
    tts_mock.assert_called_once()


def test_note_taker_clear_deletes_desktop_markdown(tmp_path, monkeypatch):
    from jarvis.skills.note_taker import execute
    fake_home = tmp_path / "home"
    desktop = fake_home / "Desktop"
    desktop.mkdir(parents=True)
    monkeypatch.setattr("pathlib.Path.home", lambda: fake_home)
    monkeypatch.setenv("LOCALAPPDATA", str(fake_home / "LocalAppData"))

    # Add note
    res_add = execute(action="add", content="Meeting at 3PM")
    assert res_add["data"]["success"] is True
    notes_md = desktop / "JARVIS_Notes.md"
    assert notes_md.exists()

    # Clear notes
    res_clear = execute(action="clear")
    assert res_clear["data"]["success"] is True
    assert not notes_md.exists()


def test_router_window_thu_nho():
    from jarvis.llm.router import LLMIntentRouter
    router = LLMIntentRouter(Mock())
    res = router.parse_intent("thu nhỏ", force_llm=False)
    assert res.action_name == "window_active"
    assert res.parameters.get("action") == "minimize"
