#!/usr/bin/env python
"""
scripts/health_check_report.py
================================
Generate a Markdown health report and JSON status snapshot.
Usage: python scripts/health_check_report.py

Outputs:
  reports/health_YYYYMMDD_HHMMSS.md  — Human-readable Markdown report
  reports/version_status.json         — Machine-readable version snapshot
"""
from __future__ import annotations

import datetime
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
REPORTS_DIR = ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def run_health_check() -> dict:
    """Run health check and return results dict."""
    try:
        _cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        result = subprocess.run(
            [sys.executable, "-m", "jarvis", "health-check", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=ROOT,
            creationflags=_cflags,
        )
        raw = result.stdout.strip()
        if raw:
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1:
                data = json.loads(raw[start : end + 1])
                return data.get("subsystems", data)
    except Exception:
        pass
    return {}


def run_test_count() -> dict:
    """Run pytest in collect-only mode to count tests."""
    try:
        _cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/unit/", "--collect-only"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=ROOT,
            creationflags=_cflags,
        )
        lines = result.stdout.splitlines()
        for line in reversed(lines):
            line_str = line.strip()
            if "test" in line_str and ("collected" in line_str or "selected" in line_str or "passed" in line_str):
                return {"raw": line_str}
    except Exception:
        pass
    return {}


def get_version() -> str:
    """Extract version from jarvis package or jarvis/__init__.py."""
    try:
        import jarvis

        return getattr(jarvis, "__version__", "unknown")
    except Exception:
        pass
    try:
        init = (ROOT / "jarvis" / "__init__.py").read_text(encoding="utf-8")
        for line in init.splitlines():
            line_s = line.strip()
            if line_s.startswith("__version__") and "=" in line_s:
                return line_s.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return "unknown"


def get_new_module_status() -> list:
    """Check which core and extended modules exist and can be imported."""
    modules = [
        ("jarvis.audio.vad", "VAD Engine"),
        ("jarvis.audio.fullduplex", "Full-Duplex Barge-in"),
        ("jarvis.audio.sound_effects", "Stark UI Sound Effects"),
        ("jarvis.audio.bluetooth_profile", "Bluetooth DAC Audio Optimizer"),
        ("jarvis.tts.piper", "Piper TTS Offline"),
        ("jarvis.tts.vieneu", "VieNeu TTS Neural Synthesis"),
        ("jarvis.stt.faster_whisper", "Faster-Whisper STT"),
        ("jarvis.memory.vector_store", "Semantic Vector Store"),
        ("jarvis.workers.night_shift", "Night Shift Worker"),
        ("jarvis.proactive.night_shift", "Battery & Sleep Sensing"),
        ("jarvis.comms.discord", "Discord Bot Controller"),
        ("jarvis.comms.telegram", "Telegram Voice & Bot Client"),
        ("jarvis.comms.mobile_bridge", "Mobile File Bridge"),
        ("jarvis.automation.zalo_client", "Zalo Desktop Automation"),
        ("jarvis.smart_home.discovery", "Smart Home Discovery"),
        ("jarvis.security.path_guard", "Filesystem Path Guard"),
        ("jarvis.llm.ollama_client", "Ollama Local LLM Acceleration"),
    ]
    skills = [
        ("jarvis.skills.screen_context", "Screen Context AI"),
        ("jarvis.skills.macro_recorder", "Voice Macro Recorder"),
        ("jarvis.skills.skill_synthesizer", "Self-Coding Synthesizer"),
        ("jarvis.skills.rag_search", "Semantic RAG Search"),
        ("jarvis.skills.night_planner", "Night Planner"),
        ("jarvis.skills.smart_home_discovery", "Smart Home Discovery"),
        ("jarvis.skills.sound_board", "Sound Board"),
    ]

    results = []
    for mod_path, display in modules + skills:
        try:
            __import__(mod_path)
            status = "✅ READY"
        except ImportError as e:
            if "faster_whisper" in str(e) or "piper" in str(e) or "onnx" in str(e):
                status = "⚠️ OPTIONAL DEP"
            else:
                status = f"❌ ERROR: {e}"
        except Exception as e:
            status = f"⚠️ WARNING: {str(e)[:60]}"
        results.append({"module": mod_path, "display": display, "status": status})
    return results


def build_markdown_report(
    health_data: dict,
    module_status: list,
    test_info: dict,
    version: str,
    ts: str,
) -> str:
    ready = sum(1 for v in health_data.values() if isinstance(v, dict) and v.get("status") == "ready")
    total = len(health_data)
    mod_ready = sum(1 for m in module_status if "✅" in m["status"])
    mod_total = len(module_status)

    lines = [
        "# 🤖 JARVIS Health Report",
        "",
        f"**Generated:** {ts}  |  **Version:** {version}",
        f"**Subsystems:** {ready}/{total} READY  |  **Architecture Modules:** {mod_ready}/{mod_total} READY",
        "",
        "---",
        "",
        f"## 🧩 Core & Modern Architecture Modules (v{version})",
        "",
        "| Module | Display Name | Status |",
        "|--------|-------------|--------|",
    ]
    for m in module_status:
        lines.append(f"| `{m['module'].split('.')[-1]}` | {m['display']} | {m['status']} |")

    if health_data:
        lines += ["", "## 🩺 Core Subsystem Health", "", "| Subsystem | Status | Detail |", "|-----------|--------|--------|"]
        for name, data in health_data.items():
            if isinstance(data, dict):
                st = data.get("status", "unknown")
                detail = data.get("message", data.get("detail", ""))[:80]
                icon = "✅" if st == "ready" else "⚠️" if st == "warning" else "❌"
                lines.append(f"| {name} | {icon} {st.upper()} | {detail} |")

    if test_info.get("raw"):
        lines += ["", "## 🧪 Tests", "", "```", test_info["raw"], "```"]

    lines += [
        "",
        "---",
        "*JARVIS Health Check Report — auto-generated*",
    ]
    return "\n".join(lines)


def main():
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ts_file = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"[JARVIS Health Report] {ts}")

    print("  -> Running health check...")
    health_data = run_health_check()

    print("  -> Counting tests...")
    test_info = run_test_count()

    print("  -> Checking new modules...")
    module_status = get_new_module_status()

    version = get_version()

    report_md = build_markdown_report(health_data, module_status, test_info, version, ts)
    report_path = REPORTS_DIR / f"health_{ts_file}.md"
    report_path.write_text(report_md, encoding="utf-8")
    print(f"  ✅ Markdown report: {report_path}")

    mod_ready = sum(1 for m in module_status if "✅" in m["status"])
    ready = sum(1 for v in health_data.values() if isinstance(v, dict) and v.get("status") == "ready")

    status_json = {
        "version": version,
        "generated_at": ts,
        "ready_subsystems": ready,
        "total_subsystems": len(health_data),
        "new_modules_ready": mod_ready,
        "new_modules_total": len(module_status),
        "test_summary": test_info.get("raw", "N/A"),
        "modules": module_status,
    }
    status_path = REPORTS_DIR / "version_status.json"
    status_path.write_text(json.dumps(status_json, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  ✅ JSON status: {status_path}")
    print(f"\n  Summary: {ready}/{len(health_data)} subsystems READY | {mod_ready}/{len(module_status)} new modules READY")


if __name__ == "__main__":
    main()
