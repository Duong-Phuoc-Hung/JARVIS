"""
jarvis/hardware
===============
Hardware Telemetry, S.M.A.R.T. Prober, and Voice Diagnostic Alerting Package.
Features:
  - F-20: Multi-source Hardware Telemetry (CPU, GPU, RAM, VRAM, fan speeds).
  - F-21: S.M.A.R.T. Disk Health Prober and Volume Diagnostics.
  - F-22: Vocal Threshold Alerts & Natural Language Query Engine.
"""
from __future__ import annotations

from jarvis.hardware.eco_governor import (
    AdaptiveEcoGovernor,
    EcoLevel,
    GovernancePolicy,
)
from jarvis.hardware.fpga_crystallizer import (
    ComputationalKernelType,
    FPGABitstreamArtifact,
    FPGABridgeTelemetry,
    FPGAHardwareBridge,
    FPGAVendorTarget,
    GraphToRTLCompiler,
    InSituBitstreamGenerator,
    SynthesizedRTLModule,
    SystolicArrayGenerator,
    SystolicDataflow,
)
from jarvis.hardware.holographic_memory import (
    AssociativeRetrievalResult,
    BekensteinHawkingBoundTracker,
    HologramRecord,
    HolographicAssociativeMemory,
    HolographicBoundTelemetry,
    HolographicInformationLimitExceeded,
    MERAEntanglementLayer,
    MERATensorNetwork,
    OpticalFourierHologramEngine,
)
from jarvis.hardware.kernel_telepathy import (
    FramePresentationToken,
    HIDPacketType,
    KernelDeviceDriverHandle,
    KernelInterceptorBackend,
    KernelTelepathyEngine,
    KernelTelepathyStatus,
    KernelTelepathyTelemetry,
    USBHIDHardwarePacket,
)
from jarvis.hardware.monitor import (
    DiskSmartMetrics,
    DiskSmartStatus,
    HardwareMetrics,
    HardwareMonitor,
)
from jarvis.hardware.neuromorphic_lif import (
    HardwareLIFCoProcessor,
    LIFCoProcessorBackend,
    LIFNeuronParameters,
    NeuromorphicSpikeEvent,
    NeuromorphicSpikeTrain,
)
from jarvis.hardware.photonic_bridge import (
    MZICell,
    MZIMesh,
    PhotonicBridgeTelemetry,
    PhotonicHardwareBridge,
    PhotonicPhysicalMetrics,
    PhotonicTensorCore,
)
from jarvis.hardware.polyhedral_jit import (
    AffineCacheScheduler,
    CacheSchedulePlan,
    CrystallizedMemory,
    JITCompiledFunction,
    MachineCodeCrystallizer,
    PolyhedralDomainBounds,
    PolyhedralIterationDomain,
)
from jarvis.hardware.polyglot_runtime import (
    ExecutionTelemetry,
    PolyglotInferenceEngine,
)
from jarvis.hardware.reporter import HardwareReporter
from jarvis.hardware.reversible_computing import (
    AdiabaticMemoryRecycler,
    FeynmanGate,
    FredkinGate,
    LandauerEntropyTracker,
    LandauerTelemetry,
    ReversibleBlock,
    ReversibleVSAEngine,
    ToffoliGate,
)
from jarvis.hardware.universal_hal import (
    AcceleratorBackend,
    CPUArchitecture,
    DeviceProfile,
    HardwareTier,
    ISACapabilities,
    PowerProfile,
    UniversalHardwareAbstractionLayer,
    get_universal_hal,
)

__all__ = [
    "AcceleratorBackend",
    "AdaptiveEcoGovernor",
    "AdiabaticMemoryRecycler",
    "AffineCacheScheduler",
    "AssociativeRetrievalResult",
    "BekensteinHawkingBoundTracker",
    "CPUArchitecture",
    "CacheSchedulePlan",
    "ComputationalKernelType",
    "CrystallizedMemory",
    "DeviceProfile",
    "DiskSmartMetrics",
    "DiskSmartStatus",
    "EcoLevel",
    "ExecutionTelemetry",
    "FPGABitstreamArtifact",
    "FPGABridgeTelemetry",
    "FPGAHardwareBridge",
    "FPGAVendorTarget",
    "FeynmanGate",
    "FramePresentationToken",
    "FredkinGate",
    "GovernancePolicy",
    "GraphToRTLCompiler",
    "HardwareLIFCoProcessor",
    "HardwareMetrics",
    "HardwareMonitor",
    "HardwareReporter",
    "HardwareTier",
    "HIDPacketType",
    "HologramRecord",
    "HolographicAssociativeMemory",
    "HolographicBoundTelemetry",
    "HolographicInformationLimitExceeded",
    "ISACapabilities",
    "InSituBitstreamGenerator",
    "JITCompiledFunction",
    "KernelDeviceDriverHandle",
    "KernelInterceptorBackend",
    "KernelTelepathyEngine",
    "KernelTelepathyStatus",
    "KernelTelepathyTelemetry",
    "LIFCoProcessorBackend",
    "LIFNeuronParameters",
    "LandauerEntropyTracker",
    "LandauerTelemetry",
    "MERAEntanglementLayer",
    "MERATensorNetwork",
    "MZICell",
    "MZIMesh",
    "MachineCodeCrystallizer",
    "NeuromorphicSpikeEvent",
    "NeuromorphicSpikeTrain",
    "OpticalFourierHologramEngine",
    "PhotonicBridgeTelemetry",
    "PhotonicHardwareBridge",
    "PhotonicPhysicalMetrics",
    "PhotonicTensorCore",
    "PolyhedralDomainBounds",
    "PolyhedralIterationDomain",
    "PolyglotInferenceEngine",
    "PowerProfile",
    "ReversibleBlock",
    "ReversibleVSAEngine",
    "SynthesizedRTLModule",
    "SystolicArrayGenerator",
    "SystolicDataflow",
    "ToffoliGate",
    "UniversalHardwareAbstractionLayer",
    "USBHIDHardwarePacket",
    "get_universal_hal",
]
