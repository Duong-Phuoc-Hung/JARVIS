"""
tests/unit/test_xiaozhi_gateway.py
==================================
Unit test suite for Xiaozhi-ESP32 Hardware Bridge & Model Context Protocol (MCP) Gateway.
Verifies:
  1. Configuration defaults and initialization.
  2. Device registry with Windows Atomic Persistence (AGENTS.md Rule 3).
  3. Session lifecycle, state machine, and audio buffering.
  4. Bidirectional MCP bridge (discovery, tools/list, tools/call).
  5. WebSocket end-to-end handshake ('hello'), authentication, and rate limiting (fail-closed).
  6. Voice dialogue loop (listen -> binary audio stream -> STT -> LLM text -> chunked TTS streaming).
  7. Acoustic barge-in interruption ('abort' frame instantly terminates TTS).
  8. Device tool invocation with fail-closed timeout handling.
  9. Malformed frame error isolation.
"""
from __future__ import annotations

import asyncio
import json
import socket
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest
import websockets

from jarvis.comms.rate_limiter import RateLimitConfig
from jarvis.comms.xiaozhi_gateway import (
    DEFAULT_FRAME_BYTES,
    XiaozhiAudioParams,
    XiaozhiDeviceRegistry,
    XiaozhiGatewayConfig,
    XiaozhiGatewayServer,
    XiaozhiMcpBridge,
    XiaozhiSession,
    XiaozhiSessionState,
)
from jarvis.core.dispatcher import ActionDispatcher
from jarvis.core.models import ActionResult, ActionStatus, PrivilegeLevel, RequesterContext


def _get_free_port() -> int:
    """Finds an available local port for isolated server testing."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ==============================================================================
# 1. Configuration & Registry Unit Tests
# ==============================================================================

def test_gateway_config_and_defaults():
    """Verify default gateway configuration parameters."""
    cfg = XiaozhiGatewayConfig()
    assert cfg.enabled is True
    assert cfg.host == "0.0.0.0"
    assert cfg.port == 8088
    assert cfg.path == "/xiaozhi/v1"
    assert cfg.audio_format == "pcm"
    assert cfg.sample_rate == 16000
    assert cfg.frame_duration_ms == 60
    assert cfg.enable_mcp is True
    assert cfg.rate_limit.requests_per_minute == 60


def test_device_registry_atomic_persistence(tmp_path: Path):
    """Verify registry updates and atomic disk persistence adhering to Rule 3."""
    reg_file = tmp_path / "devices" / "test_xiaozhi.json"
    registry = XiaozhiDeviceRegistry(persist_path=reg_file)

    # Register first device
    dev1 = registry.register_or_update(
        device_id="esp32_c45789",
        name="Desk Companion",
        ip_address="192.168.1.50",
        features={"mcp": True, "aec": True},
        audio_params=XiaozhiAudioParams(format="pcm", sample_rate=16000),
        tools_count=4,
    )
    assert dev1["device_id"] == "esp32_c45789"
    assert dev1["name"] == "Desk Companion"
    assert dev1["tools_count"] == 4
    assert reg_file.exists()

    # Re-instantiate from persisted file
    reloaded = XiaozhiDeviceRegistry(persist_path=reg_file)
    record = reloaded.get_device("esp32_c45789")
    assert record is not None
    assert record["ip_address"] == "192.168.1.50"
    assert record["tools_count"] == 4

    # Update heartbeat
    reloaded.register_or_update(device_id="esp32_c45789", tools_count=5)
    updated = reloaded.get_device("esp32_c45789")
    assert updated is not None
    assert updated["tools_count"] == 5


# ==============================================================================
# 2. Session Lifecycle & Audio Buffering Unit Tests
# ==============================================================================

def test_session_lifecycle_and_barge_in():
    """Verify session state transitions, audio buffer capacity, and abort."""
    mock_ws = MagicMock()
    params = XiaozhiAudioParams(format="pcm", sample_rate=16000, frame_duration=60)
    session = XiaozhiSession(
        session_id="sess_123",
        device_id="dev_456",
        websocket=mock_ws,
        audio_params=params,
    )
    assert session.state == XiaozhiSessionState.IDLE
    assert session.session_id == "sess_123"

    # Simulate listening state
    session.state = XiaozhiSessionState.LISTENING
    pcm_chunk = b"\x00\x01" * 960  # 1920 bytes
    session.audio_in_buffer.extend(pcm_chunk)
    assert len(session.audio_in_buffer) == 1920

    # Abort active TTS
    mock_task = MagicMock()
    mock_task.done.return_value = False
    session.active_tts_task = mock_task

    session.abort_tts(reason="wake_word_detected")
    assert session.is_aborting is True
    assert session.state == XiaozhiSessionState.IDLE
    mock_task.cancel.assert_called_once()


# ==============================================================================
# 3. Model Context Protocol (MCP) Bridge Unit Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_mcp_bridge_tools_list_and_call():
    """Verify bidirectional MCP tool discovery and execution via ActionDispatcher."""
    dispatcher = ActionDispatcher()

    # Register an action into ActionDispatcher
    def mock_set_volume(level: int = 50, **kwargs: Any) -> ActionResult:
        return ActionResult(
            action_name="system.volume",
            success=True,
            status=ActionStatus.SUCCESS,
            message=f"Volume set to {level}%",
            data={"level": level},
        )

    dispatcher.register_action(
        name="system.volume",
        handler=mock_set_volume,
        description="Set master volume",
        schema={
            "type": "object",
            "properties": {"level": {"type": "integer"}},
            "required": ["level"],
        },
    )

    bridge = XiaozhiMcpBridge(dispatcher=dispatcher)

    # 1. tools/list discovery
    list_resp = bridge.build_tools_list_response(request_id=10)
    assert list_resp["id"] == 10
    tools = list_resp["result"]["tools"]
    volume_tool = next((t for t in tools if t["name"] == "jarvis.system.volume"), None)
    assert volume_tool is not None
    assert "level" in volume_tool["inputSchema"]["properties"]

    # 2. tools/call execution
    call_resp = await bridge.execute_mcp_call("jarvis.system.volume", {"level": 75})
    assert call_resp["isError"] is False
    assert "Volume set to 75%" in call_resp["content"][0]["text"]

    # 3. Unknown tool (fail-closed)
    unknown_resp = await bridge.execute_mcp_call("jarvis.non_existent", {})
    assert unknown_resp["isError"] is True


# ==============================================================================
# 4. WebSocket Server End-to-End Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_websocket_handshake_and_mcp_discovery(tmp_path: Path):
    """Verify client handshake 'hello' and automatic MCP tool discovery."""
    port = _get_free_port()
    registry_file = tmp_path / "reg.json"
    cfg = XiaozhiGatewayConfig(
        host="127.0.0.1",
        port=port,
        path="/xiaozhi/v1",
        enable_mcp=True,
    )
    server = XiaozhiGatewayServer(config=cfg, registry=XiaozhiDeviceRegistry(registry_file))
    server.start()

    uri = f"ws://127.0.0.1:{port}/xiaozhi/v1"
    try:
        async with websockets.connect(uri, additional_headers={"Device-Id": "esp32_unit_test"}) as ws:
            # 1. Send Hello
            hello_msg = {
                "type": "hello",
                "version": 1,
                "features": {"mcp": True},
                "audio_params": {
                    "format": "pcm",
                    "sample_rate": 16000,
                    "channels": 1,
                    "frame_duration": 60,
                },
            }
            await ws.send(json.dumps(hello_msg))

            # Receive Server Hello
            raw_reply = await asyncio.wait_for(ws.recv(), timeout=2.0)
            reply = json.loads(raw_reply)
            assert reply["type"] == "hello"
            assert reply["audio_params"]["format"] == "pcm"
            session_id = reply["session_id"]
            assert session_id is not None

            # Receive Server MCP tools/list discovery query
            raw_mcp = await asyncio.wait_for(ws.recv(), timeout=2.0)
            mcp_query = json.loads(raw_mcp)
            assert mcp_query["type"] == "mcp"
            assert mcp_query["payload"]["method"] == "tools/list"
            req_id = mcp_query["payload"]["id"]

            # Respond with device tools
            mcp_resp = {
                "session_id": session_id,
                "type": "mcp",
                "payload": {
                    "jsonrpc": "2.0",
                    "result": {
                        "tools": [
                            {
                                "name": "self.lamp.set_state",
                                "description": "Desk lamp switch",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {"state": {"type": "boolean"}},
                                },
                            }
                        ]
                    },
                    "id": req_id,
                },
            }
            await ws.send(json.dumps(mcp_resp))

            # Small yield to let server process tools response
            await asyncio.sleep(0.1)
            session = server.active_sessions.get(session_id)
            assert session is not None
            assert "self.lamp.set_state" in session.discovered_device_tools

    finally:
        server.stop()


@pytest.mark.asyncio
async def test_websocket_auth_failure_fail_closed():
    """Verify unauthorized connection is closed with 4401 (fail-closed per Rule 2)."""
    port = _get_free_port()
    cfg = XiaozhiGatewayConfig(
        host="127.0.0.1",
        port=port,
        path="/xiaozhi/v1",
        auth_token="super_secret_jarvis_token",
    )
    server = XiaozhiGatewayServer(config=cfg)
    server.start()

    uri = f"ws://127.0.0.1:{port}/xiaozhi/v1"
    try:
        # Connect without auth header
        with pytest.raises(websockets.exceptions.InvalidStatus) as exc_info:
            async with websockets.connect(uri):
                pass
        assert exc_info.value.response.status_code == 401

        # Connect with correct auth header
        async with websockets.connect(
            uri,
            additional_headers={"Authorization": "Bearer super_secret_jarvis_token"},
        ) as ws:
            await ws.send(json.dumps({"type": "hello"}))
            raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
            assert json.loads(raw)["type"] == "hello"

    finally:
        server.stop()


@pytest.mark.asyncio
async def test_websocket_rate_limiting_fail_closed():
    """Verify burst requests exceed rate limit and receive error rejection."""
    port = _get_free_port()
    cfg = XiaozhiGatewayConfig(
        host="127.0.0.1",
        port=port,
        path="/xiaozhi/v1",
        rate_limit=RateLimitConfig(requests_per_minute=2, burst_limit=1),
    )
    server = XiaozhiGatewayServer(config=cfg)
    server.start()

    uri = f"ws://127.0.0.1:{port}/xiaozhi/v1"
    try:
        async with websockets.connect(uri, additional_headers={"Device-Id": "rate_limited_dev"}) as ws:
            # 1. Hello (uses token)
            await ws.send(json.dumps({"type": "hello"}))
            await ws.recv()

            # 2. Flood immediate frames -> triggers rate limit frame
            await ws.send(json.dumps({"type": "hello"}))
            raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
            msg = json.loads(raw)
            assert msg.get("type") == "error"
            assert msg.get("code") == "RATE_LIMITED"

    finally:
        server.stop()


@pytest.mark.asyncio
async def test_websocket_listen_speech_tts_loop():
    """Verify complete conversational cycle: listen -> speech -> STT -> LLM -> TTS stream."""
    port = _get_free_port()

    # Mock STT Engine
    mock_stt = MagicMock(spec=["transcribe"])
    mock_stt.transcribe.return_value = "Bật đèn bàn làm việc"

    # Mock TTS Manager
    mock_tts = MagicMock()
    # 2 frames of 16kHz PCM (1920 bytes * 2 = 3840 bytes)
    mock_tts.synthesize_to_bytes.return_value = b"\x01\x00" * 1920

    async def mock_handler(text: str, session: Any) -> str:
        return f"Đã nhận lệnh: {text}"

    cfg = XiaozhiGatewayConfig(
        host="127.0.0.1",
        port=port,
        path="/xiaozhi/v1",
        enable_mcp=False,
    )
    server = XiaozhiGatewayServer(
        config=cfg,
        stt_engine=mock_stt,
        tts_manager=mock_tts,
        command_handler=mock_handler,
    )
    server.start()

    uri = f"ws://127.0.0.1:{port}/xiaozhi/v1"
    try:
        async with websockets.connect(uri) as ws:
            # Handshake
            await ws.send(json.dumps({"type": "hello"}))
            await ws.recv()

            # Start recording
            await ws.send(json.dumps({"type": "listen", "state": "start"}))

            # Stream audio frames
            sample_pcm = b"\x05\x00" * 960  # 1920 bytes
            await ws.send(sample_pcm)
            await ws.send(sample_pcm)

            # Stop recording (triggers speech processing)
            await ws.send(json.dumps({"type": "listen", "state": "stop"}))

            # Expect STT notification
            msg_stt = json.loads(await asyncio.wait_for(ws.recv(), timeout=3.0))
            assert msg_stt["type"] == "stt"
            assert msg_stt["text"] == "Bật đèn bàn làm việc"

            # Expect LLM notification
            msg_llm = json.loads(await asyncio.wait_for(ws.recv(), timeout=3.0))
            assert msg_llm["type"] == "llm"
            assert "Bật đèn bàn làm việc" in msg_llm["text"]

            # Expect TTS Start
            msg_tts_start = json.loads(await asyncio.wait_for(ws.recv(), timeout=3.0))
            assert msg_tts_start["type"] == "tts"
            assert msg_tts_start["state"] == "start"

            # Expect Binary Audio Frames
            bin_frame_1 = await asyncio.wait_for(ws.recv(), timeout=3.0)
            assert isinstance(bin_frame_1, bytes)
            assert len(bin_frame_1) == DEFAULT_FRAME_BYTES

            bin_frame_2 = await asyncio.wait_for(ws.recv(), timeout=3.0)
            assert isinstance(bin_frame_2, bytes)
            assert len(bin_frame_2) == DEFAULT_FRAME_BYTES

            # Expect TTS Stop
            msg_tts_stop = json.loads(await asyncio.wait_for(ws.recv(), timeout=3.0))
            assert msg_tts_stop["type"] == "tts"
            assert msg_tts_stop["state"] == "stop"

    finally:
        server.stop()


@pytest.mark.asyncio
async def test_websocket_barge_in_abort_cancellation():
    """Verify 'abort' message immediately stops active TTS stream."""
    port = _get_free_port()

    mock_tts = MagicMock()
    # 20 frames to simulate a long speech
    mock_tts.synthesize_to_bytes.return_value = b"\x01\x00" * (1920 * 20)

    cfg = XiaozhiGatewayConfig(host="127.0.0.1", port=port, path="/xiaozhi/v1", enable_mcp=False)
    server = XiaozhiGatewayServer(config=cfg, tts_manager=mock_tts)
    server.start()

    uri = f"ws://127.0.0.1:{port}/xiaozhi/v1"
    try:
        async with websockets.connect(uri) as ws:
            await ws.send(json.dumps({"type": "hello"}))
            await ws.recv()

            # Trigger an utterance with synthetic speech
            session_id = list(server.active_sessions.keys())[0]
            session = server.active_sessions[session_id]

            # Trigger TTS streaming task on server's background loop
            server.stream_tts_to_session(session_id, "A long response text")

            # Wait for TTS start frame
            raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
            assert json.loads(raw)["type"] == "tts"

            # Wait for at least 1 audio frame
            raw_audio = await asyncio.wait_for(ws.recv(), timeout=2.0)
            assert isinstance(raw_audio, bytes)

            # Send abort interruption
            await ws.send(json.dumps({"type": "abort", "reason": "wake_word_detected"}))

            # Expect abort acknowledgment
            raw_ack = await asyncio.wait_for(ws.recv(), timeout=2.0)
            ack = json.loads(raw_ack)
            assert ack["type"] == "abort_ack"

            # TTS task must have aborted and returned to IDLE
            await asyncio.sleep(0.2)
            assert session.state == XiaozhiSessionState.IDLE

    finally:
        server.stop()


@pytest.mark.asyncio
async def test_device_tool_invocation_and_timeout():
    """Verify server can invoke hardware tools on device with timeout protection."""
    port = _get_free_port()
    cfg = XiaozhiGatewayConfig(host="127.0.0.1", port=port, path="/xiaozhi/v1", enable_mcp=False)
    server = XiaozhiGatewayServer(config=cfg)
    server.start()

    uri = f"ws://127.0.0.1:{port}/xiaozhi/v1"
    try:
        async with websockets.connect(uri) as ws:
            await ws.send(json.dumps({"type": "hello"}))
            raw_hello = json.loads(await ws.recv())
            session_id = raw_hello["session_id"]

            # Scenario 1: Successful tool invocation
            async def _respond_tool():
                raw_call = await ws.recv()
                call_msg = json.loads(raw_call)
                req_id = call_msg["payload"]["id"]
                resp = {
                    "session_id": session_id,
                    "type": "mcp",
                    "payload": {
                        "jsonrpc": "2.0",
                        "result": {"status": "ok", "state": True},
                        "id": req_id,
                    },
                }
                await ws.send(json.dumps(resp))

            client_task = asyncio.create_task(_respond_tool())
            result = await server.call_device_tool(
                session_id=session_id,
                tool_name="self.lamp.set_state",
                arguments={"state": True},
                timeout=2.0,
            )
            await client_task
            assert result["status"] == "ok"
            assert result["state"] is True

            # Scenario 2: Synchronous tool invocation wrapper (called from worker thread)
            client_task2 = asyncio.create_task(_respond_tool())
            sync_result = await asyncio.to_thread(
                server.call_device_tool_sync,
                session_id,
                "self.lamp.set_state",
                {"state": True},
                2.0,
            )
            await client_task2
            assert sync_result["status"] == "ok"

            # Scenario 3: Timeout when device fails to respond (fail-closed per Rule 2)
            with pytest.raises(TimeoutError):
                await server.call_device_tool(
                    session_id=session_id,
                    tool_name="self.camera.capture",
                    arguments={},
                    timeout=0.2,
                )

    finally:
        server.stop()


def test_device_id_sanitization():
    """Verify device-id sanitization guards against command/path injection."""
    from jarvis.comms.xiaozhi_gateway import _sanitize_device_id
    assert _sanitize_device_id("esp32_c45789") == "esp32_c45789"
    assert _sanitize_device_id("esp32; rm -rf /") == "esp32rm-rf"
    assert _sanitize_device_id("../../../secret") == "secret"
    assert len(_sanitize_device_id("a" * 100)) == 64
    assert _sanitize_device_id("   ").startswith("esp32_")


@pytest.mark.asyncio
async def test_malformed_json_resilience():
    """Verify server isolates malformed JSON syntax without crashing."""
    port = _get_free_port()
    cfg = XiaozhiGatewayConfig(host="127.0.0.1", port=port, path="/xiaozhi/v1")
    server = XiaozhiGatewayServer(config=cfg)
    server.start()

    uri = f"ws://127.0.0.1:{port}/xiaozhi/v1"
    try:
        async with websockets.connect(uri) as ws:
            await ws.send("{ malformed: json [")
            raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
            err = json.loads(raw)
            assert err["type"] == "error"
            assert err["code"] == "MALFORMED_JSON"

    finally:
        server.stop()
