"""
tests/unit/test_swarm_telepathy.py
==================================
Unit test suite for Frontier 23.0 Sovereign Swarm Telepathy & Decentralized P2P Consensus.
Milestone v7.0.0 (Singularity Matrix).
"""
from __future__ import annotations

import hashlib
import numpy as np
import pytest

from jarvis.network.swarm_telepathy import (
    HD_CONSENSUS_DIMENSION_BITS,
    HDVSAConsensusBundle,
    LoRARank4AdapterDelta,
    SovereignSwarmMeshManager,
    SwarmMeshStatus,
    SwarmNodeIdentity,
    SwarmNodeRole,
    SwarmPacket,
    SwarmPacketType,
    ZeroKnowledgeFederatedConsensus,
)


def _make_sample_lora_delta(
    adapter_id: str,
    dim: int = 32,
    rank: int = 4,
    samples: int = 100,
    seed: int = 42,
) -> LoRARank4AdapterDelta:
    """Helper to generate a valid LoRA Rank-4 adapter delta with verified ZK commitment."""
    rng = np.random.RandomState(seed)
    matrix_a = rng.randn(rank, dim).astype(np.float32) * 0.1
    matrix_b = rng.randn(dim, rank).astype(np.float32) * 0.1
    salt = "salt_secure_123"

    raw_buf = (
        matrix_a.tobytes()
        + matrix_b.tobytes()
        + salt.encode()
        + str(samples).encode()
    )
    zk_hash = hashlib.sha256(raw_buf).hexdigest()

    return LoRARank4AdapterDelta(
        adapter_id=adapter_id,
        layer_name="transformer.layers.0.attention.q_proj",
        rank=rank,
        dim=dim,
        alpha=8.0,
        matrix_a=matrix_a,
        matrix_b=matrix_b,
        training_samples=samples,
        blinding_salt=salt,
        zk_commitment_hash=zk_hash,
    )


def test_swarm_mesh_manager_peer_and_packet_crypto() -> None:
    """Verifies peer registration and HMAC-SHA256 authenticated packet encryption/unpacking."""
    mesh = SovereignSwarmMeshManager(local_node_id="node_desktop_primary")
    mesh.initialize()
    assert mesh.status == SwarmMeshStatus.ACTIVE

    peer = SwarmNodeIdentity(
        node_id="node_laptop_secondary",
        public_key_hex="a1b2c3d4e5f60718293a",
        endpoint_uri="wireguard://10.240.0.2:51820",
    )
    assert mesh.register_peer(peer) is True

    # Create encrypted packet
    payload = b"CONVERGE_LORA_STEP_42"
    packet = mesh.create_encrypted_packet(
        recipient_id="node_laptop_secondary",
        packet_type=SwarmPacketType.LORA_DELTA_PROPOSAL,
        payload=payload,
    )
    assert isinstance(packet, SwarmPacket)
    assert packet.sequence_num == 1
    assert len(packet.auth_tag_hex) == 64

    # Verify and unpack
    valid, unpacked = mesh.verify_and_unpack_packet(packet)
    assert valid is True
    assert unpacked == payload

    # Tampered packet must fail closed
    tampered_packet = SwarmPacket(
        packet_id=packet.packet_id,
        packet_type=packet.packet_type,
        sender_id=packet.sender_id,
        recipient_id=packet.recipient_id,
        payload_bytes=b"MALICIOUS_INJECTION",
        sequence_num=packet.sequence_num,
        timestamp_ns=packet.timestamp_ns,
        auth_tag_hex=packet.auth_tag_hex,
    )
    valid_tampered, unpacked_tampered = mesh.verify_and_unpack_packet(tampered_packet)
    assert valid_tampered is False
    assert unpacked_tampered is None


def test_zk_federated_consensus_lora_rank4_aggregation() -> None:
    """Tests zero-knowledge commitment verification and FedAvg convergence over LoRA deltas."""
    consensus = ZeroKnowledgeFederatedConsensus()

    delta1 = _make_sample_lora_delta("adapter_node1", dim=32, samples=150, seed=1)
    delta2 = _make_sample_lora_delta("adapter_node2", dim=32, samples=250, seed=2)

    assert consensus.propose_lora_delta("round_alpha", delta1) is True
    assert consensus.propose_lora_delta("round_alpha", delta2) is True

    # Quorum reached (2 deltas) -> Aggregate
    aggregated = consensus.aggregate_lora_round("round_alpha", min_quorum=2)
    assert aggregated is not None
    assert aggregated.rank == 4
    assert aggregated.dim == 32
    assert aggregated.training_samples == 400
    assert aggregated.verify_commitment() is True
    assert aggregated.compute_frobenius_norm() < 5.0


def test_zk_federated_consensus_rejects_corrupted_commitment() -> None:
    """Verifies that deltas with forged weights fail zero-knowledge proof."""
    consensus = ZeroKnowledgeFederatedConsensus()
    delta = _make_sample_lora_delta("adapter_corrupt", dim=16, samples=50, seed=99)

    # Corrupt weights without updating commitment
    corrupted_delta = LoRARank4AdapterDelta(
        adapter_id=delta.adapter_id,
        layer_name=delta.layer_name,
        rank=delta.rank,
        dim=delta.dim,
        alpha=delta.alpha,
        matrix_a=delta.matrix_a + 5.0,  # Corrupted!
        matrix_b=delta.matrix_b,
        training_samples=delta.training_samples,
        blinding_salt=delta.blinding_salt,
        zk_commitment_hash=delta.zk_commitment_hash,
    )

    accepted = consensus.propose_lora_delta("round_bad", corrupted_delta)
    assert accepted is False


def test_zk_federated_consensus_rejects_exploding_gradient() -> None:
    """Verifies that deltas exceeding Frobenius norm bound are rejected as gradient attacks."""
    consensus = ZeroKnowledgeFederatedConsensus(max_norm=2.0)
    # Huge matrices
    dim = 16
    matrix_a = np.ones((4, dim), dtype=np.float32) * 10.0
    matrix_b = np.ones((dim, 4), dtype=np.float32) * 10.0
    salt = "salt_exploding"
    raw_buf = matrix_a.tobytes() + matrix_b.tobytes() + salt.encode() + str(10).encode()
    zk_hash = hashlib.sha256(raw_buf).hexdigest()

    exploding_delta = LoRARank4AdapterDelta(
        adapter_id="adapter_exploding",
        layer_name="test",
        rank=4,
        dim=dim,
        alpha=8.0,
        matrix_a=matrix_a,
        matrix_b=matrix_b,
        training_samples=10,
        blinding_salt=salt,
        zk_commitment_hash=zk_hash,
    )
    # Frobenius norm is >> 2.0
    accepted = consensus.propose_lora_delta("round_exploding", exploding_delta)
    assert accepted is False


def test_hd_vsa_consensus_majority_voting_bundle() -> None:
    """Tests distributed majority voting bundling across 10,000-bit hypervectors."""
    consensus = ZeroKnowledgeFederatedConsensus()

    # Create 3 bundles of 10,000 bits (1250 bytes)
    # Bit 0: Node 1 has 1, Node 2 has 1, Node 3 has 0 -> Majority = 1
    # Bit 1: Node 1 has 0, Node 2 has 0, Node 3 has 1 -> Majority = 0
    b1_bits = np.zeros(HD_CONSENSUS_DIMENSION_BITS, dtype=np.uint8)
    b2_bits = np.zeros(HD_CONSENSUS_DIMENSION_BITS, dtype=np.uint8)
    b3_bits = np.zeros(HD_CONSENSUS_DIMENSION_BITS, dtype=np.uint8)

    b1_bits[0] = 1
    b2_bits[0] = 1
    b3_bits[0] = 0

    b1_bits[1] = 0
    b2_bits[1] = 0
    b3_bits[1] = 1

    bundle1 = HDVSAConsensusBundle("b1", "n1", "CONCEPT_BROWSER_STATE", np.packbits(b1_bits), 100)
    bundle2 = HDVSAConsensusBundle("b2", "n2", "CONCEPT_BROWSER_STATE", np.packbits(b2_bits), 101)
    bundle3 = HDVSAConsensusBundle("b3", "n3", "CONCEPT_BROWSER_STATE", np.packbits(b3_bits), 102)

    consensus_bundle = consensus.aggregate_hd_vsa_consensus([bundle1, bundle2, bundle3])
    assert consensus_bundle is not None
    unpacked_res = np.unpackbits(consensus_bundle.packed_bits)[:HD_CONSENSUS_DIMENSION_BITS]

    assert unpacked_res[0] == 1
    assert unpacked_res[1] == 0
