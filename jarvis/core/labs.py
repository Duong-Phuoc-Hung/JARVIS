"""
Core/Labs Feature Flag Mechanism for JARVIS.
Provides centralized feature gating, fail-closed enforcement, and decorator guards.
"""
from __future__ import annotations

import asyncio
import functools
import inspect
import logging
from collections.abc import Callable
from typing import Any

from jarvis.core.models import ActionResult, ActionStatus

logger = logging.getLogger("jarvis.core.labs")


def is_labs_enabled(feature_name: str | None = None, config: Any | None = None) -> bool:
    """
    Evaluate whether a Labs feature is authorized to execute.

    Fail-closed:
    - If config is None, attempts to load the global ConfigManager.
    - If labs.enabled is False, returns False.
    - If feature_name is specified, returns True only if feature_name is in labs.features list.
    - If feature_name is None, returns True if labs.enabled is True.
    """
    if config is None:
        try:
            from jarvis.core.config import get_config
            config = get_config()
        except Exception:
            return False

    if config is None:
        return False

    labs_enabled = False
    features: list[str] = []

    if hasattr(config, "get"):
        if isinstance(config, dict):
            labs_section = config.get("labs")
            if isinstance(labs_section, dict):
                labs_enabled = bool(labs_section.get("enabled", False))
                features = labs_section.get("features", [])
            else:
                labs_enabled = bool(config.get("labs.enabled", False))
                features = config.get("labs.features", [])
        else:
            # ConfigManager or ConfigNode with dot-notation support
            labs_enabled = bool(config.get("labs.enabled", False))
            features = config.get("labs.features", [])
    elif hasattr(config, "labs"):
        labs_enabled = bool(getattr(config.labs, "enabled", False))
        features = getattr(config.labs, "features", [])

    if not labs_enabled:
        return False

    if feature_name is not None:
        if not isinstance(features, (list, tuple, set)):
            return False
        return feature_name in features

    return True


def create_labs_disabled_result(
    action_name: str = "",
    feature_name: str | None = None,
    requester: str = "system",
    execution_time_ms: float = 0.0,
) -> ActionResult:
    """
    Construct an authoritative fail-closed ActionResult for a disabled Labs feature.
    Guarantees success=False, retryable=False, status=ActionStatus.LABS_DISABLED,
    and code="LABS_FEATURE_DISABLED".
    """
    msg = f"Action '{action_name}' requires Labs feature '{feature_name}' to be enabled in configuration."
    return ActionResult(
        action_name=action_name,
        success=False,
        status=ActionStatus.LABS_DISABLED,
        code="LABS_FEATURE_DISABLED",
        message=msg,
        retryable=False,
        error=msg,
        error_code="LABS_FEATURE_DISABLED",
        execution_time_ms=execution_time_ms,
        requester=requester,
        data={
            "feature_name": feature_name,
            "status": "LABS_DISABLED",
            "reason": "Feature flag not enabled in configuration",
        },
    )


def require_labs(
    feature_name: str,
    config_provider: Callable[[], Any] | None = None,
) -> Callable[..., Any]:
    """
    Decorator for functions/methods enforcing Labs feature authorization.
    If the specified Labs feature is disabled, immediately returns an
    authoritative fail-closed ActionResult without executing the wrapped function.
    Supports both synchronous and asynchronous functions and methods.
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        action_name = getattr(func, "__name__", feature_name)

        def _resolve_and_check(args: tuple[Any, ...], kwargs: dict[str, Any]) -> bool:
            # 1. Custom config provider
            if config_provider is not None:
                cfg = config_provider()
                return is_labs_enabled(feature_name, cfg)

            # 2. Passed explicitly as kwarg
            if "config" in kwargs:
                cfg = kwargs.get("config")
                return is_labs_enabled(feature_name, cfg)

            # 3. Method on instance with config attribute
            if args and hasattr(args[0], "config"):
                inst_cfg = getattr(args[0], "config")
                if inst_cfg is not None:
                    return is_labs_enabled(feature_name, inst_cfg)
                # Fail-closed: instance.config is None -> fall back to global config
                return is_labs_enabled(feature_name, None)

            # 4. Standalone function call -> check global config
            return is_labs_enabled(feature_name, None)

        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                if not _resolve_and_check(args, kwargs):
                    logger.warning(
                        "Blocked execution of Labs async feature '%s' (%s): Labs flag disabled.",
                        feature_name, action_name,
                    )
                    return create_labs_disabled_result(action_name=action_name, feature_name=feature_name)
                return await func(*args, **kwargs)
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                if not _resolve_and_check(args, kwargs):
                    logger.warning(
                        "Blocked execution of Labs feature '%s' (%s): Labs flag disabled.",
                        feature_name, action_name,
                    )
                    return create_labs_disabled_result(action_name=action_name, feature_name=feature_name)
                return func(*args, **kwargs)
            return sync_wrapper

    return decorator
