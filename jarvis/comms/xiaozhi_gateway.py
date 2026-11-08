"""
jarvis/comms/xiaozhi_gateway.py
================================
Xiaozhi-ESP32 Hardware Bridge & Model Context Protocol (MCP) Gateway.

Provides:
  - WebSocket full-duplex voice streaming (PCM 16kHz & Opus) for ESP32 hardware chatbots.
  - Bidirectional Model Context Protocol (MCP) server & client:
      * Server-side: Exposes JARVIS ActionDispatcher actions as MCP tools for edge devices.
      * Client-side: Discovers & invokes hardware capabilities registered on the ESP32 (GPIO, OLED, LEDs, sensors).
  - Acoustic Barge-in Interruption: Cancels active TTS playback on 'abort' frame immediately.
  - Token-bucket rate limiting per device ID and timing-attack safe bearer token authentication.
  - Thread-safe, non-blocking asynchronous server lifecycle with Windows atomic device persistence.
"""
from __future__ import annotations

import asyncio
import datetime
import enum
import hmac
import json
import logging
import os
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

import numpy as np

from jarvis.comms.rate_limiter import RateLimitConfig, TokenBucketRateLimiter
from jarvis.core.dispatcher import ActionDispatcher
from jarvis.core.models import ActionResult, ActionStatus, PrivilegeLevel, RequesterContext
from jarvis.core.paths import data_path

logger = logging.getLogger("jarvis.comms.xiaozhi")

# Standard frame constant: 16kHz, 16-bit signed mono PCM.
# 60ms frame = 960 samples = 1920 bytes.
BYTES_PER_SAMPLE = 2
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_FRAME_DURATION_MS = 60
DEFAULT_FRAME_SAMPLES = int(DEFAULT_SAMPLE_RATE * (DEFAULT_FRAME_DURATION_MS / 1000.0))
DEFAULT_FRAME_BYTES = DEFAULT_FRAME_SAMPLES * BYTES_PER_SAMPLE
MAX_AUDIO_BUFFER_BYTES = 16000 * 2 * 30  # Max 30 seconds of audio buffer (DoS prevention)


def _sanitize_device_id(raw_id: str) -> str:
    """Sanitizes incoming device-id to alphanumeric, dash, or underscore (max 64 chars)."""
    sanitized = re.sub(r"[^a-zA-Z0-9_\-]", "", raw_id.strip())
    return sanitized[:64] if sanitized else f"esp32_{uuid.uuid4().hex[:8]}"


class XiaozhiSessionState(str, enum.Enum):
    """Operational state of a connected Xiaozhi-ESP32 client session."""
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    DISCONNECTED = "disconnected"


@dataclass
class XiaozhiAudioParams:
    """Audio streaming configuration negotiated during handshake."""
    format: str = "pcm"             # "pcm" or "opus"
    sample_rate: int = 16000        # 16000 Hz
    channels: int = 1               # 1 (mono)
    frame_duration: int = 60        # 60 ms

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "frame_duration": self.frame_duration,
        }


@dataclass
class XiaozhiGatewayConfig:
    """Configuration parameters for Xiaozhi Gateway Server."""
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 8088
    path: str = "/xiaozhi/v1"
    auth_token: str = ""
    audio_format: str = "pcm"
    sample_rate: int = 16000
    frame_duration_ms: int = 60
    enable_mcp: bool = True
    tts_voice: str = "vieneu"
    rate_limit: RateLimitConfig = field(
        default_factory=lambda: RateLimitConfig(requests_per_minute=60, burst_limit=10)
    )
    max_payload_bytes: int = 10 * 1024 * 1024  # 10 MB ceiling


class XiaozhiDeviceRegistry:
    """
    Thread-safe registry for discovered and paired Xiaozhi-ESP32 hardware devices.
    Adheres strictly to AGENTS.md Rule 3: Windows Atomic Persistence.
    """

    def __init__(self, persist_path: Path | None = None) -> None:
        self.persist_path = persist_path or data_path("devices", "xiaozhi_devices.json")
        self._lock = threading.RLock()
        self._save_lock = threading.Lock()
        self._devices: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        """Loads registered devices from disk."""
        if not self.persist_path.exists():
            return
        try:
            with open(self.persist_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "devices" in data and isinstance(data["devices"], dict):
                    self._devices = data["devices"]
                    logger.info("Loaded %d registered Xiaozhi devices.", len(self._devices))
        except Exception as e:
            logger.error("Failed to load Xiaozhi device registry from %s: %s", self.persist_path, e)
            self._devices = {}

    def register_or_update(
        self,
        device_id: str,
        name: str = "",
        ip_address: str = "",
        features: dict[str, Any] | None = None,
        audio_params: XiaozhiAudioParams | None = None,
        tools_count: int = 0,
    ) -> dict[str, Any]:
        """Registers a newly seen device or updates last seen heartbeat."""
        clean_dev_id = _sanitize_device_id(device_id)
        now = time.time()
        with self._lock:
            dev = self._devices.get(clean_dev_id, {})
            if not dev:
                dev = {
                    "device_id": clean_dev_id,
                    "name": name or f"Xiaozhi-{clean_dev_id[-6:]}",
                    "first_paired_at": now,
                    "tools_count": 0,
                }
            dev["last_seen_at"] = now
            if ip_address:
                dev["ip_address"] = ip_address
            if features is not None:
                dev["features"] = features
            if audio_params is not None:
                dev["audio_format"] = audio_params.format
                dev["sample_rate"] = audio_params.sample_rate
            if tools_count > 0:
                dev["tools_count"] = tools_count

            self._devices[clean_dev_id] = dev

        self._save_atomic()
        return dev

    def get_device(self, device_id: str) -> dict[str, Any] | None:
        """Returns device record or None."""
        clean_dev_id = _sanitize_device_id(device_id)
        with self._lock:
            record = self._devices.get(clean_dev_id)
            return dict(record) if record else None

    def list_devices(self) -> list[dict[str, Any]]:
        """Returns all registered devices."""
        with self._lock:
            return [dict(d) for d in self._devices.values()]

    def _save_atomic(self) -> None:
        """
        Atomically persists registry data with retry backoff for Windows WinError 5.
        Adheres to AGENTS.md Rule 3.
        """
        with self._save_lock:
            with self._lock:
                snapshot = {"devices": dict(self._devices), "updated_at": time.time()}

            self.persist_path.parent.mkdir(parents=True, exist_ok=True)
            tid = threading.get_ident()
            time_ns = time.time_ns()
            tmp_path = self.persist_path.with_name(f"{self.persist_path.name}.tmp.{tid}.{time_ns}")

            try:
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(snapshot, f, indent=2, ensure_ascii=False)

                # Retry loop with exponential backoff on Windows
                max_attempts = 5
                for attempt in range(1, max_attempts + 1):
                    try:
                        tmp_path.replace(self.persist_path)
                        break
                    except (PermissionError, OSError) as e:
                        if attempt == max_attempts:
                            logger.error("Failed to replace %s atomically after %d attempts: %s", self.persist_path, attempt, e)
                            raise
                        time.sleep(0.02 * attempt)
            finally:
                if tmp_path.exists():
                    try:
                        tmp_path.unlink()
                    except OSError:
                        pass


class XiaozhiSession:
    """
    Manages state, audio buffers, and active asynchronous tasks for an active WebSocket connection.
    """

    def __init__(
        self,
        session_id: str,
        device_id: str,
        websocket: Any,
        audio_params: XiaozhiAudioParams,
    ) -> None:
        self.session_id = session_id
        self.device_id = _sanitize_device_id(device_id)
        self.websocket = websocket
        self.audio_params = audio_params
        self.state = XiaozhiSessionState.IDLE

        self.audio_in_buffer = bytearray()
        self.discovered_device_tools: dict[str, dict[str, Any]] = {}
        self.pending_mcp_requests: dict[int, asyncio.Future[Any]] = {}
        self.mcp_seq = 0
        self._lock = asyncio.Lock()

        self.active_tts_task: asyncio.Task[Any] | None = None
        self.is_aborting = False
        self.connected_at = time.time()

    def next_mcp_id(self) -> int:
        """Generates next sequential JSON-RPC request ID."""
        self.mcp_seq += 1
        return self.mcp_seq

    async def send_json(self, message: dict[str, Any]) -> None:
        """Encodes and transmits a JSON text frame to the device."""
        if "session_id" not in message:
            message["session_id"] = self.session_id
        payload_str = json.dumps(message, ensure_ascii=False)
        await self.websocket.send(payload_str)

    async def send_binary(self, data: bytes) -> None:
        """Transmits raw binary audio frame to the device."""
        await self.websocket.send(data)

    def abort_tts(self, reason: str = "abort_requested") -> None:
        """Instantly signals and aborts active TTS playback task."""
        self.is_aborting = True
        if self.active_tts_task and not self.active_tts_task.done():
            logger.info("Aborting active TTS stream for session %s (reason: %s)", self.session_id, reason)
            self.active_tts_task.cancel()
        self.state = XiaozhiSessionState.IDLE


class XiaozhiMcpBridge:
    """
    Model Context Protocol (MCP) bidirectional translation bridge.
    Connects Xiaozhi ESP32 hardware tools <-> JARVIS ActionDispatcher.
    """

    def __init__(self, dispatcher: ActionDispatcher | None = None) -> None:
        self.dispatcher = dispatcher

    def build_tools_list_response(self, request_id: int) -> dict[str, Any]:
        """
        Builds standard MCP tools/list result from JARVIS ActionDispatcher.
        Exposes registered actions as MCP tool descriptors for the device.
        """
        tools: list[dict[str, Any]] = []
        if self.dispatcher:
            for name, action_def in self.dispatcher.list_actions().items():
                # Only expose NORMAL privilege actions to IoT edge device by default
                if action_def.required_privilege == PrivilegeLevel.NORMAL:
                    schema = action_def.schema or {"type": "object", "properties": {}}
                    tools.append({
                        "name": f"jarvis.{name}",
                        "description": action_def.description or f"JARVIS system action {name}",
                        "inputSchema": schema,
                    })

        return {
            "jsonrpc": "2.0",
            "result": {
                "tools": tools,
            },
            "id": request_id,
        }

    async def execute_mcp_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: RequesterContext | None = None,
    ) -> dict[str, Any]:
        """
        Executes a tool call requested by the ESP32 hardware client.
        """
        if not self.dispatcher:
            return {
                "content": [{"type": "text", "text": "ActionDispatcher not initialized on server."}],
                "isError": True,
            }

        # Strip jarvis. prefix if present
        clean_name = tool_name
        if clean_name.startswith("jarvis."):
            clean_name = clean_name[len("jarvis."):]

        req_ctx = context or RequesterContext(
            requester_id="xiaozhi_mcp",
            granted_privilege=PrivilegeLevel.NORMAL,
        )

        try:
            result = self.dispatcher.dispatch_action(
                action_name=clean_name,
                payload=arguments,
                requester=req_ctx,
            )
            if inspect_is_awaitable := asyncio.iscoroutine(result):
                result = await result

            if isinstance(result, ActionResult):
                text_out = result.message or json.dumps(result.data or {}, ensure_ascii=False)
                return {
                    "content": [{"type": "text", "text": text_out}],
                    "isError": not result.success,
                }
            return {
                "content": [{"type": "text", "text": str(result)}],
                "isError": False,
            }
        except Exception as e:
            logger.error("Failed to execute MCP tool '%s': %s", tool_name, e)
            return {
                "content": [{"type": "text", "text": f"Execution error: {e}"}],
                "isError": True,
            }


class XiaozhiGatewayServer:
    """
    Main WebSocket Gateway Server for Xiaozhi-ESP32 Hardware Companions.
    """

    def __init__(
        self,
        config: XiaozhiGatewayConfig | None = None,
        dispatcher: ActionDispatcher | None = None,
        tts_manager: Any | None = None,
        stt_engine: Any | None = None,
        command_handler: Callable[[str, XiaozhiSession], Awaitable[str]] | None = None,
        registry: XiaozhiDeviceRegistry | None = None,
    ) -> None:
        self.config = config or XiaozhiGatewayConfig()
        self.dispatcher = dispatcher
        self.tts_manager = tts_manager
        self.stt_engine = stt_engine
        self.command_handler = command_handler
        self.registry = registry or XiaozhiDeviceRegistry()
        self.mcp_bridge = XiaozhiMcpBridge(dispatcher=dispatcher)

        self.rate_limiter = TokenBucketRateLimiter(
            self.config.rate_limit,
            channel_name="xiaozhi_gateway",
        )

        self.active_sessions: dict[str, XiaozhiSession] = {}
        self._server: Any = None
        self._server_loop: asyncio.AbstractEventLoop | None = None
        self._server_thread: threading.Thread | None = None
        self._is_running = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    def _process_http_request(self, connection: Any, request: Any) -> Any:
        """
        Validates path and bearer authorization during HTTP upgrade before WebSocket negotiation.
        Fail-closed per AGENTS.md Rule 2: Returns HTTP 401/404 if invalid.
        Guarded against timing side-channel attacks via hmac.compare_digest.
        """
        try:
            from websockets.http11 import Response
            from websockets.datastructures import Headers
        except ImportError:
            return None

        req_path = getattr(request, "path", "")
        if self.config.path and not req_path.startswith(self.config.path):
            logger.warning("Rejected client connection to unrecognized path: %s", req_path)
            return Response(404, "Not Found", Headers({"Content-Type": "text/plain"}), b"Path Not Found")

        if self.config.auth_token:
            headers = getattr(request, "headers", {})
            auth_header = headers.get("Authorization", "") or headers.get("authorization", "")
            expected = f"Bearer {self.config.auth_token}"
            if not hmac.compare_digest(auth_header, expected):
                logger.warning("Unauthorized Xiaozhi client connection (invalid or missing bearer token)")
                return Response(401, "Unauthorized", Headers({"Content-Type": "text/plain"}), b"Unauthorized: Invalid Bearer Token")

        return None

    def start(self) -> None:
        """Starts the gateway server in a dedicated background event loop."""
        if self._is_running:
            logger.warning("XiaozhiGatewayServer is already running.")
            return

        self._is_running = True
        ready_event = threading.Event()

        def _run_loop() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._server_loop = loop
            try:
                loop.run_until_complete(self._start_server_async(ready_event))
                loop.run_forever()
            except Exception as e:
                logger.error("XiaozhiGatewayServer event loop stopped with error: %s", e)
            finally:
                loop.close()

        self._server_thread = threading.Thread(
            target=_run_loop,
            name="XiaozhiGatewayServerThread",
            daemon=True,
        )
        self._server_thread.start()
        ready_event.wait(timeout=5.0)
        logger.info("XiaozhiGatewayServer started on %s:%d%s", self.config.host, self.config.port, self.config.path)

    async def _start_server_async(self, ready_event: threading.Event) -> None:
        """Initializes websockets server instance."""
        import websockets

        async def _connection_handler(ws: Any, *args: Any) -> None:
            # Compatible with websockets v11 through v15
            path = args[0] if args else getattr(getattr(ws, "request", None), "path", "")
            await self._handle_client_connection(ws, path)

        self._server = await websockets.serve(
            _connection_handler,
            self.config.host,
            self.config.port,
            max_size=self.config.max_payload_bytes,
            process_request=self._process_http_request,
        )
        ready_event.set()

    def stop(self, timeout: float = 3.0) -> None:
        """Stops the gateway server and terminates active sessions cleanly."""
        if not self._is_running:
            return

        self._is_running = False
        if self._server_loop and self._server:
            async def _cleanup() -> None:
                # Abort all sessions and close pending futures safely across loops
                for s in list(self.active_sessions.values()):
                    s.abort_tts("server_shutdown")
                    for req_id, fut in list(s.pending_mcp_requests.items()):
                        if not fut.done():
                            target_loop = fut.get_loop()
                            target_loop.call_soon_threadsafe(
                                lambda f=fut: not f.done() and f.set_exception(ConnectionError("Server shutting down"))
                            )
                    s.pending_mcp_requests.clear()
                    try:
                        await s.websocket.close(code=1001, reason="Server shutting down")
                    except Exception:
                        pass
                self.active_sessions.clear()
                self._server.close()
                await self._server.wait_closed()

            future = asyncio.run_coroutine_threadsafe(_cleanup(), self._server_loop)
            try:
                future.result(timeout=timeout)
            except Exception as e:
                logger.warning("Timeout during XiaozhiGatewayServer stop: %s", e)

        if self._server_thread and self._server_thread.is_alive():
            self._server_thread.join(timeout=1.0)
        logger.info("XiaozhiGatewayServer stopped.")

    # -------------------------------------------------------------------------
    # Client Connection Lifecycle
    # -------------------------------------------------------------------------

    async def _handle_client_connection(self, ws: Any, path: str) -> None:
        """Handles an individual WebSocket client connection."""
        remote_address = getattr(ws, "remote_address", None)
        client_ip = remote_address[0] if remote_address else "unknown"

        headers = getattr(getattr(ws, "request", None), "headers", {})
        raw_dev_id = headers.get("device-id", "") or headers.get("Device-Id", "") or f"esp32_{uuid.uuid4().hex[:8]}"
        device_id = _sanitize_device_id(raw_dev_id)

        # Rate limiting per device
        rl = self.rate_limiter.acquire(device_id)
        if not rl.allowed:
            logger.warning("Rate limit exceeded for Xiaozhi device %s", device_id)
            await ws.close(code=4429, reason=f"Rate Limit Exceeded. Retry after {rl.retry_after_s:.1f}s")
            return

        session_id = str(uuid.uuid4())
        session = XiaozhiSession(
            session_id=session_id,
            device_id=device_id,
            websocket=ws,
            audio_params=XiaozhiAudioParams(
                format=self.config.audio_format,
                sample_rate=self.config.sample_rate,
                frame_duration=self.config.frame_duration_ms,
            ),
        )
        self.active_sessions[session_id] = session
        logger.info("Xiaozhi device connected: session_id=%s, device_id=%s, ip=%s", session_id, device_id, client_ip)

        try:
            async for raw_msg in ws:
                # Continuous rate limiting per frame
                rl_frame = self.rate_limiter.acquire(device_id)
                if not rl_frame.allowed:
                    await session.send_json({
                        "type": "error",
                        "code": "RATE_LIMITED",
                        "message": f"Rate limit exceeded. Retry after {rl_frame.retry_after_s:.1f}s",
                    })
                    continue

                if isinstance(raw_msg, str):
                    await self._handle_text_frame(session, raw_msg, client_ip)
                elif isinstance(raw_msg, bytes):
                    await self._handle_binary_frame(session, raw_msg)
        except Exception as e:
            logger.info("Client session %s terminated (%s)", session_id, e)
        finally:
            session.abort_tts("connection_closed")
            session.state = XiaozhiSessionState.DISCONNECTED
            for req_id, fut in list(session.pending_mcp_requests.items()):
                if not fut.done():
                    target_loop = fut.get_loop()
                    target_loop.call_soon_threadsafe(
                        lambda f=fut, r=req_id: not f.done() and f.set_exception(ConnectionError(f"Client disconnected before responding to MCP request {r}"))
                    )
            session.pending_mcp_requests.clear()
            self.active_sessions.pop(session_id, None)
            logger.info("Xiaozhi session %s cleanup complete.", session_id)

    # -------------------------------------------------------------------------
    # Frame Ingestion & Dispatch
    # -------------------------------------------------------------------------

    async def _handle_text_frame(self, session: XiaozhiSession, payload_str: str, client_ip: str) -> None:
        """Parses and handles control JSON frames."""
        try:
            msg = json.loads(payload_str)
        except json.JSONDecodeError as e:
            logger.warning("Malformed JSON from Xiaozhi session %s: %s", session.session_id, e)
            await session.send_json({
                "type": "error",
                "code": "MALFORMED_JSON",
                "message": f"Failed to parse JSON: {e}",
            })
            return

        msg_type = msg.get("type", "")

        # 1. Hello / Handshake
        if msg_type == "hello":
            await self._process_hello(session, msg, client_ip)

        # 2. Listen State (Voice stream start/stop/detect)
        elif msg_type == "listen":
            await self._process_listen(session, msg)

        # 3. Abort / Barge-in Interrupt
        elif msg_type == "abort":
            reason = msg.get("reason", "user_interrupted")
            session.abort_tts(reason)
            await session.send_json({"type": "abort_ack", "reason": reason})

        # 4. Model Context Protocol (MCP) Frame
        elif msg_type == "mcp":
            await self._process_mcp(session, msg)

        # 5. IoT Status / Telemetry
        elif msg_type == "iot":
            descriptors = msg.get("descriptors", [])
            self.registry.register_or_update(
                device_id=session.device_id,
                ip_address=client_ip,
                tools_count=len(descriptors),
            )
            await session.send_json({"type": "iot_ack", "status": "ok"})

        else:
            logger.debug("Unhandled Xiaozhi message type '%s' from %s", msg_type, session.session_id)

    async def _handle_binary_frame(self, session: XiaozhiSession, audio_bytes: bytes) -> None:
        """Buffers raw audio frames streamed from ESP32 microphone."""
        if session.state != XiaozhiSessionState.LISTENING:
            # Discard audio received while not listening
            return

        if len(session.audio_in_buffer) + len(audio_bytes) > MAX_AUDIO_BUFFER_BYTES:
            logger.warning("Audio buffer exceeded limit (%d bytes) for session %s", MAX_AUDIO_BUFFER_BYTES, session.session_id)
            return

        session.audio_in_buffer.extend(audio_bytes)

    # -------------------------------------------------------------------------
    # Protocol Handlers
    # -------------------------------------------------------------------------

    async def _process_hello(self, session: XiaozhiSession, msg: dict[str, Any], client_ip: str) -> None:
        """Processes client handshake 'hello' and queries device tools."""
        audio_params_data = msg.get("audio_params", {})
        if audio_params_data:
            session.audio_params = XiaozhiAudioParams(
                format=audio_params_data.get("format", self.config.audio_format),
                sample_rate=audio_params_data.get("sample_rate", self.config.sample_rate),
                channels=audio_params_data.get("channels", 1),
                frame_duration=audio_params_data.get("frame_duration", self.config.frame_duration_ms),
            )

        features = msg.get("features", {})
        self.registry.register_or_update(
            device_id=session.device_id,
            ip_address=client_ip,
            features=features,
            audio_params=session.audio_params,
        )

        # Respond with hello acknowledgment
        await session.send_json({
            "type": "hello",
            "transport": "websocket",
            "session_id": session.session_id,
            "audio_params": session.audio_params.to_dict(),
        })

        # If MCP is enabled on both sides, query device tools
        if self.config.enable_mcp and features.get("mcp", False):
            req_id = session.next_mcp_id()
            await session.send_json({
                "type": "mcp",
                "payload": {
                    "jsonrpc": "2.0",
                    "method": "tools/list",
                    "params": {},
                    "id": req_id,
                },
            })

    async def _process_listen(self, session: XiaozhiSession, msg: dict[str, Any]) -> None:
        """Processes speech capture triggers (start/stop/detect)."""
        state = msg.get("state", "")

        if state == "start" or state == "detect":
            # If currently speaking, barge-in triggered
            if session.state == XiaozhiSessionState.SPEAKING:
                session.abort_tts("voice_barge_in")

            session.state = XiaozhiSessionState.LISTENING
            session.audio_in_buffer.clear()
            session.is_aborting = False
            logger.debug("Session %s entered LISTENING mode.", session.session_id)

        elif state == "stop":
            session.state = XiaozhiSessionState.PROCESSING
            captured_bytes = bytes(session.audio_in_buffer)
            session.audio_in_buffer.clear()
            logger.info("Session %s received voice utterance (%d bytes)", session.session_id, len(captured_bytes))

            # Launch asynchronous speech recognition and command execution
            asyncio.create_task(self._process_utterance(session, captured_bytes))

    async def _process_mcp(self, session: XiaozhiSession, msg: dict[str, Any]) -> None:
        """Processes MCP JSON-RPC 2.0 messages."""
        payload = msg.get("payload", {})
        req_id = payload.get("id")

        # Case A: Response to our previous request
        if "result" in payload or "error" in payload:
            fut = session.pending_mcp_requests.pop(req_id, None)
            if fut and not fut.done():
                target_loop = fut.get_loop()
                if "error" in payload:
                    err_msg = payload["error"]
                    target_loop.call_soon_threadsafe(
                        lambda f=fut, m=err_msg: not f.done() and f.set_exception(RuntimeError(f"MCP Error: {m}"))
                    )
                else:
                    res_val = payload.get("result")
                    target_loop.call_soon_threadsafe(
                        lambda f=fut, r=res_val: not f.done() and f.set_result(r)
                    )

            # If this is response to tools/list, cache discovered tools
            result = payload.get("result", {})
            if isinstance(result, dict) and "tools" in result:
                for tool in result["tools"]:
                    tool_name = tool.get("name")
                    if tool_name:
                        session.discovered_device_tools[tool_name] = tool
                logger.info("Discovered %d hardware tools on device %s", len(session.discovered_device_tools), session.device_id)
                self.registry.register_or_update(
                    device_id=session.device_id,
                    tools_count=len(session.discovered_device_tools),
                )
            return

        # Case B: Request from client
        method = payload.get("method", "")
        params = payload.get("params", {})

        if method == "tools/list":
            resp = self.mcp_bridge.build_tools_list_response(req_id)
            await session.send_json({"type": "mcp", "payload": resp})

        elif method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            call_result = await self.mcp_bridge.execute_mcp_call(tool_name, arguments)
            await session.send_json({
                "type": "mcp",
                "payload": {
                    "jsonrpc": "2.0",
                    "result": call_result,
                    "id": req_id,
                },
            })
        else:
            await session.send_json({
                "type": "mcp",
                "payload": {
                    "jsonrpc": "2.0",
                    "error": {"code": -32601, "message": f"Method '{method}' not found"},
                    "id": req_id,
                },
            })

    # -------------------------------------------------------------------------
    # Utterance Pipeline & TTS Streaming
    # -------------------------------------------------------------------------

    async def _process_utterance(self, session: XiaozhiSession, audio_bytes: bytes) -> None:
        """
        Transcribes speech, processes user intent, and streams back synthesized audio.
        """
        if not audio_bytes:
            session.state = XiaozhiSessionState.IDLE
            return

        try:
            transcribed_text = ""

            # Step 1: STT Transcription
            if self.stt_engine and hasattr(self.stt_engine, "transcribe_bytes") and callable(self.stt_engine.transcribe_bytes):
                try:
                    res = self.stt_engine.transcribe_bytes(audio_bytes, format=session.audio_params.format)
                    transcribed_text = str(res) if res is not None else ""
                except Exception as e:
                    logger.warning("STT transcribe_bytes error: %s", e)
            elif self.stt_engine and hasattr(self.stt_engine, "transcribe") and callable(self.stt_engine.transcribe):
                try:
                    # Convert PCM bytes to float32 numpy array
                    audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                    res = self.stt_engine.transcribe(audio_np)
                    transcribed_text = str(res) if res is not None else ""
                except Exception as e:
                    logger.warning("STT transcribe error: %s", e)

            if not transcribed_text:
                logger.info("No speech detected or STT returned empty string.")
                session.state = XiaozhiSessionState.IDLE
                return

            # Notify device of recognized speech for screen display
            await session.send_json({
                "type": "stt",
                "text": str(transcribed_text),
            })

            # Step 2: Intent / Command Resolution
            reply_text = ""
            if self.command_handler:
                try:
                    res_cmd = await self.command_handler(transcribed_text, session)
                    reply_text = str(res_cmd) if res_cmd is not None else ""
                except Exception as e:
                    logger.error("Command handler error: %s", e)
                    reply_text = f"Đã xảy ra lỗi khi xử lý: {e}"
            else:
                reply_text = f"Tôi đã nhận được lệnh: {transcribed_text}"

            # Send LLM text response
            await session.send_json({
                "type": "llm",
                "text": str(reply_text),
                "emotion": "happy",
            })

            # Step 3: Speech Synthesis & Chunked Audio Streaming
            session.active_tts_task = asyncio.create_task(self._stream_tts(session, reply_text))
            try:
                await session.active_tts_task
            except asyncio.CancelledError:
                logger.info("TTS streaming task cancelled.")
        except Exception as e:
            logger.error("Error processing utterance in session %s: %s", session.session_id, e)
        finally:
            session.state = XiaozhiSessionState.IDLE

    async def _stream_tts(self, session: XiaozhiSession, text: str) -> None:
        """Synthesizes text to audio and streams frames to the device."""
        if not text:
            return

        try:
            pcm_bytes = b""
            if self.tts_manager and hasattr(self.tts_manager, "synthesize_to_bytes"):
                try:
                    pcm_bytes = self.tts_manager.synthesize_to_bytes(text)
                except Exception as e:
                    logger.error("TTS synthesis error: %s", e)

            if not pcm_bytes:
                # Generate soft confirmation beep (synthetic PCM) if TTS unavailable
                pcm_bytes = self._generate_fallback_tone()

            session.state = XiaozhiSessionState.SPEAKING
            await session.send_json({"type": "tts", "state": "start"})

            frame_size = DEFAULT_FRAME_BYTES
            frame_interval_s = (session.audio_params.frame_duration / 1000.0) * 0.85

            for i in range(0, len(pcm_bytes), frame_size):
                if session.is_aborting or session.state != XiaozhiSessionState.SPEAKING:
                    logger.info("TTS playback aborted mid-stream for session %s", session.session_id)
                    break

                chunk = pcm_bytes[i:i + frame_size]
                if len(chunk) < frame_size:
                    # Zero-pad trailing frame
                    chunk = chunk + b"\x00" * (frame_size - len(chunk))

                await session.send_binary(chunk)
                await asyncio.sleep(frame_interval_s)

            await session.send_json({"type": "tts", "state": "stop"})
        except asyncio.CancelledError:
            logger.info("TTS streaming cancelled for session %s", session.session_id)
        except Exception as e:
            logger.warning("Error streaming TTS to session %s: %s", session.session_id, e)

    def stream_tts_to_session(self, session_id: str, text: str) -> Any:
        """
        Thread-safely schedules TTS streaming onto the server's background event loop.
        """
        session = self.active_sessions.get(session_id)
        if not session or not self._server_loop:
            raise ConnectionError(f"Session '{session_id}' not found or server loop not active.")
        session.active_tts_task = asyncio.run_coroutine_threadsafe(
            self._stream_tts(session, text),
            self._server_loop,
        )
        return session.active_tts_task

    def _generate_fallback_tone(self, duration_s: float = 0.5, freq: float = 440.0) -> bytes:
        """Generates a pleasant 440Hz sine wave PCM for testing/fallback."""
        t = np.linspace(0, duration_s, int(16000 * duration_s), endpoint=False)
        audio = (0.2 * np.sin(2 * np.pi * freq * t) * 32767).astype(np.int16)
        return audio.tobytes()

    # -------------------------------------------------------------------------
    # Device Tool Invocation API
    # -------------------------------------------------------------------------

    async def call_device_tool(
        self,
        session_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        timeout: float = 5.0,
    ) -> Any:
        """
        Invokes an MCP tool on the physical ESP32 device and awaits the result.
        Fail-closed per AGENTS.md Rule 2: Returns explicit error on timeout or disconnect.
        """
        session = self.active_sessions.get(session_id)
        if not session or session.state == XiaozhiSessionState.DISCONNECTED:
            raise ConnectionError(f"Session '{session_id}' is not connected.")

        req_id = session.next_mcp_id()
        fut: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        session.pending_mcp_requests[req_id] = fut

        try:
            coro = session.send_json({
                "type": "mcp",
                "payload": {
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": tool_name,
                        "arguments": arguments,
                    },
                    "id": req_id,
                },
            })
            if self._server_loop and asyncio.get_running_loop() != self._server_loop:
                asyncio.run_coroutine_threadsafe(coro, self._server_loop)
            else:
                await coro

            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            session.pending_mcp_requests.pop(req_id, None)
            raise TimeoutError(f"Timeout awaiting tool response for '{tool_name}' on device '{session.device_id}'.")

    def call_device_tool_sync(
        self,
        session_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        timeout: float = 5.0,
    ) -> Any:
        """
        Synchronous wrapper for ActionDispatcher or worker threads to execute MCP tool calls on ESP32.
        """
        if not self._server_loop:
            raise ConnectionError("Server event loop is not active.")
        future = asyncio.run_coroutine_threadsafe(
            self.call_device_tool(session_id, tool_name, arguments, timeout),
            self._server_loop,
        )
        return future.result(timeout=timeout + 0.5)
