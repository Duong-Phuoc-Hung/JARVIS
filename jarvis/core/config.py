"""
ConfigManager: Multi-source hierarchy configuration with dot-notation and thread-safe hot reloading.
"""
from __future__ import annotations

import copy
import json
import logging
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

try:
    import tomllib
    HAS_TOMLLIB = True
except ImportError:
    HAS_TOMLLIB = False

try:
    from dotenv import load_dotenv
    HAS_DOTENV = True
except ImportError:
    HAS_DOTENV = False

log = logging.getLogger("jarvis.core.config")

# Legacy environment variable to internal dot-notation key mapping
LEGACY_ENV_MAPPING: dict[str, tuple[str, type]] = {
    "ELEVENLABS_API_KEY": ("tts.elevenlabs.api_key", str),
    "ELEVENLABS_VOICE_ID": ("tts.elevenlabs.voice_id", str),
    "ELEVENLABS_MODEL_ID": ("tts.elevenlabs.model_id", str),
    "ELEVENLABS_OUTPUT_FORMAT": ("tts.elevenlabs.output_format", str),
    "ELEVENLABS_PCM_SAMPLE_RATE": ("tts.elevenlabs.sample_rate", int),
    "JARVIS_WELCOME_CACHE_DIR": ("tts.cache.dir", str),
    "JARVIS_INPUT_DEVICE": ("audio.input_device", str),
    "JARVIS_SPIKE_RATIO": ("audio.spike_ratio", float),
    "CLAUDE_CODE_URL": ("plugins.chrome.claude_url", str),
    "BINANCE_BTC_URL": ("plugins.chrome.binance_url", str),
    "CHROME_NEW_WINDOW_WAIT_S": ("plugins.chrome.wait_timeout_s", float),
    "CHROME_WINDOW_WIDTH": ("plugins.chrome.window_width", int),
    "CHROME_WINDOW_HEIGHT": ("plugins.chrome.window_height", int),
    "SONG_URI": ("plugins.spotify.song_uri", str),
    "JARVIS_WELCOME_ENABLED": ("tts.welcome.enabled", bool),
    "JARVIS_WELCOME_PHRASE": ("tts.welcome.phrase", str),
    "JARVIS_AFTER_SONG_DELAY_S": ("tts.welcome.delay_after_song_s", float),
    "JARVIS_WELCOME_CACHE_ENABLED": ("tts.cache.enabled", bool),
    "FOCUS_EXISTING_CURSOR_ON_DOUBLE_CLAP": ("plugins.cursor.focus_existing", bool),
    "OPEN_NEW_CURSOR_ON_DOUBLE_CLAP": ("plugins.cursor.open_new", bool),
    "CURSOR_OPEN_FULLSCREEN": ("plugins.cursor.fullscreen", bool),
    "OPEN_CLAUDE_CODE_IN_CHROME": ("plugins.chrome.open_claude", bool),
    "OPEN_BINANCE_BTC_IN_CHROME": ("plugins.chrome.open_binance", bool),
    "OPEN_CHROME_FULLSCREEN": ("plugins.chrome.fullscreen", bool),
    "CHROME_SEPARATE_SITE_PROFILES": ("plugins.chrome.separate_profiles", bool),
    "CLAUDE_CHROME_MONITOR": ("windows.claude_monitor", int),
    "BINANCE_CHROME_MONITOR": ("windows.binance_monitor", int),
    "GEMINI_API_KEY": ("vision.gemini_api_key", str),
    "OPENAI_API_KEY": ("llm.api_key", str),
    "OPENWEATHER_API_KEY": ("web.weather_api_key", str),
    "WEATHER_API_KEY": ("web.weather_api_key", str),
    "JARVIS_MEMORY_DB": ("memory.db_path", str),
    "PORCUPINE_ACCESS_KEY": ("audio.wake_word.porcupine_access_key", str),
    "JARVIS_VOSK_MODEL": ("audio.wake_word.vosk_model_path", str),
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge override dictionary into base dictionary."""
    result = copy.deepcopy(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = copy.deepcopy(val)
    return result


def _parse_bool(val: str | bool | int) -> bool:
    """Parse boolean value from various string representations."""
    if isinstance(val, bool):
        return val
    if isinstance(val, int):
        return bool(val)
    return str(val).strip().lower() in ("true", "1", "yes", "on", "t")


def _parse_scalar(val_str: str) -> Any:
    """Parse primitive scalar value from string."""
    s = val_str.strip()
    if not s:
        return ""
    if s.lower() in ("true", "yes", "on"):
        return True
    if s.lower() in ("false", "no", "off"):
        return False
    if s.lower() in ("null", "none", "~"):
        return None
    if s.startswith('"') and s.endswith('"') and len(s) >= 2:
        return s[1:-1].encode().decode("unicode_escape", errors="ignore")
    if s.startswith("'") and s.endswith("'") and len(s) >= 2:
        return s[1:-1]
    if s.startswith("[") and s.endswith("]"):
        try:
            return json.loads(s)
        except Exception:
            items = [x.strip() for x in s[1:-1].split(",") if x.strip()]
            return [_parse_scalar(x) for x in items]
    if s.startswith("{") and s.endswith("}"):
        try:
            return json.loads(s)
        except Exception:
            pass

    # Try integer
    try:
        if s.startswith("0x") or s.startswith("0X"):
            return int(s, 16)
        return int(s)
    except ValueError:
        pass

    # Try float
    try:
        return float(s)
    except ValueError:
        pass

    return s


def _simple_yaml_parse(text: str) -> dict[str, Any]:
    """
    Pure-Python indentation-aware YAML parser supporting mappings, lists, scalars, comments.
    Guarantees zero external dependency crash when PyYAML is unavailable.
    """
    lines = text.splitlines()

    def parse_block(line_idx: int, min_indent: int) -> tuple[Any, int]:
        result_dict: dict[str, Any] = {}
        result_list: list[Any] = []
        is_list_context = False

        while line_idx < len(lines):
            raw_line = lines[line_idx]
            comment_pos = -1
            in_single = False
            in_double = False
            for i, c in enumerate(raw_line):
                if c == "'" and not in_double:
                    in_single = not in_single
                elif c == '"' and not in_single:
                    in_double = not in_double
                elif c == '#' and not in_single and not in_double:
                    comment_pos = i
                    break
            if comment_pos != -1:
                cleaned_line = raw_line[:comment_pos].rstrip()
            else:
                cleaned_line = raw_line.rstrip()

            if not cleaned_line.strip():
                line_idx += 1
                continue

            indent = len(cleaned_line) - len(cleaned_line.lstrip())
            if indent < min_indent:
                break

            stripped = cleaned_line.strip()

            if stripped.startswith(":") or (stripped.count("[") != stripped.count("]")):
                raise ValueError(f"Invalid YAML syntax at line {line_idx + 1}: '{raw_line}'")

            # Check if list item
            if stripped.startswith("-"):
                is_list_context = True
                content = stripped[1:].strip()
                if not content:
                    nested_val, next_idx = parse_block(line_idx + 1, indent + 1)
                    result_list.append(nested_val)
                    line_idx = next_idx
                    continue
                elif ":" in content and not (content.startswith('"') or content.startswith("'")):
                    k, v = content.split(":", 1)
                    k = k.strip()
                    v = v.strip()
                    if not k:
                        raise ValueError(f"Empty key in list mapping at line {line_idx + 1}")
                    if v:
                        result_list.append({k: _parse_scalar(v)})
                        line_idx += 1
                    else:
                        sub_val, next_idx = parse_block(line_idx + 1, indent + 2)
                        result_list.append({k: sub_val})
                        line_idx = next_idx
                    continue
                else:
                    result_list.append(_parse_scalar(content))
                    line_idx += 1
                    continue

            # Dict entry: key: value
            if ":" in stripped:
                colon_pos = stripped.find(":")
                key = stripped[:colon_pos].strip()
                if not key:
                    raise ValueError(f"Invalid key before colon at line {line_idx + 1}: '{raw_line}'")
                if (key.startswith('"') and key.endswith('"')) or (key.startswith("'") and key.endswith("'")):
                    key = key[1:-1]
                val_part = stripped[colon_pos + 1:].strip()

                if not val_part:
                    nested_val, next_idx = parse_block(line_idx + 1, indent + 1)
                    result_dict[key] = nested_val
                    line_idx = next_idx
                    continue
                elif val_part in ("|", ">"):
                    multiline_lines = []
                    curr_idx = line_idx + 1
                    block_indent = None
                    while curr_idx < len(lines):
                        m_line = lines[curr_idx]
                        if not m_line.strip():
                            multiline_lines.append("")
                            curr_idx += 1
                            continue
                        m_indent = len(m_line) - len(m_line.lstrip())
                        if block_indent is None:
                            if m_indent <= indent:
                                break
                            block_indent = m_indent
                        elif m_indent < block_indent:
                            break
                        multiline_lines.append(m_line[block_indent:])
                        curr_idx += 1
                    result_dict[key] = "\n".join(multiline_lines).strip()
                    line_idx = curr_idx
                    continue
                else:
                    result_dict[key] = _parse_scalar(val_part)
                    line_idx += 1
                    continue

            raise ValueError(f"Unrecognized syntax at line {line_idx + 1}: '{raw_line}'")

        if is_list_context and not result_dict:
            return result_list, line_idx
        return result_dict, line_idx

    parsed, _ = parse_block(0, 0)
    return parsed if isinstance(parsed, dict) else {}


# ---------------------------------------------------------------------------
# Structured Configuration Models & Node Wrappers
# ---------------------------------------------------------------------------

class ConfigNode:
    """Wrapper that enables both attribute and dictionary access."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self._data = data or {}
        for k, v in list(self._data.items()):
            if isinstance(v, dict):
                setattr(self, k, ConfigNode(v))
            else:
                setattr(self, k, v)

    def __getitem__(self, item: str) -> Any:
        return self._data[item]

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value
        if isinstance(value, dict):
            setattr(self, key, ConfigNode(value))
        else:
            setattr(self, key, value)

    def __contains__(self, item: str) -> bool:
        return item in self._data

    def __getattr__(self, name: str) -> Any:
        if name in self._data:
            val = self._data[name]
            if isinstance(val, dict):
                return ConfigNode(val)
            return val
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def to_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self._data)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._data!r})"


class AudioConfig(ConfigNode):
    def __init__(self, data: dict[str, Any] | None = None) -> None:
        defaults = {
            "sample_rate": 44100,
            "block_ms": 40,
            "channels": 1,
            "spike_ratio": 7.0,
            "cooldown_s": 0.45,
            "min_rms": 0.012,
            "quiet_gate_mult": 2.2,
            "retrigger_ratio": 0.55,
            "noise_floor_alpha": 0.992,
            "input_device": "",
            "silent_rms_threshold": 0.001,
        }
        if data:
            defaults.update(data)
        super().__init__(defaults)


class TTSConfig(ConfigNode):
    def __init__(self, data: dict[str, Any] | None = None) -> None:
        defaults = {
            "provider": "elevenlabs",
            "welcome_enabled": True,
            "voice_id": "",
            "model_id": "eleven_multilingual_v2",
            "elevenlabs_api_key": "",
            "sample_rate": 24000,
        }
        if data:
            defaults.update(data)
            if "elevenlabs" in data and isinstance(data["elevenlabs"], dict):
                el = data["elevenlabs"]
                if "api_key" in el:
                    defaults["elevenlabs_api_key"] = el["api_key"]
                if "voice_id" in el:
                    defaults["voice_id"] = el["voice_id"]
                if "model_id" in el:
                    defaults["model_id"] = el["model_id"]
        super().__init__(defaults)


class WindowsConfig(ConfigNode):
    def __init__(self, data: dict[str, Any] | None = None) -> None:
        defaults = {
            "claude_monitor": 1,
            "binance_monitor": 3,
            "open_claude": True,
            "open_binance": True,
        }
        if data:
            defaults.update(data)
        super().__init__(defaults)


class LoggingConfig(ConfigNode):
    def __init__(self, data: dict[str, Any] | None = None) -> None:
        defaults = {
            "level": "INFO",
            "file": "logs/jarvis.log",
            "max_bytes": 10485760,
            "backup_count": 5,
            "console_colors": True,
        }
        if data:
            defaults.update(data)
        super().__init__(defaults)


class WakeWordConfig(ConfigNode):
    def __init__(self, data: dict[str, Any] | None = None) -> None:
        defaults = {
            "enabled": True,
            "sensitivity": 0.35,
            "cooldown_s": 2.0,
            "min_rms": 0.02,
            "vosk_model_path": "",
        }
        if data:
            defaults.update(data)
        super().__init__(defaults)


class MemoryConfig(ConfigNode):
    def __init__(self, data: dict[str, Any] | None = None) -> None:
        defaults = {
            "enabled": True,
            "db_path": "logs/memory.db",
            "max_session_turns": 10,
        }
        if data:
            defaults.update(data)
        super().__init__(defaults)


class VisionConfig(ConfigNode):
    def __init__(self, data: dict[str, Any] | None = None) -> None:
        defaults = {
            "enabled": True,
            "provider": "gemini",
            "gemini_model": "gemini-1.5-flash",
            "openai_model": "gpt-4o",
            "timeout_s": 10.0,
            "max_dim": 1920,
        }
        if data:
            defaults.update(data)
        super().__init__(defaults)


class WebConfig(ConfigNode):
    def __init__(self, data: dict[str, Any] | None = None) -> None:
        defaults = {
            "enabled": True,
            "cache_ttl_s": 600.0,
            "default_city": "Hà Nội",
            "weather_api_key": "",
        }
        if data:
            defaults.update(data)
        super().__init__(defaults)


class AutomationConfig(ConfigNode):
    def __init__(self, data: dict[str, Any] | None = None) -> None:
        defaults = {
            "enabled": True,
            "safety_gate_timeout_s": 30.0,
            "max_search_depth": 4,
        }
        if data:
            defaults.update(data)
        super().__init__(defaults)


class ProactiveConfigNode(ConfigNode):
    def __init__(self, data: dict[str, Any] | None = None) -> None:
        defaults = {
            "enabled": True,
            "reminders": {"enabled": True, "check_interval_s": 0.5},
            "health_monitor": {
                "enabled": True,
                "check_interval_s": 5.0,
                "cpu_threshold": 90.0,
                "ram_threshold": 85.0,
                "disk_min_free_gb": 10.0,
                "temp_threshold_c": 85.0,
                "battery_min_percent": 20.0,
                "cooldown_s": 60.0,
            },
            "pomodoro": {
                "enabled": True,
                "check_interval_s": 0.5,
                "work_duration_m": 25.0,
                "break_duration_m": 5.0,
            },
            "daily_briefing": {
                "enabled": True,
                "time": "08:00",
                "check_interval_s": 10.0,
            },
            "inactivity_greeting": {
                "enabled": True,
                "timeout_seconds": 7200.0,
                "cooldown_seconds": 3600.0,
                "phrase": "Thưa Ngài, Ngài có cần hỗ trợ gì không?",
                "check_interval_s": 10.0,
            },
        }
        if data:
            defaults = _deep_merge(defaults, data)
        super().__init__(defaults)


class OverlayConfig(ConfigNode):
    def __init__(self, data: dict[str, Any] | None = None) -> None:
        defaults = {
            "enabled": True,
            "sidebar_mode": True,
            "sidebar_width": 380,
            "auto_hide_s": 8.0,
        }
        if data:
            defaults.update(data)
        super().__init__(defaults)


class JarvisConfig(ConfigNode):
    """Structured root configuration schema."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        raw = copy.deepcopy(data or {})

        audio_data = copy.deepcopy(raw.get("audio", {}))
        if "gesture" in raw and isinstance(raw["gesture"], dict) and "dsp" in raw["gesture"]:
            dsp = raw["gesture"]["dsp"]
            for k in ("spike_ratio", "cooldown_s", "min_rms", "retrigger_ratio", "noise_floor_alpha", "quiet_gate_mult"):
                if k in dsp and k not in audio_data:
                    audio_data[k] = dsp[k]

        tts_data = copy.deepcopy(raw.get("tts", {}))
        if "welcome" in raw.get("tts", {}) and isinstance(raw["tts"]["welcome"], dict):
            tts_data["welcome_enabled"] = raw["tts"]["welcome"].get("enabled", True)

        windows_data = copy.deepcopy(raw.get("windows", {}))
        if "plugins" in raw and isinstance(raw["plugins"], dict) and "chrome" in raw["plugins"]:
            ch = raw["plugins"]["chrome"]
            if "claude_monitor" in ch and "claude_monitor" not in windows_data:
                windows_data["claude_monitor"] = ch["claude_monitor"]
            if "binance_monitor" in ch and "binance_monitor" not in windows_data:
                windows_data["binance_monitor"] = ch["binance_monitor"]

        super().__init__(raw)
        self.audio = AudioConfig(audio_data)
        self.tts = TTSConfig(tts_data)
        self.windows = WindowsConfig(windows_data)
        self.logging = LoggingConfig(raw.get("logging", {}))
        self.wake_word = WakeWordConfig(raw.get("wake_word", raw.get("audio", {}).get("wake_word", {})))
        self.memory = MemoryConfig(raw.get("memory", {}))
        self.vision = VisionConfig(raw.get("vision", {}))
        self.web = WebConfig(raw.get("web", {}))
        self.automation = AutomationConfig(raw.get("automation", {}))
        self.proactive = ProactiveConfigNode(raw.get("proactive", {}))
        self.overlay = OverlayConfig(raw.get("ui", {}).get("overlay", {}))



# ---------------------------------------------------------------------------
# ConfigManager
# ---------------------------------------------------------------------------

class ConfigManager:
    """
    Thread-safe configuration manager with:
    - Multi-source hierarchy: Default YAML -> Custom YAML/JSON/TOML -> .env / Environment Variables
    - Dot-notation dictionary access (get/set)
    - Background hot-reloading watcher (< 5 seconds) with syntax error isolation
    - Observer callback pattern (on_change / register_reload_callback)
    """

    def __init__(
        self,
        config_path: str | Path | None = None,
        default_config_path: str | Path | None = None,
        env_file_path: str | Path | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._callbacks: list[Callable[[Any], None]] = []

        root_dir = Path(__file__).resolve().parent.parent.parent
        self._default_config_path = Path(default_config_path or (root_dir / "config" / "default_config.yaml"))
        self._config_path = Path(config_path) if config_path else None
        self._env_file_path = Path(env_file_path or (root_dir / ".env"))

        self._data: dict[str, Any] = {}
        self._structured_config: JarvisConfig | None = None
        self._raw_default_data: dict[str, Any] = {}
        self._raw_custom_data: dict[str, Any] = {}

        # Hot reload state
        self._watcher_thread: threading.Thread | None = None
        self._stop_watcher_event = threading.Event()
        self._last_mtime: float = 0.0
        self._active_watch_path: Path | None = None

    def load(self) -> JarvisConfig:
        """Load all configuration layers according to hierarchy."""
        with self._lock:
            # 1. Load .env file (without overriding explicit os.environ values already set)
            if HAS_DOTENV:
                if self._env_file_path.is_file():
                    load_dotenv(dotenv_path=self._env_file_path, override=False)
                else:
                    load_dotenv(override=False)
            else:
                self._load_dotenv_manual(self._env_file_path)

            # 2. Load Default Config
            self._raw_default_data = self._read_file(self._default_config_path)
            merged = copy.deepcopy(self._raw_default_data)

            # 3. Load Custom Config if specified
            if self._config_path and self._config_path.is_file():
                self._raw_custom_data = self._read_file(self._config_path)
                merged = _deep_merge(merged, self._raw_custom_data)
                self._active_watch_path = self._config_path
            else:
                self._active_watch_path = self._default_config_path if self._default_config_path.is_file() else None

            if self._active_watch_path and self._active_watch_path.is_file():
                self._last_mtime = self._active_watch_path.stat().st_mtime

            # 4. Apply Legacy & Explicit Environment Variable Overrides
            self._apply_env_overrides(merged)

            self._data = merged
            self._structured_config = JarvisConfig(merged)
            log.debug("Configuration loaded successfully (%d root keys)", len(self._data))
            return self._structured_config

    def _load_dotenv_manual(self, path: Path) -> None:
        """Manual .env loader when python-dotenv is not installed."""
        if not path.is_file():
            return
        try:
            content = path.read_text(encoding="utf-8")
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip()
                if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                    v = v[1:-1]
                if k not in os.environ:
                    os.environ[k] = v
        except Exception as e:
            log.warning("Could not manually parse .env file '%s': %s", path, e)

    def _read_file(self, path: Path) -> dict[str, Any]:
        """Parse YAML, JSON, or TOML file safely with validation and fallback."""
        if not path.is_file():
            log.warning("Config file not found: %s", path)
            return {}
        try:
            text = path.read_text(encoding="utf-8")
            if not text.strip():
                return {}
            suffix = path.suffix.lower()
            if suffix in (".yaml", ".yml"):
                if HAS_YAML:
                    parsed = yaml.safe_load(text)
                    if parsed is None:
                        return {}
                    if not isinstance(parsed, dict):
                        raise ValueError(f"Expected mapping at root of YAML file '{path}', got {type(parsed).__name__}")
                    return parsed
                else:
                    return _simple_yaml_parse(text)
            elif suffix == ".json":
                parsed = json.loads(text)
                if not isinstance(parsed, dict):
                    raise ValueError(f"Expected JSON object in '{path}', got {type(parsed).__name__}")
                return parsed
            elif suffix == ".toml" and HAS_TOMLLIB:
                return tomllib.loads(text)
            else:
                if HAS_YAML:
                    try:
                        parsed = yaml.safe_load(text)
                        if isinstance(parsed, dict):
                            return parsed
                    except Exception:
                        pass
                try:
                    return json.loads(text)
                except Exception:
                    return _simple_yaml_parse(text)
        except Exception as e:
            log.error("Failed to parse config file '%s': %s", path, e)
            raise ValueError(f"Config syntax error in {path}: {e}") from e

    def _apply_env_overrides(self, target: dict[str, Any]) -> None:
        """Map OS environment variables into target dict."""
        for env_key, (dot_key, expected_type) in LEGACY_ENV_MAPPING.items():
            val = os.environ.get(env_key)
            if val is not None and val.strip() != "":
                val_str = val.strip()
                try:
                    if expected_type is bool:
                        typed_val: Any = _parse_bool(val_str)
                    elif expected_type is int:
                        typed_val = int(val_str)
                    elif expected_type is float:
                        typed_val = float(val_str)
                    else:
                        typed_val = val_str
                    self._set_dot_key(target, dot_key, typed_val)
                    if dot_key.startswith("plugins.chrome.") and "monitor" in dot_key:
                        win_key = dot_key.replace("plugins.chrome.", "windows.")
                        self._set_dot_key(target, win_key, typed_val)
                except (ValueError, TypeError) as e:
                    log.warning("Invalid env override for '%s'=%r (expected %s): %s", env_key, val_str, expected_type.__name__, e)

        # Generic JARVIS__SECTION__KEY pattern (e.g. JARVIS__AUDIO__SAMPLE_RATE=48000)
        for key, val in os.environ.items():
            if key.startswith("JARVIS__"):
                parts = key.lower().split("__")[1:]
                dot_key = ".".join(parts)
                typed_val = _parse_scalar(val)
                self._set_dot_key(target, dot_key, typed_val)

    def _set_dot_key(self, target: dict[str, Any], dot_key: str, value: Any) -> None:
        """Internal helper to set nested value by dot path."""
        keys = dot_key.split(".")
        current = target
        for k in keys[:-1]:
            if k not in current or not isinstance(current[k], dict):
                current[k] = {}
            current = current[k]
        current[keys[-1]] = value

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get config value using dot-notation (e.g., 'audio.sample_rate').
        Returns default if key not found.
        """
        with self._lock:
            keys = key.split(".")
            current: Any = self._data
            for k in keys:
                if isinstance(current, dict) and k in current:
                    current = current[k]
                elif hasattr(current, k):
                    current = getattr(current, k)
                else:
                    return default
            return copy.deepcopy(current)

    def set(self, key: str, value: Any) -> None:
        """Set config value in-memory using dot-notation."""
        with self._lock:
            self._set_dot_key(self._data, key, value)
            self._structured_config = JarvisConfig(self._data)

    def to_dict(self) -> dict[str, Any]:
        """Return full deep copy of current configuration dictionary."""
        with self._lock:
            return copy.deepcopy(self._data)

    def on_change(self, callback: Callable[[Any], None]) -> None:
        """Register callback for hot-reload notifications."""
        with self._lock:
            if callback not in self._callbacks:
                self._callbacks.append(callback)

    def register_reload_callback(self, callback: Callable[[Any], None]) -> None:
        """Alias for on_change."""
        self.on_change(callback)

    def reload(self) -> bool:
        """Reload configuration from disk and trigger callbacks. Isolated against syntax errors."""
        try:
            new_cfg = self.load()
            with self._lock:
                callbacks = list(self._callbacks)
            for cb in callbacks:
                try:
                    cb(new_cfg)
                except Exception as e:
                    log.error("Error in config reload callback '%s': %s", cb, e, exc_info=True)
            log.info("Configuration hot-reloaded successfully.")
            return True
        except Exception as e:
            log.error("Hot reload failed (retaining active config in memory): %s", e)
            return False

    def reload_if_changed(self) -> bool:
        """Checks if active configuration file mtime has changed and reloads."""
        with self._lock:
            target = self._active_watch_path
            if not target or not target.is_file():
                return False
            try:
                mtime = target.stat().st_mtime
                if mtime > self._last_mtime or self._last_mtime == 0.0:
                    self._last_mtime = mtime
                    return self.reload()
                return False
            except Exception as e:
                log.error("Failed checking config file modification: %s", e)
                return False

    def start_watcher(self, interval_seconds: float = 2.0) -> None:
        """Start background thread monitoring file changes (detected <= 5s)."""
        with self._lock:
            if self._watcher_thread is not None and self._watcher_thread.is_alive():
                return
            self._stop_watcher_event.clear()
            self._watcher_thread = threading.Thread(
                target=self._watcher_loop,
                args=(interval_seconds,),
                name="ConfigWatcherThread",
                daemon=True,
            )
            self._watcher_thread.start()
            log.debug("Config hot-reload watcher started (interval=%.1fs).", interval_seconds)

    def stop_watcher(self) -> None:
        """Stop background hot-reload watcher."""
        self._stop_watcher_event.set()
        if self._watcher_thread and self._watcher_thread.is_alive():
            self._watcher_thread.join(timeout=3.0)
            self._watcher_thread = None
            log.debug("Config watcher stopped.")

    def _watcher_loop(self, interval_seconds: float) -> None:
        """Polling loop inspecting active config file mtime."""
        while not self._stop_watcher_event.is_set():
            time.sleep(interval_seconds)
            target = self._active_watch_path
            if not target or not target.is_file():
                continue
            try:
                mtime = target.stat().st_mtime
                if self._last_mtime != 0.0 and mtime > self._last_mtime:
                    time.sleep(0.3)
                    self._last_mtime = mtime
                    log.info("Config file modification detected (%s). Reloading...", target.name)
                    self.reload()
                else:
                    self._last_mtime = mtime
            except Exception as e:
                log.debug("Watcher probe error on '%s': %s", target, e)


def load_config(path: str | Path) -> dict[str, Any]:
    """Convenience function to load configuration dictionary from file path."""
    mgr = ConfigManager(config_path=path)
    mgr.load()
    return mgr.to_dict()


# Global singleton instance
_GLOBAL_CONFIG: ConfigManager | None = None
_GLOBAL_LOCK = threading.Lock()


def get_config(config_path: str | Path | None = None) -> ConfigManager:
    """Retrieve or initialize the global singleton ConfigManager."""
    global _GLOBAL_CONFIG
    with _GLOBAL_LOCK:
        if _GLOBAL_CONFIG is None:
            _GLOBAL_CONFIG = ConfigManager(config_path=config_path)
            _GLOBAL_CONFIG.load()
        return _GLOBAL_CONFIG
