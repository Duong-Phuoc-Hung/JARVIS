"""
Structured, rotating, colorized logger for JARVIS.
Writes to console with ANSI colors and to logs/jarvis.log with 10MB rotation.
Provides structured [INTERACTION] logging for R6 & M3 compliance.
"""
from __future__ import annotations

import datetime
import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


# ANSI escape sequences for colorized console output
class LogColors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DEBUG = "\033[36m"      # Cyan
    INFO = "\033[32m"       # Green
    WARNING = "\033[33m"    # Yellow
    ERROR = "\033[31m"      # Red
    CRITICAL = "\033[1;31m" # Bold Red
    DIM = "\033[2m"         # Dim gray for timestamps


class ColoredConsoleFormatter(logging.Formatter):
    """Console formatter applying ANSI color codes based on log level."""

    LEVEL_COLORS = {
        logging.DEBUG: LogColors.DEBUG,
        logging.INFO: LogColors.INFO,
        logging.WARNING: LogColors.WARNING,
        logging.ERROR: LogColors.ERROR,
        logging.CRITICAL: LogColors.CRITICAL,
    }

    def format(self, record: logging.LogRecord) -> str:
        color = self.LEVEL_COLORS.get(record.levelno, LogColors.RESET)
        asctime = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        thread_name = record.threadName
        module = record.name
        level = record.levelname
        msg = record.getMessage()

        # Format: [2026-08-22 00:30:00] [INFO ] [MainThread][jarvis.core] Message
        formatted = (
            f"{LogColors.DIM}[{asctime}]{LogColors.RESET} "
            f"{color}[{level:<5}]{LogColors.RESET} "
            f"{LogColors.DIM}[{thread_name}][{module}]{LogColors.RESET} "
            f"{msg}"
        )
        if record.exc_info:
            formatted += "\n" + self.formatException(record.exc_info)
        return formatted


class StructuredFileFormatter(logging.Formatter):
    """File formatter producing clean, structured timestamps and context."""

    def format(self, record: logging.LogRecord) -> str:
        asctime = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        msecs = int(record.msecs)
        thread_name = record.threadName
        thread_id = record.thread
        module = record.name
        level = record.levelname
        msg = record.getMessage()

        formatted = f"[{asctime}.{msecs:03d}] [{level:<5}] [TID:{thread_id}:{thread_name}] [{module}] {msg}"
        if record.exc_info:
            formatted += "\n" + self.formatException(record.exc_info)
        return formatted


def _enable_windows_vt_mode() -> None:
    """Enable ENABLE_VIRTUAL_TERMINAL_PROCESSING on Windows console."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        STD_OUTPUT_HANDLE = -11
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        handle = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
        if handle and handle != -1:
            mode = wintypes.DWORD()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING)
    except Exception:
        pass


_LOGGING_INITIALIZED = False
_LOGGING_LOCK = threading.RLock()
_INTERACTION_LOCK = threading.Lock()


def setup_logging(
    level: str | None = None,
    log_dir: str | Path | None = None,
    log_file_name: str | None = None,
    log_file: str | Path | None = None,
    log_level: str | None = None,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
    enable_console_colors: bool = True,
    force_reinit: bool = False,
) -> JarvisLoggerAdapter:
    """
    Initialize global logging configuration:
    - Colorized console handler
    - Rotating file handler in logs/jarvis.log (max 10MB, 5 backups, UTF-8)
    """
    global _LOGGING_INITIALIZED
    with _LOGGING_LOCK:
        effective_level = log_level or level or "INFO"

        if log_file:
            log_path = Path(log_file)
            effective_log_dir = log_path.parent
            effective_file_name = log_path.name
        else:
            effective_file_name = log_file_name or "jarvis.log"
            if log_dir is None:
                import os
                _appdata = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
                if _appdata:
                    effective_log_dir = Path(_appdata) / "JARVIS" / "logs"
                else:
                    effective_log_dir = Path.home() / ".jarvis" / "logs"
            else:
                effective_log_dir = Path(log_dir)

        if _LOGGING_INITIALIZED and not force_reinit and not log_file and not log_dir:
            return get_logger("jarvis")

        if force_reinit or log_file or log_dir:
            shutdown_logging()

        if enable_console_colors:
            _enable_windows_vt_mode()

        numeric_level = getattr(logging, effective_level.upper(), logging.INFO)
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)

        for handler in list(root_logger.handlers):
            try:
                handler.close()
            except Exception:
                pass
            root_logger.removeHandler(handler)

        # 1. Console Handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)
        if enable_console_colors:
            console_handler.setFormatter(ColoredConsoleFormatter())
        else:
            console_handler.setFormatter(StructuredFileFormatter())
        root_logger.addHandler(console_handler)

        # 2. Rotating File Handler
        effective_log_dir.mkdir(parents=True, exist_ok=True)
        file_path = effective_log_dir / effective_file_name

        file_handler = RotatingFileHandler(
            filename=str(file_path),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(StructuredFileFormatter())
        root_logger.addHandler(file_handler)

        _LOGGING_INITIALIZED = True
        root_logger.info("Structured logging initialized (File: %s, Level: %s)", file_path, effective_level)
        return get_logger("jarvis")


def shutdown_logging() -> None:
    """Close and remove all handlers from root logger to release file locks."""
    global _LOGGING_INITIALIZED
    with _LOGGING_LOCK:
        root_logger = logging.getLogger()
        for handler in list(root_logger.handlers):
            try:
                handler.close()
            except Exception:
                pass
            root_logger.removeHandler(handler)
        _LOGGING_INITIALIZED = False


def log_interaction(
    trigger: str,
    input_text: str,
    action: str,
    response: str,
    status: str = "success",
    log_file: str | Path | None = None,
) -> str:
    """
    Structured interaction logger for R6, R4 & M3 compliance.
    Format:
    [INTERACTION] <timestamp> | TRIGGER: <trigger_type> | INPUT: <transcript/input> | ACTION: <action_name> | RESPONSE: <response_text> | STATUS: <success/failed>
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    clean_trigger = str(trigger or "UNKNOWN").strip()
    # Sanitize newlines to preserve single line log format
    clean_input = " ".join(str(input_text or "").split())
    clean_action = str(action or "none").strip()
    clean_response = " ".join(str(response or "").split())
    clean_status = "success" if str(status).lower() in ("success", "ok", "true", "1") else "failed"

    entry = (
        f"[INTERACTION] {timestamp} | TRIGGER: {clean_trigger} | "
        f"INPUT: {clean_input} | ACTION: {clean_action} | "
        f"RESPONSE: {clean_response} | STATUS: {clean_status}"
    )

    # 1. Output to standard logger
    interaction_logger = logging.getLogger("jarvis.interaction")
    interaction_logger.info(entry)

    # 2. Append directly to log file
    if log_file:
        target_path = Path(log_file)
    else:
        import os
        _appdata = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if _appdata:
            target_path = Path(_appdata) / "JARVIS" / "logs" / "jarvis.log"
        else:
            target_path = Path.home() / ".jarvis" / "logs" / "jarvis.log"

    with _INTERACTION_LOCK:
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with open(target_path, "a", encoding="utf-8") as f:
                f.write(entry + "\n")
        except Exception as e:
            interaction_logger.warning("Failed to write to interaction log file %s: %s", target_path, e)

    return entry


class JarvisLoggerAdapter(logging.LoggerAdapter):
    """
    Logger adapter providing structured domain logging helpers for R6 compliance:
    - log_trigger(trigger_type, details)
    - log_action(action_name, result, duration_ms, error=None)
    - log_interaction(trigger, input_text, action, response, status, log_file=None)
    """

    def log_trigger(self, trigger_type: str, details: dict[str, Any]) -> None:
        self.info("[TRIGGER:%s] %s", trigger_type, details)

    def log_action(self, action_name: str, result: str, duration_ms: float = 0.0, error: str | None = None) -> None:
        if error:
            self.error("[ACTION:%s] [RESULT:%s] [TIME:%.1fms] Error: %s", action_name, result, duration_ms, error)
        else:
            self.info("[ACTION:%s] [RESULT:%s] [TIME:%.1fms]", action_name, result, duration_ms)

    def log_interaction(
        self,
        trigger: str,
        input_text: str,
        action: str,
        response: str,
        status: str = "success",
        log_file: str | Path | None = None,
    ) -> str:
        return log_interaction(
            trigger=trigger,
            input_text=input_text,
            action=action,
            response=response,
            status=status,
            log_file=log_file,
        )


StructuredLogger = JarvisLoggerAdapter


class LogContext:
    """Context manager for adding contextual attributes to logging statements."""

    def __init__(self, **context_vars: Any) -> None:
        self.context_vars = context_vars

    def __enter__(self) -> LogContext:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        pass


def get_logger(name: str) -> JarvisLoggerAdapter:
    """Get a structured JarvisLoggerAdapter instance."""
    logger = logging.getLogger(name)
    return JarvisLoggerAdapter(logger, {})


def log_trigger(trigger_type: str, details: Any = "", **kwargs: Any) -> None:
    """Convenience helper to log trigger events."""
    logger = get_logger("jarvis.trigger")
    if isinstance(details, dict):
        logger.log_trigger(trigger_type, details)
    else:
        logger.info("[TRIGGER:%s] %s", trigger_type, details)


def log_action(action_name: str, result: str, duration_ms: float = 0.0, error: str | None = None) -> None:
    """Convenience helper to log action outcomes."""
    logger = get_logger("jarvis.action")
    logger.log_action(action_name, result, duration_ms, error)
