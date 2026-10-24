"""
jarvis/hardware/universal_hal.py
================================
Universal Hardware Abstraction Layer (UHAL) & Dynamic Device Tiering.
Engineered for Argon Sovereign Frontier 11.0.

Architectural Principles:
  1. Universal Cross-Device Compatibility:
     Operates seamlessly across heterogeneous hardware profiles:
     - x86-64 (Intel Core i3/i5/i7/i9, AMD Ryzen, Intel Celeron/N100)
     - ARM64 (Snapdragon X Elite, Snapdragon X Plus, Surface Pro 11, Apple Silicon via emulation)
     - Multi-vendor accelerators (NVIDIA CUDA, AMD DirectML, Intel Arc/OpenVINO, Qualcomm QNN)
     - Headless servers & virtual machines (AWS, Azure, Hyper-V)
  2. Four Standardized Hardware Tiers:
     - Tier 1: Micro-Edge (Nano)    - RAM <= 4-6GB, Cores <= 4, Budget <= 64 MB
     - Tier 2: Mainstream (Standard) - RAM 8-16GB, Cores 6-8, Budget <= 256 MB (Host default)
     - Tier 3: Power Edge (Pro)     - RAM 16-32GB, dGPU 6-12GB, Budget <= 1.5 GB
     - Tier 4: Sovereign Studio     - RAM >= 32GB, dGPU >= 16GB, Budget <= 8.0 GB
  3. Zero-Exception Hardware Probing:
     Uses native Win32 Ctypes APIs (IsProcessorFeaturePresent, GetSystemPowerStatus,
     GlobalMemoryStatusEx) with pure fallback defaults if running on non-Windows or virtualised containers.
"""
from __future__ import annotations

import ctypes
import enum
import logging
import os
import platform
import subprocess
import sys
from ctypes import wintypes
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("jarvis.hardware.universal_hal")


# ---------------------------------------------------------------------------
# Win32 Processor Feature Constants
# ---------------------------------------------------------------------------
# Reference: https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-isprocessorfeaturepresent
PF_FLOATING_POINT_PRECISION_ERRATA = 0
PF_FLOATING_POINT_EMULATION = 1
PF_COMPARE_EXCHANGE_DOUBLE = 2
PF_MMX_INSTRUCTIONS_AVAILABLE = 3
PF_XMMI_INSTRUCTIONS_AVAILABLE = 6         # SSE
PF_3DNOW_INSTRUCTIONS_AVAILABLE = 7
PF_RDTSC_INSTRUCTION_AVAILABLE = 8
PF_PAE_ENABLED = 9
PF_XMMI64_INSTRUCTIONS_AVAILABLE = 10     # SSE2
PF_SSE3_INSTRUCTIONS_AVAILABLE = 13
PF_COMPARE_EXCHANGE128 = 14
PF_COMPARE64_EXCHANGE128 = 15
PF_CHANNELS_ENABLED = 16
PF_XSAVE_ENABLED = 17
PF_ARM_VFP_32_REGISTERS_AVAILABLE = 18
PF_ARM_NEON_INSTRUCTIONS_AVAILABLE = 19
PF_SECOND_LEVEL_ADDRESS_TRANSLATION = 20
PF_VIRT_FIRMWARE_ENABLED = 21
PF_RDWRFSGSBASE_AVAILABLE = 22
PF_FASTFAIL_AVAILABLE = 23
PF_ARM_DIVIDE_INSTRUCTION_AVAILABLE = 24
PF_ARM_64BIT_LOADSTORE_ATOMIC = 25
PF_ARM_EXTERNAL_CACHE_AVAILABLE = 26
PF_ARM_FMAC_INSTRUCTIONS_AVAILABLE = 27
PF_ARM_V8_INSTRUCTIONS_AVAILABLE = 29
PF_ARM_V8_CRYPTO_INSTRUCTIONS_AVAILABLE = 30
PF_ARM_V8_CRC32_INSTRUCTIONS_AVAILABLE = 31
PF_AVX2_INSTRUCTIONS_AVAILABLE = 40
PF_AVX512F_INSTRUCTIONS_AVAILABLE = 41


class SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", wintypes.BYTE),         # 0=Offline (Battery), 1=Online (AC), 255=Unknown
        ("BatteryFlag", wintypes.BYTE),          # 1=High, 2=Low, 4=Critical, 8=Charging, 128=No battery, 255=Unknown
        ("BatteryLifePercent", wintypes.BYTE),   # 0-100, 255=Unknown
        ("SystemStatusFlag", wintypes.BYTE),     # 1=Battery Saver active, 0=inactive
        ("BatteryLifeTime", wintypes.DWORD),     # Seconds remaining or -1
        ("BatteryFullLifeTime", wintypes.DWORD), # Seconds full or -1
    ]


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", wintypes.DWORD),
        ("dwMemoryLoad", wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_uint64),
        ("ullAvailPhys", ctypes.c_uint64),
        ("ullTotalPageFile", ctypes.c_uint64),
        ("ullAvailPageFile", ctypes.c_uint64),
        ("ullTotalVirtual", ctypes.c_uint64),
        ("ullAvailVirtual", ctypes.c_uint64),
        ("ullAvailExtendedVirtual", ctypes.c_uint64),
    ]


class HardwareTier(str, enum.Enum):
    """Normalized hardware capability tier for adaptive resource allocation."""
    TIER_1_MICRO_EDGE = "TIER_1_MICRO_EDGE"     # <= 4-6GB RAM, <= 4 cores, integrated GPU / no dGPU
    TIER_2_MAINSTREAM = "TIER_2_MAINSTREAM"     # 8-16GB RAM, 6-8 cores, entry dGPU <= 4GB VRAM
    TIER_3_POWER_EDGE = "TIER_3_POWER_EDGE"     # 16-32GB RAM, >= 8 cores, dGPU 6-12GB VRAM
    TIER_4_SOVEREIGN_STUDIO = "TIER_4_SOVEREIGN_STUDIO"  # >= 32GB RAM, dGPU >= 16GB VRAM


class CPUArchitecture(str, enum.Enum):
    """Detected CPU instruction set architecture."""
    X86_64 = "x86_64"
    ARM64 = "arm64"
    X86_32 = "x86_32"
    UNKNOWN = "unknown"


class AcceleratorBackend(str, enum.Enum):
    """Available neural inference and math acceleration backends."""
    CUDA = "cuda"                 # NVIDIA CUDA runtime
    DIRECTML = "directml"         # DirectX 12 Compute Shaders (AMD, Intel, Qualcomm, NVIDIA)
    OPENVINO = "openvino"         # Intel OpenVINO runtime
    QNN = "qnn"                   # Qualcomm Neural Processing SDK
    CPU_SIMD = "cpu_simd"         # AVX2/AVX-512 or ARM NEON
    PURE_FALLBACK = "pure_c"      # Pure C / Python math fallback (Zero dependencies)


@dataclass(frozen=True)
class ISACapabilities:
    """Detailed SIMD instruction set capabilities of the host processor."""
    has_avx: bool = False
    has_avx2: bool = False
    has_avx512: bool = False
    has_arm_neon: bool = False
    has_arm_v8: bool = False
    has_rdtsc: bool = True
    has_sse2: bool = True
    has_sse42: bool = False


@dataclass(frozen=True)
class PowerProfile:
    """Operating power source and battery telemetry."""
    is_ac_connected: bool
    is_battery_saver: bool
    battery_percentage: int
    is_charging: bool
    is_unknown: bool = False


@dataclass(frozen=True)
class DeviceProfile:
    """
    Comprehensive device capability matrix and adaptive resource budget.
    """
    tier: HardwareTier
    architecture: CPUArchitecture
    physical_cores: int
    logical_cores: int
    total_ram_gb: float
    available_ram_gb: float
    gpu_name: str
    total_vram_mib: float
    free_vram_mib: float
    primary_backend: AcceleratorBackend
    supported_backends: tuple[AcceleratorBackend, ...]
    isa: ISACapabilities
    power: PowerProfile
    is_headless: bool
    
    # Adaptive Budgets Computed for this Device:
    max_memory_budget_mb: float
    crrsp_buffer_budget_kb: float
    mamba2_layer_count: int
    mamba2_target_stride_ms: int
    allow_speculative_prewarming: bool
    recommended_quantization: str  # "INT8", "FP16", "FP32"

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier.value,
            "architecture": self.architecture.value,
            "cores": {
                "physical": self.physical_cores,
                "logical": self.logical_cores,
            },
            "ram": {
                "total_gb": round(self.total_ram_gb, 2),
                "available_gb": round(self.available_ram_gb, 2),
            },
            "gpu": {
                "name": self.gpu_name,
                "total_vram_mib": round(self.total_vram_mib, 1),
                "free_vram_mib": round(self.free_vram_mib, 1),
            },
            "primary_backend": self.primary_backend.value,
            "supported_backends": [b.value for b in self.supported_backends],
            "isa": {
                "avx": self.isa.has_avx,
                "avx2": self.isa.has_avx2,
                "avx512": self.isa.has_avx512,
                "neon": self.isa.has_arm_neon,
            },
            "power": {
                "ac_online": self.power.is_ac_connected,
                "battery_saver": self.power.is_battery_saver,
                "battery_pct": self.power.battery_percentage,
            },
            "adaptive_budgets": {
                "max_memory_mb": self.max_memory_budget_mb,
                "crrsp_buffer_kb": self.crrsp_buffer_budget_kb,
                "mamba2_layers": self.mamba2_layer_count,
                "mamba2_stride_ms": self.mamba2_target_stride_ms,
                "speculative_prewarming": self.allow_speculative_prewarming,
                "quantization": self.recommended_quantization,
            },
            "is_headless": self.is_headless,
        }


class UniversalHardwareAbstractionLayer:
    """
    Universal Hardware Abstraction Layer (UHAL) for JARVIS.
    Detects host device capabilities and dynamically configures engine budgets.
    """

    def __init__(self, override_profile: DeviceProfile | None = None) -> None:
        self._override = override_profile
        self._cached_profile: DeviceProfile | None = None

    def probe_device(self, force_refresh: bool = False) -> DeviceProfile:
        """
        Probes the physical or virtual device and builds the active DeviceProfile.
        """
        if self._override is not None:
            return self._override

        if self._cached_profile is not None and not force_refresh:
            return self._cached_profile

        # 1. Architecture & ISA
        arch, isa = self._probe_cpu_architecture_and_isa()

        # 2. Cores & RAM
        phys_cores, log_cores = self._probe_cores()
        total_ram_gb, avail_ram_gb = self._probe_ram()

        # 3. GPU & VRAM
        gpu_name, total_vram_mib, free_vram_mib = self._probe_gpu()

        # 4. Power & Battery
        power = self._probe_power_status()

        # 5. Headless detection
        is_headless = self._probe_is_headless()

        # 6. Accelerators & Backends
        backends, primary_backend = self._determine_backends(arch, gpu_name, isa)

        # 7. Dynamic Hardware Tier Classification
        tier = self._classify_hardware_tier(
            total_ram_gb=total_ram_gb,
            avail_ram_gb=avail_ram_gb,
            physical_cores=phys_cores,
            total_vram_mib=total_vram_mib,
            is_battery_saver=power.is_battery_saver,
        )

        # 8. Compute Adaptive Budgets based on Tier and Power
        budgets = self._calculate_adaptive_budgets(tier, power)

        profile = DeviceProfile(
            tier=tier,
            architecture=arch,
            physical_cores=phys_cores,
            logical_cores=log_cores,
            total_ram_gb=total_ram_gb,
            available_ram_gb=avail_ram_gb,
            gpu_name=gpu_name,
            total_vram_mib=total_vram_mib,
            free_vram_mib=free_vram_mib,
            primary_backend=primary_backend,
            supported_backends=tuple(backends),
            isa=isa,
            power=power,
            is_headless=is_headless,
            max_memory_budget_mb=budgets["max_memory_mb"],
            crrsp_buffer_budget_kb=budgets["crrsp_buffer_kb"],
            mamba2_layer_count=budgets["mamba2_layers"],
            mamba2_target_stride_ms=budgets["mamba2_stride_ms"],
            allow_speculative_prewarming=budgets["allow_prewarming"],
            recommended_quantization=budgets["quantization"],
        )

        self._cached_profile = profile
        logger.info(
            "UHAL Probe complete: Tier=%s, Arch=%s, RAM=%.1fGB (Avail=%.1fGB), Primary=%s, Quant=%s",
            profile.tier.value,
            profile.architecture.value,
            profile.total_ram_gb,
            profile.available_ram_gb,
            profile.primary_backend.value,
            profile.recommended_quantization,
        )
        return profile

    def _probe_cpu_architecture_and_isa(self) -> tuple[CPUArchitecture, ISACapabilities]:
        raw_mach = platform.machine().lower()
        if "arm" in raw_mach or "aarch64" in raw_mach:
            arch = CPUArchitecture.ARM64
        elif "x86" in raw_mach or "amd64" in raw_mach or "i386" in raw_mach or "i686" in raw_mach:
            arch = CPUArchitecture.X86_64
        else:
            arch = CPUArchitecture.UNKNOWN

        # Query Win32 IsProcessorFeaturePresent if on Windows
        has_avx2 = False
        has_avx512 = False
        has_neon = False
        has_v8 = False
        has_sse2 = True

        if sys.platform == "win32":
            try:
                k32 = ctypes.windll.kernel32
                if arch == CPUArchitecture.X86_64:
                    has_avx2 = bool(k32.IsProcessorFeaturePresent(PF_AVX2_INSTRUCTIONS_AVAILABLE))
                    has_avx512 = bool(k32.IsProcessorFeaturePresent(PF_AVX512F_INSTRUCTIONS_AVAILABLE))
                    has_sse2 = bool(k32.IsProcessorFeaturePresent(PF_XMMI64_INSTRUCTIONS_AVAILABLE))
                elif arch == CPUArchitecture.ARM64:
                    has_neon = bool(k32.IsProcessorFeaturePresent(PF_ARM_NEON_INSTRUCTIONS_AVAILABLE))
                    has_v8 = bool(k32.IsProcessorFeaturePresent(PF_ARM_V8_INSTRUCTIONS_AVAILABLE))
            except Exception as exc:
                logger.debug("Win32 IsProcessorFeaturePresent probe warning: %s", exc)
                # Fallback heuristics
                has_avx2 = (arch == CPUArchitecture.X86_64)
                has_neon = (arch == CPUArchitecture.ARM64)
        else:
            has_avx2 = (arch == CPUArchitecture.X86_64)
            has_neon = (arch == CPUArchitecture.ARM64)

        isa = ISACapabilities(
            has_avx=has_avx2,
            has_avx2=has_avx2,
            has_avx512=has_avx512,
            has_arm_neon=has_neon,
            has_arm_v8=has_v8,
            has_sse2=has_sse2,
        )
        return arch, isa

    def _probe_cores(self) -> tuple[int, int]:
        log_cores = os.cpu_count() or 4
        # Estimate physical cores if not detectable via psutil
        phys_cores = max(1, log_cores // 2)
        try:
            import psutil
            phys = psutil.cpu_count(logical=False)
            if phys:
                phys_cores = phys
        except Exception:
            pass
        return phys_cores, log_cores

    def _probe_ram(self) -> tuple[float, float]:
        if sys.platform == "win32":
            try:
                k32 = ctypes.windll.kernel32
                stat = MEMORYSTATUSEX()
                stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                if k32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                    total_gb = stat.ullTotalPhys / (1024**3)
                    avail_gb = stat.ullAvailPhys / (1024**3)
                    return float(total_gb), float(avail_gb)
            except Exception:
                pass

        # Fallback via psutil or system defaults
        try:
            import psutil
            vm = psutil.virtual_memory()
            return float(vm.total / (1024**3)), float(vm.available / (1024**3))
        except Exception:
            return 8.0, 3.0

    def _probe_gpu(self) -> tuple[str, float, float]:
        # 1. Try nvidia-smi
        try:
            cmd = ["nvidia-smi", "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"]
            out = subprocess.check_output(cmd, creationflags=0x08000000, timeout=1.5).decode("utf-8").strip()
            if out:
                line = out.split("\n")[0]
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 3:
                    return parts[0], float(parts[1]), float(parts[2])
        except Exception:
            pass

        # 2. Check for integrated Intel / AMD / Qualcomm via PowerShell CIM / WMI
        if sys.platform == "win32":
            try:
                ps_cmd = "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"
                out = subprocess.check_output(["powershell", "-NoProfile", "-Command", ps_cmd], creationflags=0x08000000, timeout=1.5).decode("utf-8").strip()
                if out:
                    first_gpu = out.split("\n")[0].strip()
                    # Integrated GPU shares system RAM
                    return first_gpu, 2048.0, 1024.0
            except Exception:
                pass

        return "Standard Display Adapter", 0.0, 0.0

    def _probe_power_status(self) -> PowerProfile:
        if sys.platform == "win32":
            try:
                k32 = ctypes.windll.kernel32
                sps = SYSTEM_POWER_STATUS()
                if k32.GetSystemPowerStatus(ctypes.byref(sps)):
                    is_ac = (sps.ACLineStatus == 1)
                    is_battery_saver = bool(sps.SystemStatusFlag == 1)
                    pct = int(sps.BatteryLifePercent) if sps.BatteryLifePercent <= 100 else 100
                    is_charging = bool(sps.BatteryFlag & 8)
                    return PowerProfile(
                        is_ac_connected=is_ac,
                        is_battery_saver=is_battery_saver,
                        battery_percentage=pct,
                        is_charging=is_charging,
                        is_unknown=(sps.ACLineStatus == 255),
                    )
            except Exception:
                pass

        # Default to AC connected
        return PowerProfile(
            is_ac_connected=True,
            is_battery_saver=False,
            battery_percentage=100,
            is_charging=False,
            is_unknown=True,
        )

    def _probe_is_headless(self) -> bool:
        if sys.platform == "win32":
            try:
                user32 = ctypes.windll.user32
                # GetSystemMetrics(SM_REMOTESESSION) = 0x1000
                is_remote = bool(user32.GetSystemMetrics(0x1000))
                has_desktop = bool(user32.GetDesktopWindow())
                return is_remote or not has_desktop
            except Exception:
                return False
        return True

    def _determine_backends(
        self,
        arch: CPUArchitecture,
        gpu_name: str,
        isa: ISACapabilities,
    ) -> tuple[list[AcceleratorBackend], AcceleratorBackend]:
        backends: list[AcceleratorBackend] = [AcceleratorBackend.PURE_FALLBACK]

        # CPU SIMD is always available if x86 (AVX2/SSE) or ARM (NEON)
        if isa.has_avx2 or isa.has_arm_neon:
            backends.append(AcceleratorBackend.CPU_SIMD)

        gpu_lower = gpu_name.lower()

        # NVIDIA CUDA
        has_cuda = "nvidia" in gpu_lower or "geforce" in gpu_lower or "rtx" in gpu_lower or "gtx" in gpu_lower
        if has_cuda:
            backends.append(AcceleratorBackend.CUDA)

        # DirectML (Runs on AMD, Intel, Qualcomm, NVIDIA on Windows DirectX 12)
        if sys.platform == "win32":
            backends.append(AcceleratorBackend.DIRECTML)

        # OpenVINO (Intel)
        if "intel" in gpu_lower or "iris" in gpu_lower or "arc" in gpu_lower:
            backends.append(AcceleratorBackend.OPENVINO)

        # Qualcomm QNN (Snapdragon)
        if arch == CPUArchitecture.ARM64 or "qualcomm" in gpu_lower or "adreno" in gpu_lower or "snapdragon" in gpu_lower:
            backends.append(AcceleratorBackend.QNN)

        # Primary selection priority:
        if has_cuda:
            primary = AcceleratorBackend.CUDA
        elif AcceleratorBackend.DIRECTML in backends and "standard" not in gpu_lower and gpu_name:
            primary = AcceleratorBackend.DIRECTML
        elif AcceleratorBackend.CPU_SIMD in backends:
            primary = AcceleratorBackend.CPU_SIMD
        else:
            primary = AcceleratorBackend.PURE_FALLBACK

        return backends, primary

    def _classify_hardware_tier(
        self,
        total_ram_gb: float,
        avail_ram_gb: float,
        physical_cores: int,
        total_vram_mib: float,
        is_battery_saver: bool,
    ) -> HardwareTier:
        # If battery saver is active and available RAM is restricted, step down tier to preserve life
        if is_battery_saver and avail_ram_gb < 2.5:
            return HardwareTier.TIER_1_MICRO_EDGE

        # Tier 4: Sovereign Studio
        if total_ram_gb >= 30.0 and total_vram_mib >= 15000.0:
            return HardwareTier.TIER_4_SOVEREIGN_STUDIO

        # Tier 3: Power Edge
        if (total_ram_gb >= 15.0 and total_vram_mib >= 5500.0) or (total_ram_gb >= 30.0 and physical_cores >= 8):
            return HardwareTier.TIER_3_POWER_EDGE

        # Tier 2: Mainstream (Standard developer laptop, e.g. 16GB RAM + 4GB VRAM)
        if total_ram_gb >= 7.5 and physical_cores >= 4:
            return HardwareTier.TIER_2_MAINSTREAM

        # Tier 1: Micro-Edge (Celeron, 4GB RAM, ultra low power)
        return HardwareTier.TIER_1_MICRO_EDGE

    def _calculate_adaptive_budgets(
        self,
        tier: HardwareTier,
        power: PowerProfile,
    ) -> dict[str, Any]:
        if tier == HardwareTier.TIER_1_MICRO_EDGE:
            return {
                "max_memory_mb": 64.0,
                "crrsp_buffer_kb": 64.0,           # Compressed INT8 ring buffer
                "mamba2_layers": 2,                 # Lightweight 2 layers
                "mamba2_stride_ms": 64 if power.is_ac_connected else 128,
                "allow_prewarming": False,          # Conserve connection budget
                "quantization": "INT8",
            }
        elif tier == HardwareTier.TIER_2_MAINSTREAM:
            return {
                "max_memory_mb": 256.0,
                "crrsp_buffer_kb": 256.0,          # Standard FP16 buffer
                "mamba2_layers": 4,                 # 4 layers
                "mamba2_stride_ms": 32,
                "allow_prewarming": True,
                "quantization": "FP16",
            }
        elif tier == HardwareTier.TIER_3_POWER_EDGE:
            return {
                "max_memory_mb": 1536.0,
                "crrsp_buffer_kb": 512.0,          # High-fidelity buffer
                "mamba2_layers": 6,                 # 6 layers
                "mamba2_stride_ms": 20,
                "allow_prewarming": True,
                "quantization": "FP16",
            }
        else:  # TIER_4_SOVEREIGN_STUDIO
            return {
                "max_memory_mb": 8192.0,
                "crrsp_buffer_kb": 1024.0,         # Maximum precision
                "mamba2_layers": 8,                 # 8 layers
                "mamba2_stride_ms": 16,
                "allow_prewarming": True,
                "quantization": "FP32",
            }


# Singleton factory
_GLOBAL_UHAL: UniversalHardwareAbstractionLayer | None = None


def get_universal_hal() -> UniversalHardwareAbstractionLayer:
    """Retrieves or initializes the global UniversalHardwareAbstractionLayer singleton."""
    global _GLOBAL_UHAL
    if _GLOBAL_UHAL is None:
        _GLOBAL_UHAL = UniversalHardwareAbstractionLayer()
    return _GLOBAL_UHAL
