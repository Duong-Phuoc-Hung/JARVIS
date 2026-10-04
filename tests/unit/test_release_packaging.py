"""Voice dependencies must survive installation on a clean machine."""
import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_audio_dependencies_include_default_tts_and_decoder():
    text = (ROOT / 'pyproject.toml').read_text(encoding='utf-8')
    assert '"edge-tts>=7.2,<8"' in text
    assert '"soundfile>=0.13,<1"' in text
    assert '"openwakeword>=0.6,<1"' in text


def test_generated_spec_bundles_voice_assets_and_keeps_scipy(tmp_path):
    spec = importlib.util.spec_from_file_location('release_builder', ROOT / 'scripts/build_installer.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.SPEC_FILE = tmp_path / 'JARVIS.spec'
    module._generate_spec_file()
    source = module.SPEC_FILE.read_text(encoding='utf-8')
    compile(source, str(module.SPEC_FILE), 'exec')
    assert 'collect_data_files("openwakeword")' in source
    assert 'collect_submodules("edge_tts")' in source
    assert '"soundfile"' in source
    assert 'excludes=["matplotlib", "scipy"' not in source


@pytest.mark.parametrize('exe_ok,installer_ok,expected', [(True, False, 1), (False, True, 1), (True, True, 0)])
def test_full_build_requires_both_artifacts(monkeypatch, exe_ok, installer_ok, expected):
    spec = importlib.util.spec_from_file_location('release_builder_exit', ROOT / 'scripts/build_installer.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr('sys.argv', ['build_installer.py', '--skip-tests', '--no-clean'])
    monkeypatch.setattr(module, 'build_exe', Mock(return_value=exe_ok))
    monkeypatch.setattr(module, 'build_installer', Mock(return_value=installer_ok))
    monkeypatch.setattr(module, 'print_summary', Mock())
    with pytest.raises(SystemExit) as result:
        module.main()
    assert result.value.code == expected
