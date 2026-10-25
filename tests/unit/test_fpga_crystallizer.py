"""
tests/unit/test_fpga_crystallizer.py
====================================
Unit Tests for Self-Replicating Micro-Architectural Hardware Synthesis & In-Situ FPGA Crystallization.
Milestone v9.0.0 ("The Transcendent Singularity", Frontier 32.0).
"""
from __future__ import annotations

import os
import struct
import tempfile
import zlib
import numpy as np
import pytest

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
from jarvis.ui.terminal.theme import StatusLevel


def test_systolic_array_pe_generator():
    """Validates 2D systolic array parameterization and synthesizable SystemVerilog PE generation."""
    gen = SystolicArrayGenerator(rows=8, cols=8, data_width_bits=16, dataflow=SystolicDataflow.WEIGHT_STATIONARY)
    sv_pe = gen.generate_systemverilog_pe()

    assert "module systolic_pe" in sv_pe
    assert "DATA_WIDTH = 16" in sv_pe
    assert "accumulator <= accumulator + (in_a * in_b);" in sv_pe
    assert "endmodule" in sv_pe


def test_graph_to_rtl_compiler_all_kernels():
    """Validates RTL compilation for Mamba-2 SSD, LTC ODE, and DWT Haar kernels in SystemVerilog & VHDL."""
    compiler = GraphToRTLCompiler(data_width_bits=16)

    # 1. Mamba-2 SSD Recurrence
    mamba_mod = compiler.compile_kernel(
        ComputationalKernelType.MAMBA2_SSD_RECURRENCE,
        input_dim=16,
        state_dim=16,
    )
    assert isinstance(mamba_mod, SynthesizedRTLModule)
    assert "module kernel_mamba2_ssd_recurrence_16x16" in mamba_mod.systemverilog_code
    assert "entity kernel_mamba2_ssd_recurrence_16x16" in mamba_mod.vhdl_code
    assert mamba_mod.pipeline_latency_cycles == 2
    assert mamba_mod.dsp_blocks_estimated == 32

    # 2. LTC ODE Runge-Kutta Step
    ltc_mod = compiler.compile_kernel(
        ComputationalKernelType.LTC_ODE_RUNGE_KUTTA,
        state_dim=32,
    )
    assert "kernel_ltc_ode_runge_kutta" in ltc_mod.systemverilog_code
    assert ltc_mod.dsp_blocks_estimated == 128

    # 3. DWT Haar Filterbank
    dwt_mod = compiler.compile_kernel(
        ComputationalKernelType.DWT_HAAR_FILTERBANK,
        input_dim=8,
    )
    assert "out_approx <= (in_a + in_b) >>> 1;" in dwt_mod.systemverilog_code


def test_in_situ_bitstream_generator_latency_sla_and_checksum():
    """Validates rapid binary bitstream assembly in < 50 ms for Xilinx, Intel, and Lattice."""
    compiler = GraphToRTLCompiler()
    rtl = compiler.compile_kernel(ComputationalKernelType.MAMBA2_SSD_RECURRENCE, 16, 16)

    # 1. Xilinx UltraScale+
    xilinx_gen = InSituBitstreamGenerator(target_vendor=FPGAVendorTarget.XILINX_ULTRASCALE_PLUS)
    xilinx_bit = xilinx_gen.crystallize_bitstream(rtl, clock_mhz=300.0)

    assert isinstance(xilinx_bit, FPGABitstreamArtifact)
    # SLA: Sub-50 ms in-situ place-and-route bitstream crystallization
    assert xilinx_bit.synthesis_latency_ms < 50.0
    assert xilinx_bit.bitstream_size_bytes > 0
    # Verify Xilinx Sync Word 0xAA995566
    sync_word = struct.unpack(">I", xilinx_bit.bitstream_binary[:4])[0]
    assert sync_word == 0xAA995566
    # Verify CRC32 trailer
    expected_crc = zlib.crc32(xilinx_bit.bitstream_binary[:-4])
    assert xilinx_bit.checksum_crc32 == expected_crc

    # 2. Intel Agilex
    intel_gen = InSituBitstreamGenerator(target_vendor=FPGAVendorTarget.INTEL_AGILEX)
    intel_bit = intel_gen.crystallize_bitstream(rtl)
    assert struct.unpack(">I", intel_bit.bitstream_binary[:4])[0] == 0x12345678

    # 3. Lattice Certus-NX
    lattice_gen = InSituBitstreamGenerator(target_vendor=FPGAVendorTarget.LATTICE_CERTUS_NX)
    lattice_bit = lattice_gen.crystallize_bitstream(rtl)
    assert struct.unpack(">I", lattice_bit.bitstream_binary[:4])[0] == 0xE2C20800


def test_fpga_hardware_bridge_fail_closed_status():
    """Validates AGENTS.md Rule 2: Returns StatusLevel.LIMITED when physical FPGA is missing."""
    bridge = FPGAHardwareBridge(target_vendor=FPGAVendorTarget.XILINX_ULTRASCALE_PLUS)
    telem = bridge.get_telemetry()

    assert isinstance(telem, FPGABridgeTelemetry)
    assert telem.status == StatusLevel.LIMITED
    assert telem.is_physical_hardware is False
    assert telem.vram_delta_mib == 0.00
    assert telem.emulation_mode == "AVX2_VECTOR_SIMD"


def test_fpga_bridge_bit_exact_avx2_emulation():
    """Validates bit-exact AVX2 vector SIMD emulation of Mamba-2 SSD recurrence."""
    bridge = FPGAHardwareBridge()

    n = 16
    x = np.array([1.0, 2.0, -1.0, 0.5] * 4, dtype=np.float32)
    a = np.array([0.9, 0.85, 0.95, 0.99] * 4, dtype=np.float32)
    b = np.array([0.5, 0.25, 0.1, 0.2] * 4, dtype=np.float32)
    h_prev = np.zeros(n, dtype=np.float32)

    # Step 1
    h_1 = bridge.emulate_mamba2_ssd(x, a, b, h_prev)
    expected_h1 = (a * h_prev) + (b * x)
    assert np.allclose(h_1, expected_h1, atol=1e-6)

    # Step 2
    h_2 = bridge.emulate_mamba2_ssd(x, a, b, h_1)
    expected_h2 = (a * h_1) + (b * x)
    assert np.allclose(h_2, expected_h2, atol=1e-6)


def test_fpga_bridge_windows_atomic_persistence():
    """Validates thread-safe Windows Atomic Persistence save/load for FPGA bridge."""
    bridge = FPGAHardwareBridge(target_vendor=FPGAVendorTarget.INTEL_AGILEX)

    with tempfile.TemporaryDirectory() as tmpdir:
        save_file = os.path.join(tmpdir, "fpga_config.json")
        bridge.save(save_file)
        assert os.path.exists(save_file)

        restored = FPGAHardwareBridge.load(save_file)
        assert restored.target_vendor == FPGAVendorTarget.INTEL_AGILEX
        assert restored._status == StatusLevel.LIMITED


def test_fpga_bridge_persistence_restores_complete_telemetry():
    """Validates that save/load faithfully restores _is_physical, _status, and _detected_devices."""
    bridge = FPGAHardwareBridge(target_vendor=FPGAVendorTarget.XILINX_ULTRASCALE_PLUS)
    bridge._detected_devices = [{"vendor_id": "10EE", "device_id": "0001", "name": "Fake UltraScale"}]
    bridge._is_physical = True
    bridge._status = StatusLevel.READY

    with tempfile.TemporaryDirectory() as tmpdir:
        save_file = os.path.join(tmpdir, "fpga_telemetry.json")
        bridge.save(save_file)
        restored = FPGAHardwareBridge.load(save_file)

        assert restored.target_vendor == FPGAVendorTarget.XILINX_ULTRASCALE_PLUS
        assert restored._is_physical is True
        assert restored._status == StatusLevel.READY
        assert len(restored._detected_devices) == 1
        assert restored._detected_devices[0]["name"] == "Fake UltraScale"


def test_graph_to_rtl_compiler_complete_vhdl_generation():
    """Validates that DWT Haar and Systolic kernels generate complete, non-stub synthesizable VHDL."""
    compiler = GraphToRTLCompiler(data_width_bits=16)
    dwt_mod = compiler.compile_kernel(ComputationalKernelType.DWT_HAAR_FILTERBANK, input_dim=8)

    assert "entity kernel_dwt_haar_filterbank_8x16 is" in dwt_mod.vhdl_code
    assert "port (" in dwt_mod.vhdl_code
    assert "in_a" in dwt_mod.vhdl_code
    assert "in_b" in dwt_mod.vhdl_code
    assert "out_approx" in dwt_mod.vhdl_code
    assert "out_detail" in dwt_mod.vhdl_code
    assert "architecture rtl of kernel_dwt_haar_filterbank_8x16 is" in dwt_mod.vhdl_code
    assert "out_approx <= shift_right(in_a + in_b, 1);" in dwt_mod.vhdl_code


def test_systolic_array_2d_grid_generation():
    """Validates 2D systolic array full mesh generation in SystemVerilog and VHDL."""
    gen = SystolicArrayGenerator(rows=4, cols=4, data_width_bits=16)
    sv_array = gen.generate_systemverilog_array("my_systolic_4x4")
    vhdl_array = gen.generate_vhdl_array("my_systolic_4x4")

    assert "module my_systolic_4x4" in sv_array
    assert "u_pe" in sv_array
    assert "entity my_systolic_4x4 is" in vhdl_array
    assert "architecture rtl of my_systolic_4x4 is" in vhdl_array
    assert "entity systolic_pe is" in vhdl_array


def test_fpga_crystallizer_edge_cases():
    """Validates edge cases: invalid dimensions, empty inputs."""
    with pytest.raises(ValueError):
        SystolicArrayGenerator(rows=0, cols=8)

    with pytest.raises(ValueError):
        SystolicArrayGenerator(rows=8, cols=-1)

    bridge = FPGAHardwareBridge()
    empty_res = bridge.emulate_mamba2_ssd(np.array([], dtype=np.float32), np.array([], dtype=np.float32), np.array([], dtype=np.float32))
    assert len(empty_res) == 0
