"""
Data models, enums, and structured payloads for JARVIS Core.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum
import time
from typing import Any, Callable, Dict, List, Optional, Tuple


class PrivilegeLevel(IntEnum):
    """Role-based access control privilege levels."""
    GUEST = -1   # Unauthenticated or external guest context with minimal privileges
    NORMAL = 0   # Read-only actions, TTS queries, web browsing, status display
    HIGH = 1     # Desktop interaction, window movement, keystroke injection, volume adjustment
    ADMIN = 2    # OS shutdown, reboot, process termination, Nmap security scans, registry edits



class PluginStatus(str, Enum):
    """Plugin runtime lifecycle states."""
    UNINITIALIZED = "uninitialized"
    INITIALIZED = "initialized"
    RUNNING = "running"
    STOPPED = "stopped"
    DEGRADED = "degraded"
    ERROR = "error"


@dataclass
class RequesterContext:
    """Security context representing the entity requesting an action."""
    requester_id: str = "system"                    # e.g. "user_voice", "telegram:123456", "system"
    granted_privilege: PrivilegeLevel = PrivilegeLevel.NORMAL
    is_authenticated: bool = False                 # True if passed face recognition or secret key
    client_ip: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def system(cls) -> RequesterContext:
        """Create fully privileged internal system context."""
        return cls(
            requester_id="system",
            granted_privilege=PrivilegeLevel.ADMIN,
            is_authenticated=True
        )

    @classmethod
    def user(cls, requester_id: str = "user_local", authenticated: bool = False) -> RequesterContext:
        """Create standard user context."""
        return cls(
            requester_id=requester_id,
            granted_privilege=PrivilegeLevel.ADMIN if authenticated else PrivilegeLevel.NORMAL,
            is_authenticated=authenticated
        )


@dataclass
class HandlerResult:
    """Execution outcome of an individual EventBus subscriber handler."""
    subscription_id: str
    event_name: str
    success: bool
    result: Any = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    execution_time_ms: float = 0.0


@dataclass
class ActionResult:
    """Structured result returned by ActionDispatcher after executing an action."""
    action_name: str
    success: bool
    data: Any = None
    error: Optional[str] = None
    error_code: Optional[str] = None     # e.g. ACTION_NOT_FOUND, PERMISSION_DENIED, TIMEOUT, HANDLER_EXCEPTION
    execution_time_ms: float = 0.0
    requester: str = "system"
    timestamp: float = field(default_factory=time.time)

    @property
    def is_success(self) -> bool:
        return self.success

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_name": self.action_name,
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "error_code": self.error_code,
            "execution_time_ms": self.execution_time_ms,
            "requester": self.requester,
            "timestamp": self.timestamp,
        }


@dataclass
class ActionDefinition:
    """Metadata and handler definition for a registered action."""
    name: str
    handler: Callable[..., Any]
    required_privilege: PrivilegeLevel = PrivilegeLevel.NORMAL
    description: str = ""
    schema: Optional[Dict[str, Any]] = None
    timeout_seconds: Optional[float] = None
    plugin_name: Optional[str] = None
    is_async: bool = False


@dataclass
class SubscriptionRecord:
    """Internal representation of an active EventBus subscription."""
    subscription_id: str
    event_name: str
    handler: Callable[..., Any]
    priority: int = 0
    is_async: bool = False
    created_at: float = field(default_factory=time.time)


@dataclass
class PluginMetadata:
    """Metadata describing a plugin package."""
    name: str
    version: str = "1.0.0"
    author: str = "JARVIS Team"
    description: str = ""
    required_permissions: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    enabled_by_default: bool = True
    tags: List[str] = field(default_factory=list)


@dataclass
class PluginHealth:
    """Diagnostic health status of a plugin."""
    plugin_name: str
    status: PluginStatus
    is_healthy: bool
    message: str = "OK"
    last_check_timestamp: float = field(default_factory=time.time)
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MonitorInfo:
    """Detailed geometry and DPI attributes for a physical display monitor."""
    index: int                                  # 1-based index (sorted left-to-right, top-to-bottom)
    handle: int                                 # HMONITOR
    device_name: str                            # e.g. "\\\\.\\DISPLAY1"
    is_primary: bool                            # True if primary display
    rect: Tuple[int, int, int, int]             # (left, top, right, bottom) in virtual desktop pixels
    work_rect: Tuple[int, int, int, int]        # (left, top, right, bottom) excluding taskbar
    width: int                                  # right - left
    height: int                                 # bottom - top
    dpi_x: int                                  # Horizontal DPI (e.g. 96, 120, 144)
    dpi_y: int                                  # Vertical DPI
    scale_factor: float                         # e.g. 1.0, 1.25, 1.5


@dataclass(frozen=True)
class WindowInfo:
    """Metadata and geometry for a Win32 top-level window."""
    hwnd: int
    title: str
    class_name: str
    rect: Tuple[int, int, int, int]             # (left, top, right, bottom)
    width: int
    height: int
    pid: int
    process_name: str
    is_visible: bool
    is_minimized: bool
    is_maximized: bool
    is_cloaked: bool
    is_hung: bool
