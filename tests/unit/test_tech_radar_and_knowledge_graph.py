"""
tests/unit/test_tech_radar_and_knowledge_graph.py
=================================================
Comprehensive unit tests for Milestone 3:
Continuous Learning Memory Graph & Academic Tech Radar Ingestion.
Covers:
  1. DDL creation of knowledge_nodes, knowledge_edges, tech_radar_blips, and indexes.
  2. CRUD operations for knowledge nodes and edges with property JSON serialization.
  3. Foreign key constraints and cascading deletes in SQLite.
  4. ThoughtWorks Tech Radar blip recording, upserting, and filtered querying.
  5. Subgraph BFS graph retrieval (get_knowledge_graph) with depth limits.
  6. ArXiv Atom 1.0 XML feed parsing with sample XML fixture.
  7. ArXiv client rate limiting and fail-closed network error handling.
  8. TechRadarAggregator orchestration: preprints & trending repositories into knowledge graph.
"""
from __future__ import annotations

import sqlite3
import time
import urllib.error
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from jarvis.memory.sqlite_store import SQLiteMemoryStore
from jarvis.web.tech_radar import (
    ArxivIngestionClient,
    ArxivPaper,
    TechRadarAggregator,
)

SAMPLE_ARXIV_ATOM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <link href="http://arxiv.org/api/query?search_query=cat:cs.AI" rel="self" type="application/atom+xml"/>
  <title type="html">ArXiv Query: cat:cs.AI</title>
  <id>http://arxiv.org/api/12345</id>
  <updated>2026-10-18T00:00:00Z</updated>
  <entry>
    <id>http://arxiv.org/abs/2212.04356v1</id>
    <updated>2022-12-08T18:55:00Z</updated>
    <published>2022-12-08T18:55:00Z</published>
    <title>Robust Speech Recognition via Large-Scale Weak Supervision</title>
    <summary>We study the capabilities of speech processing systems trained simply to predict large amounts of transcripts on the internet.</summary>
    <author>
      <name>Alec Radford</name>
    </author>
    <author>
      <name>Jong Wook Kim</name>
    </author>
    <arxiv:primary_category term="eess.AS" scheme="http://arxiv.org/schemas/atom"/>
    <category term="eess.AS" scheme="http://arxiv.org/schemas/atom"/>
    <category term="cs.SD" scheme="http://arxiv.org/schemas/atom"/>
    <category term="cs.AI" scheme="http://arxiv.org/schemas/atom"/>
    <link title="pdf" href="http://arxiv.org/pdf/2212.04356v1" rel="related" type="application/pdf"/>
    <link href="http://arxiv.org/abs/2212.04356v1" rel="alternate" type="text/html"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2401.09876v2</id>
    <updated>2024-01-20T10:00:00Z</updated>
    <published>2024-01-18T12:00:00Z</published>
    <title>Fast On-Device Semantic Router for Autonomous AI Assistants</title>
    <summary>A sub-2ms embedding-based slot filling and intent classifier designed for local edge deployment.</summary>
    <author>
      <name>Alice Smith</name>
    </author>
    <arxiv:primary_category term="cs.AI" scheme="http://arxiv.org/schemas/atom"/>
    <category term="cs.AI" scheme="http://arxiv.org/schemas/atom"/>
    <category term="cs.CL" scheme="http://arxiv.org/schemas/atom"/>
    <link title="pdf" href="http://arxiv.org/pdf/2401.09876v2" rel="related" type="application/pdf"/>
  </entry>
</feed>
"""


# ============================================================================
# 1. DDL & Schema Creation Tests
# ============================================================================

def test_knowledge_tables_and_indexes_ddl(tmp_path: Path):
    """
    Verifies that knowledge_nodes, knowledge_edges, and tech_radar_blips tables
    and their indexes are properly created in SQLite.
    """
    db_file = tmp_path / "test_knowledge_ddl.db"
    store = SQLiteMemoryStore(db_path=db_file)

    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()

    # Verify tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {row[0] for row in cursor.fetchall()}
    assert "knowledge_nodes" in tables
    assert "knowledge_edges" in tables
    assert "tech_radar_blips" in tables

    # Verify indexes
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index';")
    indexes = {row[0] for row in cursor.fetchall()}
    assert "idx_knowledge_nodes_type" in indexes
    assert "idx_knowledge_edges_pair" in indexes
    assert "idx_tech_radar_quadrant_ring" in indexes

    conn.close()
    store.close()


# ============================================================================
# 2. Knowledge Graph Node & Edge CRUD Tests
# ============================================================================

def test_node_and_edge_crud(tmp_path: Path):
    """
    Tests adding knowledge nodes, upserting existing nodes, and creating directed edges.
    """
    db_file = tmp_path / "test_nodes.db"
    store = SQLiteMemoryStore(db_path=db_file)

    # 1. Add nodes
    store.add_knowledge_node(
        node_id="paper:whisper",
        label="Whisper Speech Model",
        node_type="paper",
        properties={"authors": ["Alec Radford"], "year": 2022},
    )
    store.add_knowledge_node(
        node_id="module:audio_engine",
        label="JARVIS Audio Engine",
        node_type="module",
        properties={"path": "jarvis/audio/engine.py"},
    )

    # Verify nodes inserted
    graph = store.get_knowledge_graph()
    assert len(graph["nodes"]) == 2
    whisper_node = next(n for n in graph["nodes"] if n["node_id"] == "paper:whisper")
    assert whisper_node["label"] == "Whisper Speech Model"
    assert whisper_node["node_type"] == "paper"
    assert whisper_node["properties"]["year"] == 2022

    # 2. Update existing node (UPSERT)
    store.add_knowledge_node(
        node_id="paper:whisper",
        label="Whisper Speech Model v2",
        node_type="paper",
        properties={"authors": ["Alec Radford"], "year": 2023, "version": "v2"},
    )
    graph_after_update = store.get_knowledge_graph()
    assert len(graph_after_update["nodes"]) == 2
    whisper_updated = next(n for n in graph_after_update["nodes"] if n["node_id"] == "paper:whisper")
    assert whisper_updated["label"] == "Whisper Speech Model v2"
    assert whisper_updated["properties"]["version"] == "v2"

    # 3. Add edge
    store.add_knowledge_edge(
        source_id="paper:whisper",
        target_id="module:audio_engine",
        relation="implemented_by",
        weight=0.95,
        properties={"latency_target_ms": 150},
    )

    graph_with_edge = store.get_knowledge_graph()
    assert len(graph_with_edge["edges"]) == 1
    edge = graph_with_edge["edges"][0]
    assert edge["source_id"] == "paper:whisper"
    assert edge["target_id"] == "module:audio_engine"
    assert edge["relation"] == "implemented_by"
    assert edge["weight"] == 0.95
    assert edge["properties"]["latency_target_ms"] == 150

    store.close()


def test_empty_node_id_validation(tmp_path: Path):
    """Verifies that invalid or empty node_id raises ValueError."""
    db_file = tmp_path / "test_val.db"
    store = SQLiteMemoryStore(db_path=db_file)

    with pytest.raises(ValueError):
        store.add_knowledge_node(node_id="", label="Test", node_type="test")

    with pytest.raises(ValueError):
        store.add_knowledge_edge(source_id="", target_id="target", relation="rel")

    store.close()


# ============================================================================
# 3. Foreign Key Constraints & Cascading Deletes Tests
# ============================================================================

def test_foreign_key_enforcement_and_cascading_deletes(tmp_path: Path):
    """
    Verifies that foreign keys are enforced (cannot add edge for non-existent node)
    and that deleting a node automatically cascades and deletes incident edges.
    """
    db_file = tmp_path / "test_cascade.db"
    store = SQLiteMemoryStore(db_path=db_file)

    # 1. Foreign key integrity check: adding edge with non-existent nodes must fail
    with pytest.raises(sqlite3.IntegrityError):
        store.add_knowledge_edge(
            source_id="nonexistent_src",
            target_id="nonexistent_tgt",
            relation="test_relation",
        )

    # 2. Setup 3 nodes and 2 edges: A -> B -> C
    store.add_knowledge_node(node_id="node:A", label="Node A", node_type="test")
    store.add_knowledge_node(node_id="node:B", label="Node B", node_type="test")
    store.add_knowledge_node(node_id="node:C", label="Node C", node_type="test")

    store.add_knowledge_edge(source_id="node:A", target_id="node:B", relation="to_b")
    store.add_knowledge_edge(source_id="node:B", target_id="node:C", relation="to_c")

    graph = store.get_knowledge_graph()
    assert len(graph["nodes"]) == 3
    assert len(graph["edges"]) == 2

    # 3. Delete node:B -> should CASCADE delete both edges (A->B and B->C)
    deleted = store.delete_knowledge_node("node:B")
    assert deleted is True

    graph_after = store.get_knowledge_graph()
    remaining_node_ids = {n["node_id"] for n in graph_after["nodes"]}
    assert remaining_node_ids == {"node:A", "node:C"}
    # Both edges touching node:B must be cascaded away
    assert len(graph_after["edges"]) == 0

    store.close()


# ============================================================================
# 4. Tech Radar Blip Recording & Querying Tests
# ============================================================================

def test_tech_radar_blip_crud_and_queries(tmp_path: Path):
    """
    Verifies recording blips, updating blips, and querying with quadrant and ring filters.
    """
    db_file = tmp_path / "test_radar.db"
    store = SQLiteMemoryStore(db_path=db_file)

    # Insert blips across various quadrants and rings
    store.record_tech_radar_blip(
        blip_id="blip:whisper",
        title="Streaming Whisper STT",
        ring="adopt",
        quadrant="techniques",
        summary="Low-latency streaming ASR model",
        url="https://arxiv.org/abs/2212.04356",
        source="arxiv",
        published="2022-12-08",
        tags=["speech", "stt", "whisper"],
    )
    store.record_tech_radar_blip(
        blip_id="blip:sqlite_wal",
        title="SQLite WAL Persistence",
        ring="adopt",
        quadrant="platforms",
        summary="High concurrency local storage",
        url="https://sqlite.org/wal.html",
        source="sqlite",
        tags=["database", "storage"],
    )
    store.record_tech_radar_blip(
        blip_id="blip:semantic_router",
        title="Semantic Router",
        ring="trial",
        quadrant="techniques",
        summary="Sub-2ms on-device intent routing",
        url="https://github.com/vrsen/semantic-router",
        source="github",
        tags=["nlp", "routing"],
    )
    store.record_tech_radar_blip(
        blip_id="blip:legacy_vosk",
        title="Legacy Vosk Model",
        ring="hold",
        quadrant="tools",
        summary="Heavyweight offline Kaldi model",
        url="https://alphacephei.com/vosk/",
        source="web",
        tags=["legacy", "stt"],
    )

    # 1. Query all blips
    all_blips = store.query_tech_radar()
    assert len(all_blips) == 4

    # 2. Filter by quadrant
    tech_blips = store.query_tech_radar(quadrant="techniques")
    assert len(tech_blips) == 2
    assert {b["blip_id"] for b in tech_blips} == {"blip:whisper", "blip:semantic_router"}

    # 3. Filter by ring
    adopt_blips = store.query_tech_radar(ring="adopt")
    assert len(adopt_blips) == 2
    assert {b["blip_id"] for b in adopt_blips} == {"blip:whisper", "blip:sqlite_wal"}

    # 4. Filter by both quadrant and ring
    specific_blips = store.query_tech_radar(quadrant="techniques", ring="trial")
    assert len(specific_blips) == 1
    assert specific_blips[0]["blip_id"] == "blip:semantic_router"
    assert "nlp" in specific_blips[0]["tags"]

    # 5. Upsert blip (change ring to 'adopt')
    store.record_tech_radar_blip(
        blip_id="blip:semantic_router",
        title="Semantic Router",
        ring="adopt",
        quadrant="techniques",
        summary="Promoted to ADOPT after sub-2ms verification",
        url="https://github.com/vrsen/semantic-router",
        tags=["nlp", "routing", "promoted"],
    )
    updated_trial = store.query_tech_radar(quadrant="techniques", ring="trial")
    assert len(updated_trial) == 0

    updated_adopt = store.query_tech_radar(quadrant="techniques", ring="adopt")
    assert len(updated_adopt) == 2
    promoted = next(b for b in updated_adopt if b["blip_id"] == "blip:semantic_router")
    assert promoted["summary"] == "Promoted to ADOPT after sub-2ms verification"
    assert "promoted" in promoted["tags"]

    store.close()


# ============================================================================
# 5. Subgraph BFS Traversal Tests
# ============================================================================

def test_get_knowledge_graph_full_and_subgraph_bfs(tmp_path: Path):
    """
    Verifies that get_knowledge_graph correctly performs depth-bounded BFS
    traversals from a root node.
    """
    db_file = tmp_path / "test_bfs.db"
    store = SQLiteMemoryStore(db_path=db_file)

    # Graph structure:
    # N1 -> N2 -> N3 -> N4
    # N5 (isolated)
    for i in range(1, 6):
        store.add_knowledge_node(node_id=f"N{i}", label=f"Node {i}", node_type="test")

    store.add_knowledge_edge(source_id="N1", target_id="N2", relation="next")
    store.add_knowledge_edge(source_id="N2", target_id="N3", relation="next")
    store.add_knowledge_edge(source_id="N3", target_id="N4", relation="next")

    # Depth 1 from N1: should return N1, N2 and edge N1->N2
    subgraph_d1 = store.get_knowledge_graph(node_id="N1", depth=1)
    d1_node_ids = {n["node_id"] for n in subgraph_d1["nodes"]}
    assert d1_node_ids == {"N1", "N2"}
    assert len(subgraph_d1["edges"]) == 1

    # Depth 2 from N1: should return N1, N2, N3
    subgraph_d2 = store.get_knowledge_graph(node_id="N1", depth=2)
    d2_node_ids = {n["node_id"] for n in subgraph_d2["nodes"]}
    assert d2_node_ids == {"N1", "N2", "N3"}
    assert len(subgraph_d2["edges"]) == 2

    # Isolated node N5: returns only N5 and 0 edges
    subgraph_n5 = store.get_knowledge_graph(node_id="N5", depth=2)
    assert len(subgraph_n5["nodes"]) == 1
    assert subgraph_n5["nodes"][0]["node_id"] == "N5"
    assert len(subgraph_n5["edges"]) == 0

    store.close()


# ============================================================================
# 6. ArXiv Atom Ingestion Client Tests
# ============================================================================

def test_arxiv_atom_feed_parsing():
    """
    Verifies that ArxivIngestionClient accurately parses paper IDs, titles,
    authors, summaries, categories, published timestamps, and PDF links from Atom 1.0 XML.
    """
    client = ArxivIngestionClient(rate_limit_seconds=0.0)
    papers = client.parse_atom_feed(SAMPLE_ARXIV_ATOM_XML)

    assert len(papers) == 2

    # Paper 1
    p1 = papers[0]
    assert p1.paper_id == "2212.04356v1"
    assert p1.title == "Robust Speech Recognition via Large-Scale Weak Supervision"
    assert p1.authors == ["Alec Radford", "Jong Wook Kim"]
    assert "internet" in p1.summary
    assert p1.categories[0] == "eess.AS"  # Primary category placed first
    assert "cs.AI" in p1.categories
    assert p1.published == "2022-12-08T18:55:00Z"
    assert p1.pdf_url == "http://arxiv.org/pdf/2212.04356v1"

    # Paper 2
    p2 = papers[1]
    assert p2.paper_id == "2401.09876v2"
    assert p2.title == "Fast On-Device Semantic Router for Autonomous AI Assistants"
    assert p2.authors == ["Alice Smith"]
    assert "sub-2ms" in p2.summary
    assert p2.pdf_url == "http://arxiv.org/pdf/2401.09876v2"


def test_arxiv_client_rate_limiting():
    """
    Verifies that ArxivIngestionClient enforces the required rate limiting delay.
    """
    client = ArxivIngestionClient(rate_limit_seconds=0.15)
    t0 = time.time()
    client._apply_rate_limit()
    client._apply_rate_limit()
    elapsed = time.time() - t0

    assert elapsed >= 0.14, f"Rate limiting failed: took {elapsed:.3f}s, expected >= 0.14s"


def test_arxiv_client_fail_closed_on_network_error(monkeypatch):
    """
    Verifies that network errors (URLError) fail closed and return empty list
    without raising unhandled exceptions.
    """
    client = ArxivIngestionClient(rate_limit_seconds=0.0, timeout_seconds=1.0)

    def mock_urlopen(*args, **kwargs):
        raise urllib.error.URLError("Simulated connection timeout")

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    results = client.search(query="cat:cs.AI")
    assert results == []


# ============================================================================
# 7. TechRadarAggregator Multi-Source Integration Tests
# ============================================================================

def test_tech_radar_aggregator_arxiv_ingestion(tmp_path: Path, monkeypatch):
    """
    Tests that TechRadarAggregator fetches papers from ArXiv and populates
    both Tech Radar blips and the knowledge graph (nodes + edges).
    """
    db_file = tmp_path / "test_agg_arxiv.db"
    store = SQLiteMemoryStore(db_path=db_file)

    client = ArxivIngestionClient(rate_limit_seconds=0.0)
    # Mock parse_atom_feed output via search
    sample_papers = client.parse_atom_feed(SAMPLE_ARXIV_ATOM_XML)

    monkeypatch.setattr(client, "search", lambda query, max_results=5: sample_papers)

    aggregator = TechRadarAggregator(memory_store=store, arxiv_client=client)
    ingested = aggregator.ingest_arxiv_papers(query="cat:cs.AI", max_results=2)

    assert len(ingested) == 2

    # Check blips recorded
    blips = store.query_tech_radar()
    assert len(blips) == 2
    blip_ids = {b["blip_id"] for b in blips}
    assert "arxiv:2212.04356v1" in blip_ids
    assert "arxiv:2401.09876v2" in blip_ids

    # Check knowledge graph
    graph = store.get_knowledge_graph()
    node_types = {n["node_type"] for n in graph["nodes"]}
    assert "paper" in node_types
    assert "category" in node_types
    assert "author" in node_types
    assert "domain" in node_types  # Whisper correlates with voice_pipeline!

    # Check relationships
    relations = {e["relation"] for e in graph["edges"]}
    assert "categorized_under" in relations
    assert "authored_by" in relations
    assert "enhances_domain" in relations

    # Test BFS from Whisper paper node
    whisper_subgraph = store.get_knowledge_graph(node_id="arxiv:2212.04356v1", depth=1)
    connected_labels = {n["label"] for n in whisper_subgraph["nodes"]}
    assert "Alec Radford" in connected_labels
    assert "Voice & Acoustic Pipeline" in connected_labels

    store.close()


def test_tech_radar_aggregator_github_trending(tmp_path: Path):
    """
    Verifies that GitHub Trending repositories are properly ingested
    as tools in Tech Radar and linked in the knowledge graph.
    """
    db_file = tmp_path / "test_agg_github.db"
    store = SQLiteMemoryStore(db_path=db_file)
    aggregator = TechRadarAggregator(memory_store=store)

    sample_repos = [
        {
            "name": "openai/whisper",
            "title": "Robust Speech Recognition via Large-Scale Weak Supervision",
            "description": "General-purpose speech recognition model",
            "url": "https://github.com/openai/whisper",
            "quadrant": "tools",
            "ring": "adopt",
            "tags": ["audio", "speech", "python"],
        },
        {
            "name": "vrsen/semantic-router",
            "title": "Semantic Router",
            "description": "Superfast decision-making layer for LLMs",
            "url": "https://github.com/vrsen/semantic-router",
            "quadrant": "tools",
            "ring": "trial",
            "tags": ["router", "embeddings"],
        },
    ]

    ingested = aggregator.ingest_github_trending(repositories=sample_repos)
    assert len(ingested) == 2

    # Verify blips
    blips = store.query_tech_radar(quadrant="tools")
    assert len(blips) == 2

    # Verify knowledge nodes
    graph = store.get_knowledge_graph()
    repo_nodes = [n for n in graph["nodes"] if n["node_type"] == "repository"]
    assert len(repo_nodes) == 2

    store.close()


def test_tech_radar_aggregator_sync_all(tmp_path: Path, monkeypatch):
    """
    Tests high-level sync_all method combining ArXiv and GitHub trending repositories.
    """
    db_file = tmp_path / "test_sync_all.db"
    store = SQLiteMemoryStore(db_path=db_file)

    client = ArxivIngestionClient(rate_limit_seconds=0.0)
    sample_papers = client.parse_atom_feed(SAMPLE_ARXIV_ATOM_XML)[:1]
    monkeypatch.setattr(client, "search", lambda query, max_results=3: sample_papers)

    aggregator = TechRadarAggregator(memory_store=store, arxiv_client=client)

    trending = [
        {
            "name": "ggerganov/whisper.cpp",
            "title": "whisper.cpp",
            "description": "Port of OpenAI Whisper in C/C++",
            "url": "https://github.com/ggerganov/whisper.cpp",
        }
    ]

    stats = aggregator.sync_all(queries=["cat:cs.AI"], trending_repos=trending)
    assert stats["papers_ingested"] == 1
    assert stats["repos_ingested"] == 1
    assert stats["total_radar_blips"] == 2

    store.close()
