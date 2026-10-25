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
from jarvis.audio.adap_head import ADAPProjectionHead, ADAPPrediction, DEFAULT_REFLEX_ACTIONS
from jarvis.audio.liquid_dynamics import (
    LiquidStateSpaceNetwork,
    LiquidTimeConstantConfig,
    LiquidTrajectoryMetrics,
    LTCSolverType,
)
from jarvis.audio.mose_head import (
    CANONICAL_180_ACTIONS,
    MoSEPrediction,
    MoSEProjectionHead,
)
from jarvis.audio.ssd_vocoder import (
    SSDVocoderFrame,
    SSDVocoderSampleRate,
    StateSpaceStreamingVocoder,
)
from jarvis.audio.subvocal_semg import (
    BioHardwareBridge,
    BioHardwareBridgeTelemetry,
    ContinuousNeuromuscularLTC,
    FilterBankConfig,
    OfflineNeuromuscularSignalGenerator,
    SubvocalIntentResult,
    SubvocalSignalFilter,
    SubvocalTelepathyEngine,
)
from jarvis.audio.wake_word import WakeWordScoreEvent

__all__ = [
    "ADAPPrediction",
    "ADAPProjectionHead",
    "AudioDeviceInfo",
    "AudioDSPProcessor",
    "AudioEngine",
    "AudioEngineMode",
    "BioHardwareBridge",
    "BioHardwareBridgeTelemetry",
    "CANONICAL_180_ACTIONS",
    "calculate_rms",
    "ContinuousNeuromuscularLTC",
    "DEFAULT_REFLEX_ACTIONS",
    "DSPBlockResult",
    "FilterBankConfig",
    "LiquidStateSpaceNetwork",
    "LiquidTimeConstantConfig",
    "LiquidTrajectoryMetrics",
    "LTCSolverType",
    "MicrophoneProbeManager",
    "MoSEPrediction",
    "MoSEProjectionHead",
    "NoiseFloorTracker",
    "OfflineNeuromuscularSignalGenerator",
    "rms_mono",
    "SchmittTrigger",
    "SSDVocoderFrame",
    "SSDVocoderSampleRate",
    "StateSpaceStreamingVocoder",
    "SubvocalIntentResult",
    "SubvocalSignalFilter",
    "SubvocalTelepathyEngine",
    "WakeWordScoreEvent",
]

