"""
Dynamic Action Dispatcher and Event Bus for JARVIS.
Provides priority-ordered event routing, strict error isolation, role-based privilege
interception, and synchronous/asynchronous action execution.
"""
from __future__ import annotations

import asyncio
import fnmatch
import inspect
import logging
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

from jarvis.core.models import (
    ActionDefinition,
    ActionResult,
    HandlerResult,
    PrivilegeLevel,
    RequesterContext,
    SubscriptionRecord,
)

logger = logging.getLogger("jarvis.core.dispatcher")


class EventBus:
    """
    Thread-safe Publish/Subscribe Event Bus with Priority and Error Isolation.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[SubscriptionRecord]] = {}
        self._sub_id_map: dict[str, SubscriptionRecord] = {}
        self._lock = threading.RLock()

    def subscribe(
        self,
        event_name: str,
        handler: Callable[..., Any],
        priority: int = 0
    ) -> str:
        """
        Subscribe a callable handler to an event topic.
        
        Args:
            event_name: Exact topic (e.g. 'audio.clap') or wildcard pattern (e.g. 'audio.*').
            handler: Callable taking **payload or specific arguments.
            priority: Higher integers execute earlier (e.g. 100 before 0).
            
        Returns:
            Unique subscription ID string.
        """
        if not event_name or not isinstance(event_name, str):
            raise ValueError("Event name must be a non-empty string.")
        if not callable(handler):
            raise ValueError("Handler must be callable.")

        sub_id = f"sub_{uuid.uuid4().hex[:12]}"
        is_async = inspect.iscoroutinefunction(handler)

        record = SubscriptionRecord(
            subscription_id=sub_id,
            event_name=event_name,
            handler=handler,
            priority=priority,
            is_async=is_async,
        )

        with self._lock:
            if event_name not in self._subscribers:
                self._subscribers[event_name] = []
            self._subscribers[event_name].append(record)
            # Sort by priority descending
            self._subscribers[event_name].sort(key=lambda s: s.priority, reverse=True)
            self._sub_id_map[sub_id] = record

        logger.debug("Subscribed %s to '%s' with priority %d (async=%s)", sub_id, event_name, priority, is_async)
        return sub_id

    def unsubscribe(self, subscription_id: str) -> bool:
        """
        Remove an active subscription by ID.
        
        Returns:
            True if removed, False if not found.
        """
        with self._lock:
            record = self._sub_id_map.pop(subscription_id, None)
            if not record:
                return False

            sub_list = self._subscribers.get(record.event_name, [])
            self._subscribers[record.event_name] = [s for s in sub_list if s.subscription_id != subscription_id]
            if not self._subscribers[record.event_name]:
                del self._subscribers[record.event_name]

        logger.debug("Unsubscribed %s from '%s'", subscription_id, record.event_name)
        return True

    def unsubscribe_all(self, event_name: str | None = None) -> int:
        """Clear all subscribers for a given topic or all topics entirely."""
        with self._lock:
            if event_name is not None:
                records = self._subscribers.pop(event_name, [])
                for r in records:
                    self._sub_id_map.pop(r.subscription_id, None)
                return len(records)
            else:
                count = len(self._sub_id_map)
                self._subscribers.clear()
                self._sub_id_map.clear()
                return count

    def _get_matching_subscribers(self, event_name: str) -> list[SubscriptionRecord]:
        """Collect and sort all matching exact and wildcard subscribers."""
        matched: list[SubscriptionRecord] = []
        with self._lock:
            for pattern, records in self._subscribers.items():
                if pattern == event_name or pattern == "*" or fnmatch.fnmatch(event_name, pattern):
                    matched.extend(records)
            # Deduplicate by subscription_id while preserving highest priority order
            seen = set()
            deduped = []
            for sub in sorted(matched, key=lambda s: s.priority, reverse=True):
                if sub.subscription_id not in seen:
                    seen.add(sub.subscription_id)
                    deduped.append(sub)
            return deduped

    def publish(self, event_name: str, **payload) -> list[HandlerResult]:
        """
        Synchronously publish an event to all subscribers with strict error isolation.
        """
        subscribers = self._get_matching_subscribers(event_name)
        results: list[HandlerResult] = []

        for sub in subscribers:
            t0 = time.perf_counter()
            try:
                if sub.is_async:
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        loop = None

                    if loop and loop.is_running():
                        future = asyncio.run_coroutine_threadsafe(sub.handler(**payload), loop)
                        res = future.result(timeout=10.0)
                    else:
                        res = asyncio.run(sub.handler(**payload))
                else:
                    res = sub.handler(**payload)

                elapsed = (time.perf_counter() - t0) * 1000.0
                results.append(HandlerResult(
                    subscription_id=sub.subscription_id,
                    event_name=event_name,
                    success=True,
                    result=res,
                    execution_time_ms=elapsed
                ))
            except Exception as exc:
                elapsed = (time.perf_counter() - t0) * 1000.0
                logger.error(
                    "EventBus handler '%s' raised exception on event '%s': %s",
                    sub.subscription_id, event_name, exc, exc_info=True
                )
                results.append(HandlerResult(
                    subscription_id=sub.subscription_id,
                    event_name=event_name,
                    success=False,
                    error=str(exc),
                    error_type=type(exc).__name__,
                    execution_time_ms=elapsed
                ))
                # Error isolation: continue to next subscriber

        return results

    async def publish_async(self, event_name: str, **payload) -> list[HandlerResult]:
        """
        Asynchronously publish an event to all subscribers, awaiting coroutines
        and executing synchronous handlers in the thread pool.
        """
        subscribers = self._get_matching_subscribers(event_name)
        results: list[HandlerResult] = []
        loop = asyncio.get_running_loop()

        for sub in subscribers:
            t0 = time.perf_counter()
            try:
                if sub.is_async:
                    res = await sub.handler(**payload)
                else:
                    res = await loop.run_in_executor(None, lambda s=sub: s.handler(**payload))
                elapsed = (time.perf_counter() - t0) * 1000.0
                results.append(HandlerResult(
                    subscription_id=sub.subscription_id,
                    event_name=event_name,
                    success=True,
                    result=res,
                    execution_time_ms=elapsed
                ))
            except Exception as exc:
                elapsed = (time.perf_counter() - t0) * 1000.0
                logger.error(
                    "EventBus async handler '%s' raised exception on event '%s': %s",
                    sub.subscription_id, event_name, exc, exc_info=True
                )
                results.append(HandlerResult(
                    subscription_id=sub.subscription_id,
                    event_name=event_name,
                    success=False,
                    error=str(exc),
                    error_type=type(exc).__name__,
                    execution_time_ms=elapsed
                ))
                # Error isolation: continue to next subscriber

        return results


def default_privilege_interceptor(
    action_name: str,
    payload: dict[str, Any],
    context: RequesterContext,
    required_privilege: PrivilegeLevel
) -> bool:
    """Default privilege evaluator: permits action if granted privilege >= required privilege."""
    return context.granted_privilege >= required_privilege


class ActionDispatcher:
    """
    Action Dispatcher and Execution Coordinator.
    Enforces RBAC privilege gating, payload validation, and lifecycle logging.
    """

    def __init__(
        self,
        event_bus: EventBus | None = None,
        privilege_interceptor: Callable[..., bool] | None = None,
        bypass_security: bool = False
    ) -> None:
        self.event_bus = event_bus or EventBus()
        self._actions: dict[str, ActionDefinition] = {}
        self._privilege_interceptor = privilege_interceptor or default_privilege_interceptor
        self.bypass_security = bypass_security
        self._lock = threading.RLock()

    def register_action(
        self,
        name: str,
        handler: Callable[..., Any],
        required_privilege: PrivilegeLevel = PrivilegeLevel.NORMAL,
        description: str = "",
        schema: dict[str, Any] | None = None,
        timeout_seconds: float | None = None,
        plugin_name: str | None = None
    ) -> None:
        """Register a new callable action."""
        if not name or not isinstance(name, str):
            raise ValueError("Action name must be a non-empty string.")
        if not callable(handler):
            raise ValueError("Action handler must be callable.")

        is_async = inspect.iscoroutinefunction(handler)

        action_def = ActionDefinition(
            name=name,
            handler=handler,
            required_privilege=required_privilege,
            description=description,
            schema=schema,
            timeout_seconds=timeout_seconds,
            plugin_name=plugin_name,
            is_async=is_async,
        )

        with self._lock:
            if name in self._actions:
                logger.warning("Action '%s' is being overwritten in ActionDispatcher.", name)
            self._actions[name] = action_def

        logger.debug("Registered action '%s' (privilege=%s, async=%s)", name, required_privilege.name, is_async)
        self.event_bus.publish("dispatcher.action_registered", action_name=name, privilege=required_privilege.name)

    def unregister_action(self, name: str) -> bool:
        """Unregister an action by name."""
        with self._lock:
            action_def = self._actions.pop(name, None)
            if not action_def:
                return False
        logger.debug("Unregistered action '%s'", name)
        self.event_bus.publish("dispatcher.action_unregistered", action_name=name)
        return True

    def get_action(self, name: str) -> ActionDefinition | None:
        """Retrieve action definition by name."""
        with self._lock:
            return self._actions.get(name)

    def list_actions(self) -> dict[str, ActionDefinition]:
        """List all registered actions."""
        with self._lock:
            return dict(self._actions)

    def set_privilege_interceptor(self, interceptor: Callable[..., bool]) -> None:
        """Set custom privilege validation hook."""
        if not callable(interceptor):
            raise ValueError("Privilege interceptor must be callable.")
        self._privilege_interceptor = interceptor

    def is_authorized(
        self,
        action_name: str,
        context: RequesterContext,
        payload: dict[str, Any] | None = None
    ) -> bool:
        """Check if the given context is authorized to execute the action."""
        if self.bypass_security:
            return True
        action_def = self.get_action(action_name)
        if not action_def:
            return False
        return bool(self._privilege_interceptor(
            action_name,
            payload or {},
            context,
            action_def.required_privilege
        ))

    def dispatch_action(
        self,
        action_name: str,
        payload: dict[str, Any] | None = None,
        requester: str | RequesterContext = "system",
        timeout: float | None = None
    ) -> ActionResult:
        """Synchronously dispatch and execute an action."""
        t0 = time.perf_counter()
        payload = payload or {}

        # Normalize requester context
        if isinstance(requester, str):
            if requester == "system":
                context = RequesterContext.system()
            else:
                context = RequesterContext(requester_id=requester, granted_privilege=PrivilegeLevel.NORMAL)
        else:
            context = requester

        # 1. Action Existence Check
        action_def = self.get_action(action_name)
        if not action_def:
            elapsed = (time.perf_counter() - t0) * 1000.0
            return ActionResult(
                action_name=action_name,
                success=False,
                error=f"Action '{action_name}' is not registered.",
                error_code="ACTION_NOT_FOUND",
                execution_time_ms=elapsed,
                requester=context.requester_id
            )

        # 2. Privilege Interception
        if not self.bypass_security:
            authorized = self._privilege_interceptor(
                action_name, payload, context, action_def.required_privilege
            )
            if not authorized:
                elapsed = (time.perf_counter() - t0) * 1000.0
                logger.warning(
                    "Privilege denied: Requester '%s' (privilege=%s) attempted action '%s' requiring %s",
                    context.requester_id, context.granted_privilege.name, action_name, action_def.required_privilege.name
                )
                self.event_bus.publish(
                    "security.privilege_denied",
                    action_name=action_name,
                    requester_id=context.requester_id,
                    required=action_def.required_privilege.name
                )
                return ActionResult(
                    action_name=action_name,
                    success=False,
                    error=f"Permission denied. Requires {action_def.required_privilege.name} privilege.",
                    error_code="PERMISSION_DENIED",
                    execution_time_ms=elapsed,
                    requester=context.requester_id
                )

        # 3. Pre-Dispatch Event
        self.event_bus.publish("action.pre_dispatch", action_name=action_name, requester=context.requester_id)

        # 4. Handler Execution
        effective_timeout = timeout or action_def.timeout_seconds
        try:
            if action_def.is_async:
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None

                if loop and loop.is_running():
                    future = asyncio.run_coroutine_threadsafe(action_def.handler(**payload), loop)
                    data = future.result(timeout=effective_timeout)
                else:
                    data = asyncio.run(action_def.handler(**payload))
            else:
                data = action_def.handler(**payload)

            elapsed = (time.perf_counter() - t0) * 1000.0
            self.event_bus.publish("action.post_dispatch", action_name=action_name, success=True)
            return ActionResult(
                action_name=action_name,
                success=True,
                data=data,
                execution_time_ms=elapsed,
                requester=context.requester_id
            )

        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000.0
            logger.error("Action '%s' failed during execution: %s", action_name, exc, exc_info=True)
            self.event_bus.publish("action.failed", action_name=action_name, error=str(exc))
            return ActionResult(
                action_name=action_name,
                success=False,
                error=str(exc),
                error_code="HANDLER_EXCEPTION",
                execution_time_ms=elapsed,
                requester=context.requester_id
            )

    async def dispatch_action_async(
        self,
        action_name: str,
        payload: dict[str, Any] | None = None,
        requester: str | RequesterContext = "system",
        timeout: float | None = None
    ) -> ActionResult:
        """Asynchronously dispatch and execute an action with non-blocking concurrency."""
        t0 = time.perf_counter()
        payload = payload or {}
        loop = asyncio.get_running_loop()

        if isinstance(requester, str):
            if requester == "system":
                context = RequesterContext.system()
            else:
                context = RequesterContext(requester_id=requester, granted_privilege=PrivilegeLevel.NORMAL)
        else:
            context = requester

        action_def = self.get_action(action_name)
        if not action_def:
            elapsed = (time.perf_counter() - t0) * 1000.0
            return ActionResult(
                action_name=action_name,
                success=False,
                error=f"Action '{action_name}' is not registered.",
                error_code="ACTION_NOT_FOUND",
                execution_time_ms=elapsed,
                requester=context.requester_id
            )

        if not self.bypass_security:
            authorized = self._privilege_interceptor(
                action_name, payload, context, action_def.required_privilege
            )
            if inspect.iscoroutine(authorized):
                authorized = await authorized
            if not authorized:
                elapsed = (time.perf_counter() - t0) * 1000.0
                return ActionResult(
                    action_name=action_name,
                    success=False,
                    error=f"Permission denied. Requires {action_def.required_privilege.name} privilege.",
                    error_code="PERMISSION_DENIED",
                    execution_time_ms=elapsed,
                    requester=context.requester_id
                )

        await self.event_bus.publish_async("action.pre_dispatch", action_name=action_name, requester=context.requester_id)

        effective_timeout = timeout or action_def.timeout_seconds
        try:
            if action_def.is_async:
                coro = action_def.handler(**payload)
                if effective_timeout:
                    data = await asyncio.wait_for(coro, timeout=effective_timeout)
                else:
                    data = await coro
            else:
                if effective_timeout:
                    data = await asyncio.wait_for(
                        loop.run_in_executor(None, lambda: action_def.handler(**payload)),
                        timeout=effective_timeout
                    )
                else:
                    data = await loop.run_in_executor(None, lambda: action_def.handler(**payload))

            elapsed = (time.perf_counter() - t0) * 1000.0
            await self.event_bus.publish_async("action.post_dispatch", action_name=action_name, success=True)
            return ActionResult(
                action_name=action_name,
                success=True,
                data=data,
                execution_time_ms=elapsed,
                requester=context.requester_id
            )

        except asyncio.TimeoutError:
            elapsed = (time.perf_counter() - t0) * 1000.0
            logger.error("Action '%s' timed out after %ss", action_name, effective_timeout)
            return ActionResult(
                action_name=action_name,
                success=False,
                error=f"Action execution timed out after {effective_timeout}s.",
                error_code="TIMEOUT",
                execution_time_ms=elapsed,
                requester=context.requester_id
            )
        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000.0
            logger.error("Action '%s' failed during async execution: %s", action_name, exc, exc_info=True)
            return ActionResult(
                action_name=action_name,
                success=False,
                error=str(exc),
                error_code="HANDLER_EXCEPTION",
                execution_time_ms=elapsed,
                requester=context.requester_id
            )
