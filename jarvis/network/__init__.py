"""
jarvis/network
==============
Decentralized Mesh Networking, Sovereign Swarm Telepathy, and P2P Consensus Package.
Features:
  - Frontier 23.0: P2P Noise/WireGuard encrypted mesh networking across user endpoints.
  - Zero-Knowledge Federated Consensus aggregating LoRA Rank-4 adapters.
  - Distributed 10,000-bit HD-VSA hypervector majority voting consensus.
"""
from __future__ import annotations

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

__all__ = [
    "HD_CONSENSUS_DIMENSION_BITS",
    "HDVSAConsensusBundle",
    "LoRARank4AdapterDelta",
    "SovereignSwarmMeshManager",
    "SwarmMeshStatus",
    "SwarmNodeIdentity",
    "SwarmNodeRole",
    "SwarmPacket",
    "SwarmPacketType",
    "ZeroKnowledgeFederatedConsensus",
]
