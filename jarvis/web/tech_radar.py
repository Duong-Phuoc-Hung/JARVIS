"""
jarvis/web/tech_radar.py
========================
Continuous Learning Academic Ingestion Client & ThoughtWorks Tech Radar Aggregator.
Implements:
  - Zero-dependency ArXiv Atom 1.0 Client (`ArxivIngestionClient`) using standard library
    `urllib.request` and `xml.etree.ElementTree` with strict rate limiting (1 request per 3 seconds).
  - Multi-source Tech Radar Aggregator (`TechRadarAggregator`) synchronizing preprints,
    scientific literature, and GitHub open-source repositories into `SQLiteMemoryStore`
    as both Tech Radar blips and interconnected knowledge graph nodes and edges.
"""
from __future__ import annotations

import html
import logging
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, List, Optional

from jarvis.memory.sqlite_store import SQLiteMemoryStore

logger = logging.getLogger("jarvis.web.tech_radar")

ATOM_XMLNS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


@dataclass(frozen=True)
class ArxivPaper:
    """
    Structured representation of a scientific paper parsed from ArXiv Atom 1.0 feed.
    """
    paper_id: str
    title: str
    authors: list[str]
    summary: str
    categories: list[str]
    published: str
    pdf_url: str
    entry_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serializes paper metadata to a dictionary."""
        return {
            "paper_id": self.paper_id,
            "title": self.title,
            "authors": list(self.authors),
            "summary": self.summary,
            "categories": list(self.categories),
            "published": self.published,
            "pdf_url": self.pdf_url,
            "entry_id": self.entry_id,
        }


class ArxivIngestionClient:
    """
    Zero-external-dependency ArXiv Atom 1.0 API ingestion client.
    Enforces official rate limiting (1 request per 3 seconds) and safe fail-closed error handling.
    """
    DEFAULT_CATEGORIES: list[str] = ["cs.AI", "cs.CL", "cs.SD", "eess.AS", "cs.HC", "cs.CV", "cs.LG"]

    def __init__(
        self,
        base_url: str = "http://export.arxiv.org/api/query",
        rate_limit_seconds: float = 3.0,
        timeout_seconds: float = 12.0,
        user_agent: str = "JARVIS-Sovereign-Research/2.0 (Zero-Dependency Academic Ingestion)",
        rate_limit_interval_s: float | None = None,
    ) -> None:
        self.base_url = base_url
        if rate_limit_interval_s is not None:
            self.rate_limit_seconds = max(0.0, float(rate_limit_interval_s))
        else:
            self.rate_limit_seconds = max(0.0, float(rate_limit_seconds))
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.user_agent = user_agent
        self._last_request_time: float = 0.0
        self._lock = threading.Lock()

    def _apply_rate_limit(self) -> None:
        """
        Enforces rate limiting delay between consecutive ArXiv queries to avoid 429/IP blocks.
        """
        with self._lock:
            now = time.time()
            elapsed = now - self._last_request_time
            if elapsed < self.rate_limit_seconds:
                sleep_duration = self.rate_limit_seconds - elapsed
                logger.debug("ArXiv client throttling for %.2f seconds", sleep_duration)
                time.sleep(sleep_duration)
            self._last_request_time = time.time()

    def parse_atom_xml(self, xml_content: str) -> list[dict[str, Any]]:
        """
        Parses raw XML string from ArXiv Atom 1.0 response into list of paper dicts.
        Raises ET.ParseError if XML syntax is invalid.
        """
        if not xml_content or not xml_content.strip():
            return []
        cleaned_xml = xml_content.strip()
        cleaned_xml = re.sub(r"^[^<]+", "", cleaned_xml)
        root = ET.fromstring(cleaned_xml)

        entries = root.findall("atom:entry", namespaces=ATOM_XMLNS)
        if not entries:
            entries = root.findall("entry")

        papers: list[dict[str, Any]] = []
        for entry in entries:
            entry_id = (
                entry.findtext("atom:id", default="", namespaces=ATOM_XMLNS)
                or entry.findtext("id")
                or ""
            ).strip()

            raw_title = (
                entry.findtext("atom:title", default="", namespaces=ATOM_XMLNS)
                or entry.findtext("title")
                or ""
            )
            title = re.sub(r"\s+", " ", html.unescape(raw_title)).strip()

            author_nodes = entry.findall("atom:author", namespaces=ATOM_XMLNS) or entry.findall("author")
            authors: list[str] = []
            for a_node in author_nodes:
                name = (
                    a_node.findtext("atom:name", default="", namespaces=ATOM_XMLNS)
                    or a_node.findtext("name")
                    or ""
                ).strip()
                if name:
                    authors.append(re.sub(r"\s+", " ", html.unescape(name)))

            raw_summary = (
                entry.findtext("atom:summary", default="", namespaces=ATOM_XMLNS)
                or entry.findtext("summary")
                or ""
            )
            summary = re.sub(r"\s+", " ", html.unescape(raw_summary)).strip()

            category_nodes = entry.findall("atom:category", namespaces=ATOM_XMLNS) or entry.findall("category")
            category = ""
            if category_nodes:
                category = category_nodes[0].attrib.get("term", "").strip()

            pdf_url = ""
            link_nodes = entry.findall("atom:link", namespaces=ATOM_XMLNS) or entry.findall("link")
            for l_node in link_nodes:
                title_attr = l_node.attrib.get("title", "").lower()
                type_attr = l_node.attrib.get("type", "").lower()
                href = l_node.attrib.get("href", "").strip()
                if title_attr == "pdf" or type_attr == "application/pdf":
                    pdf_url = href
                    break
            if not pdf_url and entry_id:
                pdf_url = entry_id.replace("abs", "pdf") + ".pdf"

            papers.append({
                "id": entry_id,
                "title": title,
                "authors": authors,
                "summary": summary,
                "category": category,
                "pdf_url": pdf_url,
            })
        return papers

    def fetch_latest_papers(
        self,
        query: str = "",
        categories: list[str] | None = None,
        max_results: int = 10,
        http_getter: Any | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetches latest papers from ArXiv API with rate limiting and max_results clamping [1, 100].
        """
        self._apply_rate_limit()
        clamped_max = max(1, min(100, int(max_results)))
        cats = categories or self.DEFAULT_CATEGORIES
        cat_query = " OR ".join(f"cat:{c}" for c in cats)
        search_q = f"({query}) AND ({cat_query})" if query else cat_query
        params = {
            "search_query": search_q,
            "max_results": clamped_max,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        url = f"{self.base_url}?{urllib.parse.urlencode(params)}"
        if http_getter is not None:
            xml_data = http_getter(url)
        else:
            req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                xml_data = resp.read().decode("utf-8", errors="replace")

        return self.parse_atom_xml(xml_data)

    def parse_atom_feed(self, xml_content: str) -> List[ArxivPaper]:
        """
        Parses raw XML string from ArXiv Atom 1.0 response into a list of ArxivPaper instances.
        Gracefully handles XML namespaces, CDATA blocks, and missing metadata attributes.
        """
        if not xml_content or not xml_content.strip():
            logger.warning("Empty XML content received for ArXiv feed parsing")
            return []

        cleaned_xml = xml_content.strip()
        # Clean any leading bytes or comments before the XML declaration
        cleaned_xml = re.sub(r"^[^<]+", "", cleaned_xml)

        try:
            root = ET.fromstring(cleaned_xml)
        except Exception as exc:
            logger.error("Failed to parse ArXiv Atom XML: %s", exc)
            return []

        # Find entry nodes with or without namespace
        entries = root.findall("atom:entry", namespaces=ATOM_XMLNS)
        if not entries:
            entries = root.findall("entry")

        papers: list[ArxivPaper] = []
        for entry in entries:
            # 1. Entry ID & Paper ID
            entry_id = (
                entry.findtext("atom:id", default="", namespaces=ATOM_XMLNS)
                or entry.findtext("id")
                or ""
            ).strip()

            # Extract clean paper_id (e.g. '2212.04356v1' or '2212.04356')
            paper_id_match = re.search(r"abs/([0-9]+\.[0-9]+(?:v[0-9]+)?)", entry_id)
            if paper_id_match:
                paper_id = paper_id_match.group(1)
            else:
                paper_id = entry_id.rsplit("/", 1)[-1] if "/" in entry_id else entry_id

            # 2. Title (clean multiline whitespace and HTML entities)
            raw_title = (
                entry.findtext("atom:title", default="", namespaces=ATOM_XMLNS)
                or entry.findtext("title")
                or ""
            )
            title = re.sub(r"\s+", " ", html.unescape(raw_title)).strip()

            # 3. Authors
            author_nodes = entry.findall("atom:author", namespaces=ATOM_XMLNS) or entry.findall("author")
            authors: list[str] = []
            for a_node in author_nodes:
                name = (
                    a_node.findtext("atom:name", default="", namespaces=ATOM_XMLNS)
                    or a_node.findtext("name")
                    or ""
                ).strip()
                if name:
                    authors.append(re.sub(r"\s+", " ", html.unescape(name)))

            # 4. Summary / Abstract
            raw_summary = (
                entry.findtext("atom:summary", default="", namespaces=ATOM_XMLNS)
                or entry.findtext("summary")
                or ""
            )
            summary = re.sub(r"\s+", " ", html.unescape(raw_summary)).strip()

            # 5. Categories
            category_nodes = entry.findall("atom:category", namespaces=ATOM_XMLNS) or entry.findall("category")
            categories: list[str] = []
            for c_node in category_nodes:
                term = c_node.attrib.get("term", "").strip()
                if term and term not in categories:
                    categories.append(term)

            # Check primary category
            primary_node = entry.find("arxiv:primary_category", namespaces=ATOM_XMLNS)
            if primary_node is not None:
                prim_term = primary_node.attrib.get("term", "").strip()
                if prim_term and prim_term in categories:
                    # Move primary to front
                    categories.remove(prim_term)
                    categories.insert(0, prim_term)
                elif prim_term:
                    categories.insert(0, prim_term)

            # 6. Published Timestamp
            published = (
                entry.findtext("atom:published", default="", namespaces=ATOM_XMLNS)
                or entry.findtext("published")
                or ""
            ).strip()

            # 7. PDF Link
            pdf_url = ""
            link_nodes = entry.findall("atom:link", namespaces=ATOM_XMLNS) or entry.findall("link")
            for l_node in link_nodes:
                rel = l_node.attrib.get("rel", "")
                title_attr = l_node.attrib.get("title", "").lower()
                type_attr = l_node.attrib.get("type", "").lower()
                href = l_node.attrib.get("href", "").strip()
                if title_attr == "pdf" or type_attr == "application/pdf":
                    pdf_url = href
                    break
            if not pdf_url and paper_id:
                pdf_url = f"https://arxiv.org/pdf/{paper_id}.pdf"

            if title and paper_id:
                papers.append(ArxivPaper(
                    paper_id=paper_id,
                    title=title,
                    authors=authors,
                    summary=summary,
                    categories=categories,
                    published=published,
                    pdf_url=pdf_url,
                    entry_id=entry_id,
                ))

        return papers

    def search(
        self,
        query: str,
        max_results: int = 10,
        start: int = 0,
        sort_by: str = "relevance",
        sort_order: str = "descending",
    ) -> List[ArxivPaper]:
        """
        Executes a live query to the ArXiv Atom 1.0 endpoint.
        Returns parsed list of papers. In case of network errors or timeouts, fails closed with [].
        """
        clean_query = str(query).strip()
        if not clean_query:
            logger.warning("Empty search query provided to ArXiv client")
            return []

        self._apply_rate_limit()

        params = {
            "search_query": clean_query,
            "start": max(0, int(start)),
            "max_results": max(1, int(max_results)),
            "sortBy": sort_by,
            "sortOrder": sort_order,
        }
        encoded_url = f"{self.base_url}?{urllib.parse.urlencode(params)}"
        logger.info("Executing ArXiv query: %s", encoded_url)

        req = urllib.request.Request(
            encoded_url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/atom+xml, application/xml, text/xml",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                payload = response.read().decode("utf-8", errors="replace")
                return self.parse_atom_feed(payload)
        except urllib.error.HTTPError as http_err:
            logger.error("ArXiv HTTP error %d: %s", http_err.code, http_err.reason)
            return []
        except urllib.error.URLError as url_err:
            logger.warning("ArXiv network connection failed (fail-closed): %s", url_err.reason)
            return []
        except TimeoutError:
            logger.warning("ArXiv request timed out after %.1f seconds", self.timeout_seconds)
            return []
        except Exception as exc:
            logger.error("Unexpected error querying ArXiv: %s", exc)
            return []


class TechRadarAggregator:
    """
    Multi-source continuous technology radar & knowledge graph ingestion orchestrator.
    Ingests research preprints and open-source trends into SQLiteMemoryStore.
    """

    def __init__(
        self,
        memory_store: SQLiteMemoryStore,
        arxiv_client: Optional[ArxivIngestionClient] = None,
    ) -> None:
        self.memory_store = memory_store
        self.arxiv_client = arxiv_client or ArxivIngestionClient()

    def ingest_arxiv_papers(
        self,
        query: str = "cat:cs.AI",
        max_results: int = 5,
        default_quadrant: str = "techniques",
        default_ring: str = "assess",
    ) -> List[dict[str, Any]]:
        """
        Queries ArXiv, records papers as Tech Radar blips, and links them into the knowledge graph.
        """
        papers = self.arxiv_client.search(query=query, max_results=max_results)
        ingested_records: list[dict[str, Any]] = []

        for paper in papers:
            blip_id = f"arxiv:{paper.paper_id}"

            # 1. ThoughtWorks quadrant classification heuristic
            quadrant = default_quadrant.lower()
            lower_cats = [c.lower() for c in paper.categories]
            if any("cs.ai" in c or "cs.cl" in c or "cs.sd" in c or "eess.as" in c for c in lower_cats):
                quadrant = "techniques"
            elif any("tool" in c or "framework" in c for c in lower_cats):
                quadrant = "tools"
            elif any("platform" in c or "infra" in c for c in lower_cats):
                quadrant = "platforms"

            # 2. Record Tech Radar Blip
            self.memory_store.record_tech_radar_blip(
                blip_id=blip_id,
                title=paper.title,
                ring=default_ring.lower(),
                quadrant=quadrant,
                summary=paper.summary,
                url=paper.pdf_url or (f"https://arxiv.org/abs/{paper.paper_id}"),
                source="arxiv",
                published=paper.published,
                tags=paper.categories,
            )

            # 3. Add Paper Entity Node to Knowledge Graph
            paper_props = {
                "paper_id": paper.paper_id,
                "authors": paper.authors,
                "categories": paper.categories,
                "pdf_url": paper.pdf_url,
                "published": paper.published,
                "summary": paper.summary[:400],
            }
            self.memory_store.add_knowledge_node(
                node_id=blip_id,
                label=paper.title,
                node_type="paper",
                properties=paper_props,
            )

            # 4. Link Category Nodes & Edges
            for cat in paper.categories:
                cat_node_id = f"category:{cat}"
                self.memory_store.add_knowledge_node(
                    node_id=cat_node_id,
                    label=cat,
                    node_type="category",
                    properties={"taxonomy": "arxiv"},
                )
                self.memory_store.add_knowledge_edge(
                    source_id=blip_id,
                    target_id=cat_node_id,
                    relation="categorized_under",
                    weight=1.0,
                    properties={},
                )

            # 5. Link Top Authors
            for author in paper.authors[:3]:
                norm_author = re.sub(r"[^a-zA-Z0-9]+", "_", author).strip("_").lower()
                if not norm_author:
                    continue
                author_node_id = f"author:{norm_author}"
                self.memory_store.add_knowledge_node(
                    node_id=author_node_id,
                    label=author,
                    node_type="author",
                    properties={"full_name": author},
                )
                self.memory_store.add_knowledge_edge(
                    source_id=blip_id,
                    target_id=author_node_id,
                    relation="authored_by",
                    weight=1.0,
                    properties={},
                )

            # 6. Correlate with JARVIS Core Subsystems
            summary_lower = f"{paper.title.lower()} {paper.summary.lower()}"
            domain_correlations = [
                ("domain:voice_pipeline", "Voice & Acoustic Pipeline", ["speech", "voice", "acoustic", "stt", "whisper", "biometrics"]),
                ("domain:intent_routing", "On-Device Intent Routing", ["intent", "router", "routing", "semantic", "slot", "classification"]),
                ("domain:continuous_memory", "Continuous Learning Vault", ["memory", "knowledge graph", "sqlite", "vector", "embedding"]),
            ]
            for domain_id, domain_label, keywords in domain_correlations:
                if any(kw in summary_lower for kw in keywords):
                    self.memory_store.add_knowledge_node(
                        node_id=domain_id,
                        label=domain_label,
                        node_type="domain",
                        properties={},
                    )
                    self.memory_store.add_knowledge_edge(
                        source_id=blip_id,
                        target_id=domain_id,
                        relation="enhances_domain",
                        weight=0.9,
                        properties={},
                    )

            ingested_records.append({
                "blip_id": blip_id,
                "title": paper.title,
                "quadrant": quadrant,
                "ring": default_ring.lower(),
                "categories": paper.categories,
            })

        logger.info("Successfully ingested %d papers from ArXiv query '%s'", len(ingested_records), query)
        return ingested_records

    def ingest_github_trending(
        self,
        repositories: Optional[List[dict[str, Any]]] = None,
        trending_feed_url: str = "",
    ) -> List[dict[str, Any]]:
        """
        Ingests open-source repositories into Tech Radar and knowledge graph.
        Accepts structured repository dictionaries or fetches from an RSS feed.
        """
        repos_to_process: list[dict[str, Any]] = []

        if repositories:
            repos_to_process.extend(repositories)
        elif trending_feed_url:
            try:
                req = urllib.request.Request(
                    trending_feed_url,
                    headers={"User-Agent": "JARVIS-Sovereign-Research/2.0"},
                )
                with urllib.request.urlopen(req, timeout=8.0) as resp:
                    raw_xml = resp.read().decode("utf-8", errors="replace")
                    root = ET.fromstring(raw_xml)
                    channel = root.find("channel")
                    items = channel.findall("item") if channel is not None else root.findall("item")
                    for item in items:
                        t = (item.findtext("title") or "").strip()
                        desc = (item.findtext("description") or "").strip()
                        link = (item.findtext("link") or "").strip()
                        if t and link:
                            repo_name = t.split(" ")[0] if " " in t else t
                            repos_to_process.append({
                                "name": repo_name,
                                "title": t,
                                "description": desc,
                                "url": link,
                                "quadrant": "tools",
                                "ring": "trial",
                                "tags": ["github", "opensource"],
                            })
            except Exception as exc:
                logger.warning("Failed to fetch GitHub trending RSS feed %s: %s", trending_feed_url, exc)

        ingested: list[dict[str, Any]] = []
        for repo in repos_to_process:
            repo_name = repo.get("name", "unknown")
            norm_name = re.sub(r"[^a-zA-Z0-9_\-]+", "_", repo_name).strip("_")
            blip_id = f"gh:{norm_name}"

            title = repo.get("title", repo_name)
            quadrant = str(repo.get("quadrant", "tools")).lower()
            ring = str(repo.get("ring", "trial")).lower()
            summary = repo.get("description", repo.get("summary", ""))
            url = repo.get("url", f"https://github.com/{repo_name}")
            tags = repo.get("tags", ["github", "trending"])

            # Record Radar Blip
            self.memory_store.record_tech_radar_blip(
                blip_id=blip_id,
                title=title,
                ring=ring,
                quadrant=quadrant,
                summary=summary,
                url=url,
                source="github",
                published=repo.get("published", ""),
                tags=tags,
            )

            # Record Knowledge Node
            self.memory_store.add_knowledge_node(
                node_id=blip_id,
                label=title,
                node_type="repository",
                properties={"name": repo_name, "url": url, "summary": summary, "tags": tags},
            )

            # Connect to Tools Category
            cat_id = "category:open_source_tools"
            self.memory_store.add_knowledge_node(
                node_id=cat_id,
                label="Open Source Tools",
                node_type="category",
                properties={},
            )
            self.memory_store.add_knowledge_edge(
                source_id=blip_id,
                target_id=cat_id,
                relation="categorized_under",
                weight=1.0,
                properties={},
            )

            ingested.append({"blip_id": blip_id, "title": title, "quadrant": quadrant, "ring": ring})

        return ingested

    def sync_all(
        self,
        queries: Optional[List[str]] = None,
        trending_repos: Optional[List[dict[str, Any]]] = None,
    ) -> dict[str, int]:
        """
        Orchestrates an end-to-end continuous research ingestion run.
        Synchronizes scientific papers across multiple queries and trending open-source tools.
        """
        default_queries = queries or [
            "cat:cs.AI",
            "cat:cs.CL",
            "cat:cs.SD",
            "all:speech recognition",
        ]

        total_papers = 0
        for q in default_queries:
            results = self.ingest_arxiv_papers(query=q, max_results=3)
            total_papers += len(results)

        total_repos = 0
        if trending_repos:
            repo_results = self.ingest_github_trending(repositories=trending_repos)
            total_repos = len(repo_results)

        all_blips = self.memory_store.query_tech_radar()
        logger.info(
            "Sync complete: %d papers, %d repos ingested; %d total blips in Tech Radar",
            total_papers, total_repos, len(all_blips),
        )
        return {
            "papers_ingested": total_papers,
            "repos_ingested": total_repos,
            "total_radar_blips": len(all_blips),
        }
