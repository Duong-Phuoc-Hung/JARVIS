"""
tests/unit/test_kernel_telepathy.py
===================================
Unit test suite for Frontier 19.0 Ring-0 Kernel Telepathy & Hardware Interrupt Hooking.
Milestone v7.0.0 (Singularity Matrix).
"""
from __future__ import annotations

import time
import pytest

from jarvis.hardware.kernel_telepathy import (
    DEFAULT_KMDF_DEVICE_PATH,
    FramePresentationToken,
    HIDPacketType,
    KernelDeviceDriverHandle,
    KernelInterceptorBackend,
    KernelTelepathyEngine,
    KernelTelepathyStatus,
    KernelTelepathyTelemetry,
    USBHIDHardwarePacket,
)


def test_kernel_device_driver_handle_fail_closed_init() -> None:
    """Verifies that an unprivileged or missing driver handle fails closed gracefully."""
    handle = KernelDeviceDriverHandle(device_path=DEFAULT_KMDF_DEVICE_PATH)
    # Without real ring-0 driver installed, open_handle must return (False, LIMITED/DRIVER_NOT_FOUND)
    success, status = handle.open_handle()
    assert success is False
    assert status in (
        KernelTelepathyStatus.LIMITED,
        KernelTelepathyStatus.DRIVER_NOT_FOUND,
        KernelTelepathyStatus.ACCESS_DENIED,
    )
    assert handle.is_open is False
    handle.close()
    assert handle.is_open is False


def test_kernel_telepathy_engine_forced_emulation() -> None:
    """Verifies forced emulation initializes into LIMITED mode adhering to fail-closed rules."""
    engine = KernelTelepathyEngine()
    init_ok = engine.initialize(force_emulation=True)
    assert init_ok is True
    assert engine.status == KernelTelepathyStatus.LIMITED
    assert engine.backend == KernelInterceptorBackend.EMULATED_LIMITED

    # Telemetry should reflect LIMITED mode
    telemetry = engine.get_telemetry()
    assert telemetry["status"] == KernelTelepathyStatus.LIMITED.value
    assert telemetry["backend"] == KernelInterceptorBackend.EMULATED_LIMITED.value
    assert telemetry["vram_delta_mib"] == 0.00

    engine.close()
    assert engine.status == KernelTelepathyStatus.OFFLINE


def test_frame_presentation_token_capture() -> None:
    """Tests nanosecond-precision GPU frame presentation token capture."""
    engine = KernelTelepathyEngine()
    engine.initialize(force_emulation=True)

    token1 = engine.capture_frame_presentation_token()
    assert isinstance(token1, FramePresentationToken)
    assert token1.token_id == 1
    assert token1.present_id == 1
    assert token1.vblank_count == 1
    assert token1.qpc_timestamp_ns > 0
    assert token1.is_hardware_flip is False

    time.sleep(0.005)

    token2 = engine.capture_frame_presentation_token()
    assert token2.token_id == 2
    assert token2.present_id == 2
    assert token2.vblank_count == 2
    assert token2.qpc_timestamp_ns >= token1.qpc_timestamp_ns

    telemetry = engine.get_telemetry()
    assert telemetry["tokens_captured"] == 2
    engine.close()


def test_usb_hid_hardware_packet_keyboard_injection() -> None:
    """Tests 8-byte standard USB HID keyboard report packet injection."""
    engine = KernelTelepathyEngine()
    engine.initialize(force_emulation=True)

    # Scancode 0x04 = Keyboard 'a'
    injected_press = engine.inject_keyboard_scancode(scancode=0x04, key_up=False)
    assert injected_press is True

    # Scancode 0x04 Key Up
    injected_release = engine.inject_keyboard_scancode(scancode=0x04, key_up=True)
    assert injected_release is True

    telemetry = engine.get_telemetry()
    assert telemetry["packets_injected"] == 2
    assert telemetry["average_injection_latency_ns"] > 0
    engine.close()


def test_usb_hid_hardware_packet_mouse_injection() -> None:
    """Tests 4-byte standard USB HID mouse report packet relative injection."""
    engine = KernelTelepathyEngine()
    engine.initialize(force_emulation=True)

    # Move dx=10, dy=-15, button=1 (Left click)
    injected_mouse = engine.inject_mouse_motion(dx=10, dy=-15, buttons=1)
    assert injected_mouse is True

    # Clamping test for out-of-range delta
    injected_clamped = engine.inject_mouse_motion(dx=500, dy=-300, buttons=0)
    assert injected_clamped is True

    telemetry = engine.get_telemetry()
    assert telemetry["packets_injected"] == 2
    engine.close()


def test_invalid_packet_rejection() -> None:
    """Ensures packets with empty payloads are rejected fail-closed."""
    engine = KernelTelepathyEngine()
    engine.initialize(force_emulation=True)

    invalid_packet = USBHIDHardwarePacket(
        packet_type=HIDPacketType.KEYBOARD_SCANCODE,
        payload_bytes=b"",
        report_id=0,
    )
    result = engine.inject_hardware_hid_packet(invalid_packet)
    assert result is False
    engine.close()
