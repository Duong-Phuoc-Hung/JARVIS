"""
Unit Tests for Natural Language Shell Assistant (Milestone 4 - R7).
"""
import json
import os
import subprocess
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from jarvis.automation.safety_gate import SafetyGate
from jarvis.automation.shell_assistant import ShellAssistant


@pytest.fixture
def safety_gate():
    return SafetyGate(timeout_seconds=10.0)


@pytest.fixture
def assistant(safety_gate):
    return ShellAssistant(safety_gate=safety_gate)


# ===========================================================================
# 1. Dev Server Detection Tests
# ===========================================================================
def test_resolve_dev_server_nodejs_with_dev_script(assistant):
    with tempfile.TemporaryDirectory() as tmpdir:
        pkg_json = os.path.join(tmpdir, "package.json")
        with open(pkg_json, "w", encoding="utf-8") as f:
            json.dump({"name": "my-app", "scripts": {"dev": "vite", "build": "vite build"}}, f)

        cmd = assistant.resolve_dev_server_command(tmpdir)
        assert cmd == "npm run dev"


def test_resolve_dev_server_nodejs_with_start_script(assistant):
    with tempfile.TemporaryDirectory() as tmpdir:
        pkg_json = os.path.join(tmpdir, "package.json")
        with open(pkg_json, "w", encoding="utf-8") as f:
            json.dump({"name": "my-backend", "scripts": {"start": "node index.js"}}, f)

        cmd = assistant.resolve_dev_server_command(tmpdir)
        assert cmd == "npm start"


def test_resolve_dev_server_django(assistant):
    with tempfile.TemporaryDirectory() as tmpdir:
        manage_py = os.path.join(tmpdir, "manage.py")
        open(manage_py, "w").close()

        cmd = assistant.resolve_dev_server_command(tmpdir)
        assert cmd == "python manage.py runserver"


def test_resolve_dev_server_fastapi_uvicorn(assistant):
    with tempfile.TemporaryDirectory() as tmpdir:
        main_py = os.path.join(tmpdir, "main.py")
        with open(main_py, "w", encoding="utf-8") as f:
            f.write("from fastapi import FastAPI\napp = FastAPI()\n")

        cmd = assistant.resolve_dev_server_command(tmpdir)
        assert cmd == "uvicorn main:app --reload"


def test_resolve_dev_server_flask(assistant):
    with tempfile.TemporaryDirectory() as tmpdir:
        app_py = os.path.join(tmpdir, "app.py")
        with open(app_py, "w", encoding="utf-8") as f:
            f.write("from flask import Flask\napp = Flask(__name__)\n")

        cmd = assistant.resolve_dev_server_command(tmpdir)
        assert cmd == "python app.py"


def test_resolve_dev_server_rust_and_go(assistant):
    with tempfile.TemporaryDirectory() as tmpdir:
        cargo = os.path.join(tmpdir, "Cargo.toml")
        open(cargo, "w").close()
        assert assistant.resolve_dev_server_command(tmpdir) == "cargo run"

    with tempfile.TemporaryDirectory() as tmpdir:
        gomod = os.path.join(tmpdir, "go.mod")
        open(gomod, "w").close()
        assert assistant.resolve_dev_server_command(tmpdir) == "go run ."


# ===========================================================================
# 2. Natural Language Translation Tests
# ===========================================================================
def test_translate_dev_server_command(assistant):
    with tempfile.TemporaryDirectory() as tmpdir:
        pkg = os.path.join(tmpdir, "package.json")
        with open(pkg, "w", encoding="utf-8") as f:
            json.dump({"scripts": {"dev": "next dev"}}, f)

        cmd, cat = assistant.translate_nl_command("JARVIS, hãy chạy server", cwd=tmpdir)
        assert cmd == "npm run dev"
        assert cat == "dev_server"


def test_translate_git_status_command(assistant):
    cmd, cat = assistant.translate_nl_command("kiểm tra trạng thái git")
    assert cmd == "git status"
    assert cat == "git_status"


def test_translate_package_install_pip_and_npm(assistant):
    with tempfile.TemporaryDirectory() as tmpdir:
        cmd, cat = assistant.translate_nl_command("cài đặt package requests", cwd=tmpdir)
        assert cmd == "pip install requests"
        assert cat == "package_install"

        # If node package.json exists
        with open(os.path.join(tmpdir, "package.json"), "w") as f:
            json.dump({}, f)

        cmd_npm, _ = assistant.translate_nl_command("install package axios", cwd=tmpdir)
        assert cmd_npm == "npm install axios"


def test_translate_docker_and_port_commands(assistant):
    cmd, cat = assistant.translate_nl_command("restart docker")
    assert "docker restart" in cmd
    assert cat == "docker_restart"

    cmd_port, cat_port = assistant.translate_nl_command("kiểm tra port 8080")
    assert "findstr :8080" in cmd_port
    assert cat_port == "port_check"


# ===========================================================================
# 3. Git Status Parser & Summarizer Tests
# ===========================================================================
def test_parse_git_status_short_format(assistant):
    short_output = """## main...origin/main [ahead 1]
 M jarvis/core/app.py
 M tests/test_core.py
?? jarvis/automation/control.py
A  jarvis/automation/safety_gate.py
"""
    summary = assistant.parse_git_status_output(short_output)
    assert "Nhánh main" in summary
    assert "1 tệp đã sẵn sàng commit" in summary
    assert "2 tệp đã chỉnh sửa" in summary
    assert "1 tệp chưa theo dõi" in summary


def test_parse_git_status_clean_working_tree(assistant):
    output = "On branch develop\nnothing to commit, working tree clean"
    summary = assistant.parse_git_status_output(output)
    assert "Nhánh develop" in summary
    assert "Working tree sạch" in summary


def test_parse_git_status_long_format(assistant):
    long_output = """On branch master
Changes not staged for commit:
  (use "git add <file>..." to update what will be committed)
	modified:   README.md
	deleted:    old_doc.txt

Untracked files:
  (use "git add <file>..." to include in what will be committed)
	new_feature.py
"""
    summary = assistant.parse_git_status_output(long_output)
    assert "Nhánh master" in summary
    assert "1 tệp đã chỉnh sửa" in summary
    assert "1 tệp đã xóa" in summary
    assert "1 tệp chưa theo dõi" in summary


# ===========================================================================
# 4. Port Inspector Tests
# ===========================================================================
def test_check_port_listening(assistant):
    mock_netstat = "  TCP    0.0.0.0:8080           0.0.0.0:0              LISTENING       15420\n"
    with patch("subprocess.run") as mock_run:
        # Mock netstat
        res_netstat = MagicMock()
        res_netstat.stdout = mock_netstat
        # Mock tasklist
        res_tasklist = MagicMock()
        res_tasklist.stdout = '"python.exe","15420","Console","1","54,320 K"\n'
        mock_run.side_effect = [res_netstat, res_tasklist]

        result = assistant.check_port(8080)
        assert "Port 8080 đang mở ở trạng thái LISTENING" in result
        assert "python.exe" in result
        assert "PID 15420" in result


def test_check_port_free(assistant):
    with patch("subprocess.run") as mock_run:
        res = MagicMock()
        res.stdout = "  TCP    0.0.0.0:3000           0.0.0.0:0              LISTENING       1234\n"
        mock_run.return_value = res

        result = assistant.check_port(9000)
        assert "Port 9000 hiện đang rảnh" in result


# ===========================================================================
# 5. Destructive Command Safety Filter Tests
# ===========================================================================
@pytest.mark.parametrize(
    "cmd",
    [
        "rm -rf /var/log",
        "rm -r ./dist",
        "rmdir /s /q C:\\test",
        "del /f /s /q *.*",
        "format d:",
        "drop database production",
        "delete from users",
        "truncate table events",
        "taskkill /f /im explorer.exe",
        "git reset --hard HEAD~1",
        "git clean -fd",
        "Remove-Item -Path $env:TEMP -Recurse",
        "shutil.rmtree('/tmp/dir')",
    ],
)
def test_destructive_commands_detected(assistant, cmd):
    assert assistant.is_destructive(cmd) is True


@pytest.mark.parametrize(
    "cmd",
    [
        "npm start",
        "python manage.py runserver",
        "git status",
        "git log -n 5",
        "pip install requests",
        "docker ps",
        "netstat -ano",
        "python main.py",
        "echo Hello World",
        "dir C:\\Users",
    ],
)
def test_safe_commands_allowed(assistant, cmd):
    assert assistant.is_destructive(cmd) is False


# ===========================================================================
# 6. Stdout Summarizer (> 10 lines) Tests
# ===========================================================================
def test_summarize_output_short_less_than_10_lines(assistant):
    short_text = "Line 1\nLine 2\nLine 3"
    summary = assistant.summarize_output("echo test", short_text)
    assert summary == short_text


def test_summarize_output_generic_more_than_10_lines(assistant):
    long_lines = [f"Step {i}: Processing component {i}..." for i in range(1, 25)]
    raw_stdout = "\n".join(long_lines)

    summary = assistant.summarize_output("build_project.bat", raw_stdout, exit_code=0)
    assert "24 dòng kết quả" in summary
    assert "Step 1" in summary
    assert "Step 24" in summary
    assert "thưa Ngài" in summary


def test_summarize_output_pip_install_more_than_10_lines(assistant):
    pip_lines = [f"Collecting dep-{i}..." for i in range(15)]
    pip_lines.append("Successfully installed dep-1 dep-2 dep-3")
    raw_stdout = "\n".join(pip_lines)

    summary = assistant.summarize_output("pip install mypkg", raw_stdout, exit_code=0)
    assert "Cài đặt gói thành công" in summary
    assert "Successfully installed" in summary


def test_summarize_output_pytest_more_than_10_lines(assistant):
    pytest_lines = [f"test_{i}.py ." for i in range(15)]
    pytest_lines.append("=== 15 passed, 0 failed in 1.45s ===")
    raw_stdout = "\n".join(pytest_lines)

    summary = assistant.summarize_output("pytest tests/", raw_stdout, exit_code=0)
    assert "Kết quả kiểm thử" in summary
    assert "15 passed" in summary


# ===========================================================================
# 7. Execute Natural Command Tests
# ===========================================================================
def test_execute_destructive_command_requires_confirmation(assistant, safety_gate):
    res = assistant.execute_natural_command("rm -rf node_modules")
    assert res["success"] is False
    assert res["requires_confirmation"] is True
    assert "token" in res
    assert safety_gate.is_pending(res["token"]) is True
    assert "Cảnh báo" in res["message"]


def test_execute_safe_command(assistant):
    with patch("subprocess.run") as mock_run:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "Python 3.13.2"
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        res = assistant.execute_natural_command("python --version")
        assert res["success"] is True
        assert res["requires_confirmation"] is False
        assert res["stdout"] == "Python 3.13.2"
        assert res["summary"] == "Python 3.13.2"
