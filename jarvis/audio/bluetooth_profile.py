"""
jarvis/audio/bluetooth_profile.py
=================================
Bluetooth Smart Audio Profile Switcher & Endpoint Topology Manager for JARVIS.

Handles Windows & cross-platform Bluetooth audio characteristics:
  - A2DP (Advanced Audio Distribution Profile): 44.1/48kHz pristine stereo playback.
  - HFP/HSP (Hands-Free Profile): 8/16kHz narrowband mono audio.
  - Avoids audio degradation by orchestrating hybrid split topologies
    (using dedicated USB/internal mic for STT to keep Bluetooth playback in high-fidelity A2DP).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("jarvis.audio.bluetooth_profile")


class DeviceType(str, Enum):
    BLUETOOTH_A2DP = "bluetooth_a2dp"
    BLUETOOTH_HFP = "bluetooth_hfp"
    USB_ENDPOINT = "usb_endpoint"
    INTERNAL_OR_ANALOG = "internal_or_analog"
    UNKNOWN = "unknown"


class AudioProfileMode(str, Enum):
    AUTO = "auto"
    A2DP_PREFERRED = "a2dp_preferred"
    HFP_HANDS_FREE = "hfp_hands_free"
    HYBRID_SPLIT = "hybrid_split"


@dataclass
class AudioEndpoint:
    index: int
    name: str
    host_api: int
    max_input_channels: int
    max_output_channels: int
    default_sample_rate: float
    device_type: DeviceType = DeviceType.UNKNOWN
    is_bluetooth: bool = False
    is_handsfree: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "name": self.name,
            "host_api": self.host_api,
            "max_input_channels": self.max_input_channels,
            "max_output_channels": self.max_output_channels,
            "default_sample_rate": self.default_sample_rate,
            "device_type": self.device_type.value,
            "is_bluetooth": self.is_bluetooth,
            "is_handsfree": self.is_handsfree,
        }


@dataclass
class AudioTopology:
    input_devices: list[AudioEndpoint] = field(default_factory=list)
    output_devices: list[AudioEndpoint] = field(default_factory=list)
    recommended_input: AudioEndpoint | None = None
    recommended_output: AudioEndpoint | None = None
    degradation_risk: bool = False
    remedy_notice: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_count": len(self.input_devices),
            "output_count": len(self.output_devices),
            "recommended_input": self.recommended_input.to_dict() if self.recommended_input else None,
            "recommended_output": self.recommended_output.to_dict() if self.recommended_output else None,
            "degradation_risk": self.degradation_risk,
            "remedy_notice": self.remedy_notice,
        }


class BluetoothAudioManager:
    """
    Intelligent audio endpoint orchestrator for high-fidelity speech synthesis and recognition.
    """

    BT_PATTERNS = [
        re.compile(r"bluetooth", re.IGNORECASE),
        re.compile(r"hands-?free", re.IGNORECASE),
        re.compile(r"headset", re.IGNORECASE),
        re.compile(r"airpods", re.IGNORECASE),
        re.compile(r"wh-1000", re.IGNORECASE),
        re.compile(r"wf-1000", re.IGNORECASE),
        re.compile(r"bose", re.IGNORECASE),
        re.compile(r"galaxy buds", re.IGNORECASE),
    ]

    HFP_PATTERNS = [
        re.compile(r"hands-?free", re.IGNORECASE),
        re.compile(r"ag audio", re.IGNORECASE),
        re.compile(r"telephony", re.IGNORECASE),
    ]

    USB_PATTERNS = [
        re.compile(r"usb", re.IGNORECASE),
        re.compile(r"fifine", re.IGNORECASE),
        re.compile(r"blue yeti", re.IGNORECASE),
        re.compile(r"rode", re.IGNORECASE),
        re.compile(r"elgato", re.IGNORECASE),
        re.compile(r"hyperx", re.IGNORECASE),
        re.compile(r"samson", re.IGNORECASE),
    ]

    def __init__(self, mode: AudioProfileMode = AudioProfileMode.AUTO) -> None:
        self.mode = mode

    def classify_device(self, name: str, is_input: bool) -> tuple[DeviceType, bool, bool]:
        """
        Classifies audio device name into DeviceType, is_bluetooth, and is_handsfree flags.
        """
        name_lower = name.lower()

        # Check Bluetooth
        is_bt = any(p.search(name_lower) for p in self.BT_PATTERNS)
        is_hfp = any(p.search(name_lower) for p in self.HFP_PATTERNS)
        is_usb = any(p.search(name_lower) for p in self.USB_PATTERNS)

        if is_bt:
            if is_hfp:
                return DeviceType.BLUETOOTH_HFP, True, True
            return DeviceType.BLUETOOTH_A2DP, True, False

        if is_usb:
            return DeviceType.USB_ENDPOINT, False, False

        return DeviceType.INTERNAL_OR_ANALOG, False, False

    def query_raw_devices(self) -> list[dict[str, Any]]:
        """
        Queries system audio devices via sounddevice.
        Fail-closed: Returns empty list if sounddevice is not available or query fails.
        """
        try:
            import sounddevice as sd  # type: ignore[import-untyped]
            raw = sd.query_devices()
            if isinstance(raw, list):
                return raw
            elif isinstance(raw, dict):
                return [raw]
            return list(raw)
        except Exception as exc:
            logger.debug("sounddevice device query failed: %s", exc)
            return []

    def inspect_audio_topology(self, raw_devices: list[dict[str, Any]] | None = None) -> AudioTopology:
        """
        Builds AudioTopology from enumerated system audio devices.
        """
        devices = raw_devices if raw_devices is not None else self.query_raw_devices()
        input_endpoints: list[AudioEndpoint] = []
        output_endpoints: list[AudioEndpoint] = []

        for idx, dev in enumerate(devices):
            name = str(dev.get("name", f"Device #{idx}"))
            max_in = int(dev.get("max_input_channels", 0))
            max_out = int(dev.get("max_output_channels", 0))
            sr = float(dev.get("default_samplerate", 44100.0))
            api = int(dev.get("hostapi", 0))

            if max_in > 0:
                dev_type, is_bt, is_hfp = self.classify_device(name, is_input=True)
                input_endpoints.append(
                    AudioEndpoint(
                        index=idx,
                        name=name,
                        host_api=api,
                        max_input_channels=max_in,
                        max_output_channels=max_out,
                        default_sample_rate=sr,
                        device_type=dev_type,
                        is_bluetooth=is_bt,
                        is_handsfree=is_hfp,
                    )
                )

            if max_out > 0:
                dev_type, is_bt, is_hfp = self.classify_device(name, is_input=False)
                output_endpoints.append(
                    AudioEndpoint(
                        index=idx,
                        name=name,
                        host_api=api,
                        max_input_channels=max_in,
                        max_output_channels=max_out,
                        default_sample_rate=sr,
                        device_type=dev_type,
                        is_bluetooth=is_bt,
                        is_handsfree=is_hfp,
                    )
                )

        # Resolve recommendation
        rec_in, rec_out, risk, remedy = self._resolve_strategy(input_endpoints, output_endpoints)

        return AudioTopology(
            input_devices=input_endpoints,
            output_devices=output_endpoints,
            recommended_input=rec_in,
            recommended_output=rec_out,
            degradation_risk=risk,
            remedy_notice=remedy,
        )

    def _resolve_strategy(
        self,
        inputs: list[AudioEndpoint],
        outputs: list[AudioEndpoint],
    ) -> tuple[AudioEndpoint | None, AudioEndpoint | None, bool, str]:
        """
        Calculates optimal pairing based on configured AudioProfileMode.
        """
        if not outputs and not inputs:
            return None, None, False, "No audio endpoints detected on system."

        # Preferred output: Bluetooth A2DP if present, else first output
        preferred_out: AudioEndpoint | None = None
        bt_a2dp_outputs = [o for o in outputs if o.device_type == DeviceType.BLUETOOTH_A2DP]
        if bt_a2dp_outputs:
            preferred_out = bt_a2dp_outputs[0]
        elif outputs:
            preferred_out = outputs[0]

        # Check alternative non-bluetooth microphones
        usb_inputs = [i for i in inputs if i.device_type == DeviceType.USB_ENDPOINT]
        internal_inputs = [i for i in inputs if i.device_type == DeviceType.INTERNAL_OR_ANALOG]
        bt_inputs = [i for i in inputs if i.is_bluetooth]

        preferred_in: AudioEndpoint | None = None
        degradation_risk = False
        remedy = ""

        if self.mode == AudioProfileMode.HFP_HANDS_FREE:
            # Enforce HFP
            preferred_in = bt_inputs[0] if bt_inputs else (inputs[0] if inputs else None)
            hfp_outs = [o for o in outputs if o.is_handsfree]
            if hfp_outs:
                preferred_out = hfp_outs[0]
            remedy = "Active profile set to HFP Hands-Free telephony mode."

        elif self.mode in (AudioProfileMode.AUTO, AudioProfileMode.A2DP_PREFERRED, AudioProfileMode.HYBRID_SPLIT):
            # Prioritize USB mic > Internal mic to keep BT in A2DP stereo
            if preferred_out and preferred_out.is_bluetooth:
                if usb_inputs:
                    preferred_in = usb_inputs[0]
                    remedy = f"Hybrid split active: Recording via USB '{preferred_in.name}', preserving A2DP stereo for '{preferred_out.name}'."
                elif internal_inputs:
                    preferred_in = internal_inputs[0]
                    remedy = f"Hybrid split active: Recording via internal '{preferred_in.name}', preserving A2DP stereo for '{preferred_out.name}'."
                elif bt_inputs:
                    preferred_in = bt_inputs[0]
                    degradation_risk = True
                    remedy = (
                        f"Warning: Only Bluetooth mic '{preferred_in.name}' detected. "
                        f"Opening this mic will force '{preferred_out.name}' into 16kHz mono HFP mode. "
                        "Connect a dedicated USB mic to unlock full 48kHz A2DP playback."
                    )
            else:
                preferred_in = usb_inputs[0] if usb_inputs else (internal_inputs[0] if internal_inputs else (inputs[0] if inputs else None))
                remedy = "Standard wired/internal audio pipeline active."

        return preferred_in, preferred_out, degradation_risk, remedy
