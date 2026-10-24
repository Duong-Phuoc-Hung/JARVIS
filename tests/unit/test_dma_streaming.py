"""
tests/unit/test_dma_streaming.py
=================================
Unit tests for Frontier 14.0 Zero-Copy Kernel DMA & Resizable BAR Texture Streaming.
Sprint 26 / Milestone v6.4.0.
"""
from __future__ import annotations

import numpy as np
import pytest

from jarvis.vision.dma_streaming import (
    DMABufferFormat,
    DMAPerformanceMetrics,
    DMAPinnedSlot,
    DMAStreamingBackend,
    DMAStreamingStatus,
    ResizableBARRingBuffer,
    ZeroCopyDMAManager,
)


def test_dma_pinned_ring_buffer_allocation() -> None:
    """Verifies that the 3-slot ring buffer pre-allocates contiguous pinned memory slots."""
    ring = ResizableBARRingBuffer(
        width=1920,
        height=1080,
        buffer_format=DMABufferFormat.BGRA8_UNORM,
        num_slots=3,
    )
    assert ring.num_slots == 3
    assert ring.stride_bytes == 1920 * 4
    assert ring.slot_byte_size == 1920 * 1080 * 4

    slot0 = ring.acquire_write_slot()
    assert isinstance(slot0, DMAPinnedSlot)
    assert slot0.slot_id == 0
    assert slot0.buffer.nbytes == ring.slot_byte_size
    assert slot0.is_locked is True

    ring.commit_write_slot(slot0, latency_ms=0.045)
    assert slot0.is_locked is False
    assert slot0.frame_id == 1
    assert slot0.ingest_latency_ms == 0.045

    latest = ring.acquire_latest_read_slot()
    assert latest is not None
    assert latest.slot_id == 0
    assert latest.frame_id == 1


def test_dma_ring_buffer_cycling() -> None:
    """Ensures triple-buffering cycles through slots without memory leaks."""
    ring = ResizableBARRingBuffer(width=640, height=480, num_slots=3)
    slots_acquired = []
    for _ in range(6):
        s = ring.acquire_write_slot()
        slots_acquired.append(s.slot_id)
        ring.commit_write_slot(s, 0.02)

    assert slots_acquired == [0, 1, 2, 0, 1, 2]
    latest = ring.acquire_latest_read_slot()
    assert latest is not None
    assert latest.frame_id == 6
    assert latest.slot_id == 2


def test_zero_copy_dma_manager_lifecycle() -> None:
    """Tests DMA Manager initialization, hardware probing, and direct ingestion."""
    manager = ZeroCopyDMAManager(width=1920, height=1080)
    caps = manager.probe_hardware_capabilities()
    assert "os_name" in caps
    assert "pinned_host_supported" in caps

    success = manager.initialize_session()
    assert success is True
    assert manager.status == DMAStreamingStatus.ACTIVE
    assert manager.backend in (
        DMAStreamingBackend.RESIZABLE_BAR_DX12,
        DMAStreamingBackend.DXGI_DUPLICATION_NT_HANDLE,
        DMAStreamingBackend.VULKAN_EXTERNAL_MEMORY,
        DMAStreamingBackend.PINNED_HOST_MAPPED,
    )

    # Ingest synthetic 1080p frame
    raw_frame = np.full((1080, 1920, 4), fill_value=128, dtype=np.uint8)
    slot = manager.ingest_frame_direct_dma(raw_frame)

    assert slot is not None
    assert slot.frame_id == 1
    assert slot.ingest_latency_ms >= 0.0
    assert manager.metrics.total_frames_ingested == 1
    assert manager.metrics.vram_delta_mib == 0.00

    latest = manager.get_latest_frame()
    assert latest is not None
    assert latest.frame_id == 1

    snapshot = manager.get_performance_snapshot()
    assert snapshot["status"] == "ACTIVE"
    assert snapshot["vram_delta_mib"] == 0.00
    assert snapshot["total_frames_ingested"] == 1


def test_zero_copy_dma_uninitialized_error() -> None:
    """Ensures fail-closed exception when ingesting without initialization."""
    manager = ZeroCopyDMAManager()
    with pytest.raises(RuntimeError, match="not active or uninitialized"):
        manager.ingest_frame_direct_dma(b"some_bytes")


def test_zero_copy_dma_empty_frame_validation() -> None:
    """Ensures fail-closed ValueError on empty or None input frame buffers."""
    manager = ZeroCopyDMAManager()
    manager.initialize_session()

    with pytest.raises(ValueError, match="cannot be None"):
        manager.ingest_frame_direct_dma(None)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="cannot be empty"):
        manager.ingest_frame_direct_dma(np.array([], dtype=np.uint8))

    with pytest.raises(ValueError, match="cannot be empty"):
        manager.ingest_frame_direct_dma(b"")


def test_zero_copy_dma_limited_fallback() -> None:
    """Verifies that requesting an unavailable backend honestly reports LIMITED per AGENTS.md Rule 2."""
    manager = ZeroCopyDMAManager(preferred_backend=DMAStreamingBackend.RESIZABLE_BAR_DX12)
    # Mock probe to simulate system lacking DirectX 12 Resizable BAR
    manager.probe_hardware_capabilities = lambda: {  # type: ignore[method-assign]
        "is_windows": True,
        "resizable_bar_supported": False,
        "pinned_host_supported": True,
    }
    success = manager.initialize_session()
    assert success is True
    assert manager.status == DMAStreamingStatus.LIMITED
    assert manager.backend == DMAStreamingBackend.PINNED_HOST_MAPPED

    # Still ingests properly under LIMITED fallback
    frame = np.full((1080, 1920, 4), 100, dtype=np.uint8)
    slot = manager.ingest_frame_direct_dma(frame)
    assert slot.frame_id == 1


def test_zero_copy_dma_autonegotiate_best_backend() -> None:
    """Ensures that default initialization auto-selects highest available backend."""
    manager = ZeroCopyDMAManager(preferred_backend=None)
    manager.initialize_session()
    # On Windows with DX12, should automatically select RESIZABLE_BAR_DX12
    caps = manager.probe_hardware_capabilities()
    if caps.get("resizable_bar_supported"):
        assert manager.backend == DMAStreamingBackend.RESIZABLE_BAR_DX12
        assert manager.status == DMAStreamingStatus.ACTIVE

