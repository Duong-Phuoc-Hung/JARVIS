"""
Audio subsystem package for JARVIS.
Provides acoustic DSP math, noise floor tracking, Schmitt trigger transient detection,
and thread-safe SoundDevice audio stream capture.
"""
from jarvis.audio.dsp import (
    AudioDSPProcessor,
    DSPBlockResult,
    NoiseFloorTracker,
    SchmittTrigger,
    calculate_rms,
    rms_mono,
)
from jarvis.audio.engine import (
    AudioDeviceInfo,
    AudioEngine,
    AudioEngineMode,
    MicrophoneProbeManager,
)

__all__ = [
    "AudioDSPProcessor",
    "DSPBlockResult",
    "NoiseFloorTracker",
    "SchmittTrigger",
    "calculate_rms",
    "rms_mono",
    "AudioDeviceInfo",
    "AudioEngine",
    "AudioEngineMode",
    "MicrophoneProbeManager",
]
