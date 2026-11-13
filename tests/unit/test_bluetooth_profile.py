"""
tests/unit/test_bluetooth_profile.py
====================================
Unit tests for Bluetooth Smart Audio Profile Switcher & Hybrid Topology Manager.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from jarvis.audio.bluetooth_profile import (
    AudioEndpoint,
    AudioProfileMode,
    AudioTopology,
    BluetoothAudioManager,
    DeviceType,
)


def test_classify_device() -> None:
    """Verify regex classification of Bluetooth A2DP, HFP, USB, and internal audio devices."""
    mgr = BluetoothAudioManager()

    # 1. Bluetooth A2DP stereo headphones
    dtype, is_bt, is_hfp = mgr.classify_device("Headphones (Sony WH-1000XM4 Stereo)", is_input=False)
    assert dtype == DeviceType.BLUETOOTH_A2DP
    assert is_bt is True
    assert is_hfp is False

    # 2. Bluetooth HFP Hands-Free telephony
    dtype, is_bt, is_hfp = mgr.classify_device("Headset (Sony WH-1000XM4 Hands-Free AG Audio)", is_input=True)
    assert dtype == DeviceType.BLUETOOTH_HFP
    assert is_bt is True
    assert is_hfp is True

    # 3. Dedicated USB Microphone
    dtype, is_bt, is_hfp = mgr.classify_device("Microphone (Fifine K669 USB Audio Device)", is_input=True)
    assert dtype == DeviceType.USB_ENDPOINT
    assert is_bt is False
    assert is_hfp is False

    # 4. Laptop internal Realtek audio
    dtype, is_bt, is_hfp = mgr.classify_device("Speakers (Realtek High Definition Audio)", is_input=False)
    assert dtype == DeviceType.INTERNAL_OR_ANALOG
    assert is_bt is False
    assert is_hfp is False


def test_inspect_audio_topology_empty() -> None:
    """Verify fail-closed empty topology handling when no devices are detected."""
    mgr = BluetoothAudioManager()
    topology = mgr.inspect_audio_topology(raw_devices=[])
    assert topology.input_devices == []
    assert topology.output_devices == []
    assert topology.recommended_input is None
    assert topology.recommended_output is None
    assert topology.degradation_risk is False
    assert "No audio endpoints" in topology.remedy_notice


def test_inspect_audio_topology_hybrid_split() -> None:
    """
    Verify hybrid split topology:
    Prefers USB mic for input and Bluetooth A2DP for output to protect 48kHz playback quality.
    """
    mock_devices = [
        # Output 0: Bluetooth A2DP Stereo
        {
            "name": "Headphones (WH-1000XM4 Stereo)",
            "max_input_channels": 0,
            "max_output_channels": 2,
            "default_samplerate": 48000.0,
            "hostapi": 0,
        },
        # Input 1: Dedicated USB Microphone
        {
            "name": "Microphone (Fifine USB Audio)",
            "max_input_channels": 1,
            "max_output_channels": 0,
            "default_samplerate": 48000.0,
            "hostapi": 0,
        },
        # Input 2: Bluetooth Hands-Free Mic
        {
            "name": "Headset (WH-1000XM4 Hands-Free AG Audio)",
            "max_input_channels": 1,
            "max_output_channels": 0,
            "default_samplerate": 16000.0,
            "hostapi": 0,
        },
    ]

    mgr = BluetoothAudioManager(mode=AudioProfileMode.AUTO)
    topology = mgr.inspect_audio_topology(raw_devices=mock_devices)

    assert topology.recommended_output is not None
    assert topology.recommended_output.name == "Headphones (WH-1000XM4 Stereo)"
    assert topology.recommended_output.device_type == DeviceType.BLUETOOTH_A2DP

    assert topology.recommended_input is not None
    assert topology.recommended_input.name == "Microphone (Fifine USB Audio)"
    assert topology.recommended_input.device_type == DeviceType.USB_ENDPOINT

    assert topology.degradation_risk is False
    assert "Hybrid split active" in topology.remedy_notice


def test_inspect_audio_topology_degradation_risk_detected() -> None:
    """
    Verify degradation risk flag when ONLY a Bluetooth headset is connected
    for both recording and playback.
    """
    mock_devices = [
        # Output 0: Bluetooth Stereo
        {
            "name": "AirPods Pro Stereo",
            "max_input_channels": 0,
            "max_output_channels": 2,
            "default_samplerate": 48000.0,
            "hostapi": 0,
        },
        # Input 1: Bluetooth Hands-Free Mic
        {
            "name": "AirPods Pro Hands-Free Audio",
            "max_input_channels": 1,
            "max_output_channels": 0,
            "default_samplerate": 16000.0,
            "hostapi": 0,
        },
    ]

    mgr = BluetoothAudioManager(mode=AudioProfileMode.AUTO)
    topology = mgr.inspect_audio_topology(raw_devices=mock_devices)

    assert topology.degradation_risk is True
    assert "Warning: Only Bluetooth mic" in topology.remedy_notice


def test_hfp_forced_mode() -> None:
    """Verify forcing HFP mode selects hands-free endpoints explicitly."""
    mock_devices = [
        {
            "name": "WH-1000XM4 Stereo",
            "max_input_channels": 0,
            "max_output_channels": 2,
            "default_samplerate": 48000.0,
            "hostapi": 0,
        },
        {
            "name": "WH-1000XM4 Hands-Free AG Audio",
            "max_input_channels": 1,
            "max_output_channels": 1,
            "default_samplerate": 16000.0,
            "hostapi": 0,
        },
    ]

    mgr = BluetoothAudioManager(mode=AudioProfileMode.HFP_HANDS_FREE)
    topology = mgr.inspect_audio_topology(raw_devices=mock_devices)

    assert topology.recommended_output is not None
    assert topology.recommended_output.is_handsfree is True
    assert "HFP Hands-Free" in topology.remedy_notice


def test_to_dict_serialization() -> None:
    """Verify AudioTopology serializes cleanly to dictionary for API telemetry."""
    endpoint = AudioEndpoint(
        index=0,
        name="Test Mic",
        host_api=0,
        max_input_channels=1,
        max_output_channels=0,
        default_sample_rate=44100.0,
        device_type=DeviceType.USB_ENDPOINT,
        is_bluetooth=False,
        is_handsfree=False,
    )
    topology = AudioTopology(
        input_devices=[endpoint],
        output_devices=[],
        recommended_input=endpoint,
        recommended_output=None,
        degradation_risk=False,
        remedy_notice="OK",
    )
    d = topology.to_dict()
    assert d["input_count"] == 1
    assert d["output_count"] == 0
    assert d["recommended_input"]["name"] == "Test Mic"
    assert d["degradation_risk"] is False
