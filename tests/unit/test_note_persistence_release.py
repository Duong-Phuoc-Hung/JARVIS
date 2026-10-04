"""Persistence regressions using temporary notes, never the user's notebook."""
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest

from jarvis.skills import note_taker


@pytest.fixture
def notebook(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    folder = tmp_path / 'JARVIS'
    folder.mkdir()
    return folder / 'notes.json'


@pytest.mark.parametrize('original', ['{broken', '{}', '[null]'])
def test_corrupt_notebook_is_not_overwritten(notebook, original):
    notebook.write_text(original, encoding='utf-8')
    with pytest.raises((ValueError, RuntimeError)):
        note_taker.execute(action='add', content='new note')
    assert notebook.read_text(encoding='utf-8') == original


def test_failed_replace_preserves_previous_notes_and_cleans_temp(notebook):
    original = '[{"id":1,"content":"keep"}]'
    notebook.write_text(original, encoding='utf-8')
    with patch.object(Path, 'replace', side_effect=PermissionError('locked')):
        with pytest.raises(PermissionError):
            note_taker.execute(action='add', content='not committed')
    assert notebook.read_text(encoding='utf-8') == original
    assert list(notebook.parent.glob('*.tmp.*')) == []


def test_transient_replace_lock_retries_and_persists(notebook):
    notebook.write_text('[]', encoding='utf-8')
    replace = Path.replace
    attempts = []

    def transient(source, target):
        attempts.append(source)
        if len(attempts) < 3:
            raise PermissionError('locked')
        return replace(source, target)

    with patch.object(Path, 'replace', transient):
        result = note_taker.execute(action='add', content='retained')
    assert result['data']['success']
    assert len(attempts) == 3
    assert json.loads(notebook.read_text(encoding='utf-8'))[0]['content'] == 'retained'


def test_concurrent_adds_do_not_lose_notes(notebook):
    notebook.write_text('[]', encoding='utf-8')
    load = note_taker._load_notes

    def slow_load():
        data = load()
        time.sleep(0.01)
        return data

    with patch.object(note_taker, '_load_notes', slow_load), ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda i: note_taker.execute(content=f'note {i}'), range(12)))
    assert all(result['data']['success'] for result in results)
    saved = json.loads(notebook.read_text(encoding='utf-8'))
    assert len(saved) == 12
    assert len({note['id'] for note in saved}) == 12
