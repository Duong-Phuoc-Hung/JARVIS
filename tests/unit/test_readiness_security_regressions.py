"""Behavioral regressions from the September readiness audit; no live actions."""
import json
import types

import pytest

from jarvis.planner.safety_interceptor import SafetyGateInterceptor
from jarvis.core.dispatcher import ActionDispatcher
from jarvis.core.models import ActionResult
from jarvis.skills import skill_synthesizer as synth
from jarvis.skills.synthesizer import DynamicSkillSynthesizer


def test_confirmed_token_expires_before_execution(monkeypatch):
    now = [100.0]
    monkeypatch.setattr('jarvis.automation.safety_gate.time.time', lambda: now[0])
    guard = SafetyGateInterceptor(timeout_seconds=30)
    token = guard.gate('delete_file', {'path': 'sample.txt'})
    assert guard.confirm(token)
    now[0] = 131.0
    assert guard.verify(token, 'delete_file', {'path': 'sample.txt'}) == (False, 'EXPIRED')


def test_confirmation_payload_cannot_change_through_caller_reference():
    guard = SafetyGateInterceptor()
    payload = {'targets': ['sample.txt']}
    token = guard.gate('delete_file', payload)
    assert guard.confirm(token)
    payload['targets'].append('important.txt')
    assert guard.verify(token, 'delete_file', payload) == (False, 'PAYLOAD_MISMATCH')


@pytest.mark.parametrize('name', ['delete_status', 'remove_read', 'discord_send_status'])
def test_read_suffix_cannot_override_destructive_prefix(name):
    assert SafetyGateInterceptor().is_high_risk(name, {})


@pytest.mark.parametrize('name', ['../outside', '', '..'])
def test_delete_rejects_invalid_skill_names(tmp_path, monkeypatch, name):
    root = tmp_path / 'skills'
    root.mkdir()
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'keep.txt').write_text('keep')
    monkeypatch.setattr(synth, '_SKILLS_ROOT', root)
    result = synth.execute(action='delete', skill_name=name)
    assert result['data']['success'] is False
    assert (outside / 'keep.txt').read_text() == 'keep'
    assert root.exists()


def test_delete_requires_explicit_synthesized_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(synth, '_SKILLS_ROOT', tmp_path)
    target = tmp_path / 'builtin'
    target.mkdir()
    (target / '__init__.py').write_text('# keep')
    assert synth.execute(action='delete', skill_name='builtin')['data']['success'] is False
    assert target.exists()


def test_create_does_not_overwrite_builtin(tmp_path, monkeypatch):
    monkeypatch.setattr(synth, '_SKILLS_ROOT', tmp_path)
    target = tmp_path / 'builtin'
    target.mkdir()
    (target / 'metadata.json').write_text(json.dumps({'synthesized': False}))
    (target / '__init__.py').write_text('# original')
    result = synth.execute(action='create', skill_name='builtin', description='monitor CPU')
    assert result['data']['success'] is False
    assert (target / '__init__.py').read_text() == '# original'


@pytest.mark.parametrize('template', ['generic', 'notifier', 'calculator', 'sender'])
def test_unimplemented_generated_action_never_claims_success(template):
    namespace = {}
    exec(synth._generate_skill_code('safe_skill', 'A test skill', template, ['run']), namespace)
    result = namespace['execute']()
    assert result['data']['success'] is False


def test_generated_fetch_failure_is_not_success(monkeypatch):
    import urllib.request
    def offline(*args, **kwargs):
        raise OSError('offline')
    monkeypatch.setattr(urllib.request, 'urlopen', offline)
    namespace = {}
    exec(synth._generate_skill_code('fetch_skill', 'Fetch', 'web_fetch', ['run']), namespace)
    assert namespace['execute'](query='https://example.test')['data']['success'] is False


def test_rejected_dynamic_update_preserves_existing_skill(tmp_path):
    target = tmp_path / 'existing_skill'
    target.mkdir()
    source = target / '__init__.py'
    source.write_text('# working implementation')
    generator = DynamicSkillSynthesizer(skills_dir=tmp_path)
    with pytest.raises(ValueError):
        generator.synthesize_skill(name='existing_skill', code='def broken(',
                                   overwrite=True, dry_run=False)
    assert source.read_text() == '# working implementation'


def test_description_is_data_not_generated_python():
    description = '\"\"\"\nraise RuntimeError("injected")\n#'
    namespace = {}
    exec(synth._generate_skill_code('safe_skill', description, 'generic', ['run']), namespace)
    assert namespace['execute']()['data']['success'] is False


def test_monitor_missing_metrics_does_not_invent_zero(monkeypatch):
    monkeypatch.setitem(__import__('sys').modules, 'psutil', types.ModuleType('psutil'))
    namespace = {}
    exec(synth._generate_skill_code('safe_skill', 'monitor', 'monitor', ['run']), namespace)
    assert namespace['execute']()['data']['success'] is False


@pytest.mark.parametrize('status', ['BLOCKED', 'UNAVAILABLE', 'NOT_CONFIGURED'])
def test_unavailable_result_cannot_claim_success(status):
    result = ActionResult(status=status)
    assert result.success is False
    assert result.to_dict()['status'] == status
    assert result.code == status
    assert result.error_code == status


@pytest.mark.parametrize('status', ['BLOCKED', 'UNAVAILABLE', 'NOT_CONFIGURED'])
@pytest.mark.parametrize('asynchronous', [False, True])
def test_dispatch_preserves_non_success_status(status, asynchronous):
    import asyncio
    dispatcher = ActionDispatcher()
    dispatcher.register_action('probe_backend', lambda: {'status': status, 'code': 'TEST_UNAVAILABLE'})
    result = (asyncio.run(dispatcher.dispatch_action_async('probe_backend')) if asynchronous
              else dispatcher.dispatch_action('probe_backend'))
    assert result.success is False
    assert result.to_dict()['status'] == status


@pytest.mark.parametrize('asynchronous', [False, True])
@pytest.mark.parametrize('structured', [False, True])
def test_dispatch_preserves_result_metadata(asynchronous, structured):
    import asyncio
    payload = {'status': 'UNAVAILABLE', 'code': 'DEVICE_OFFLINE',
               'message': 'Device offline', 'retryable': True}
    outcome = ActionResult(**payload) if structured else payload
    dispatcher = ActionDispatcher()
    dispatcher.register_action('probe_backend', lambda: outcome)
    result = (asyncio.run(dispatcher.dispatch_action_async('probe_backend')) if asynchronous
              else dispatcher.dispatch_action('probe_backend'))
    assert result.to_dict()['status'] == 'UNAVAILABLE'
    assert result.code == 'DEVICE_OFFLINE'
    assert result.message == 'Device offline'
    assert result.retryable is True


def test_default_test_network_policy_blocks_external_connections():
    import socket
    with socket.socket() as client:
        with pytest.raises(OSError, match='External network disabled'):
            client.connect(('192.0.2.1', 443))
    with pytest.raises(OSError, match='External network disabled'):
        socket.getaddrinfo('example.invalid', 443)


def test_default_test_network_policy_allows_loopback():
    import socket
    with socket.socket() as server, socket.socket() as client:
        server.bind(('127.0.0.1', 0))
        server.listen(1)
        client.settimeout(1)
        client.connect(server.getsockname())
        connection, _ = server.accept()
        connection.close()


@pytest.mark.parametrize('filename', ['__init__.py', 'metadata.json', 'SKILL.md'])
def test_dynamic_overwrite_rejects_linked_package_files(tmp_path, filename):
    import os
    target = tmp_path / 'existing_skill'
    target.mkdir()
    sentinel = tmp_path / 'sentinel.txt'
    sentinel.write_text('DO NOT OVERWRITE')
    os.link(sentinel, target / filename)
    generator = DynamicSkillSynthesizer(skills_dir=tmp_path)
    with pytest.raises(ValueError, match='linked'):
        generator.synthesize_skill(name='existing_skill', code='def execute():\n    return 1',
                                   overwrite=True, dry_run=False)
    assert sentinel.read_text() == 'DO NOT OVERWRITE'


def test_atomic_skill_write_retries_windows_file_lock(tmp_path, monkeypatch):
    from pathlib import Path
    target = tmp_path / 'output.py'
    target.write_text('original')
    attempts = []
    original_replace = Path.replace

    def temporarily_locked(source, destination):
        attempts.append(destination)
        if len(attempts) < 3:
            raise PermissionError('file locked')
        return original_replace(source, destination)

    monkeypatch.setattr(Path, 'replace', temporarily_locked)
    DynamicSkillSynthesizer._write_atomic(target, 'updated')
    assert len(attempts) == 3
    assert target.read_text() == 'updated'
    assert list(tmp_path.glob('*.tmp.*')) == []


def test_atomic_skill_write_failure_preserves_original(tmp_path, monkeypatch):
    from pathlib import Path
    target = tmp_path / 'output.py'
    target.write_text('original')
    attempts = []

    def locked(source, destination):
        attempts.append(destination)
        raise PermissionError('file locked')

    monkeypatch.setattr(Path, 'replace', locked)
    with pytest.raises(PermissionError):
        DynamicSkillSynthesizer._write_atomic(target, 'updated')
    assert len(attempts) == 5
    assert target.read_text() == 'original'
    assert list(tmp_path.glob('*.tmp.*')) == []
