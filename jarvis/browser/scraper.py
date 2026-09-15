"""
Web Scraping, HTML to Markdown Conversion, and Structured Data Extraction.

Provides:
- HTMLToMarkdownConverter: Cleans raw HTML and converts headings, lists, tables, and links to Markdown.
- HTMLTableParser: Parses HTML tables into structured List[Dict[str, str]] records.
- StructuredDataExtractor: Extracts OpenGraph, Twitter Cards, Meta tags, and Schema.org JSON-LD scripts.
- PriceComparisonAggregator: Extracts normalized price comparison items across diverse eCommerce formats.
- WebScraper: High-level scraper producing comprehensive ScrapeResult objects.
"""

import html as html_module
import json
import logging
import math
import re
import urllib.parse
from html.parser import HTMLParser
from typing import Any

from jarvis.browser.models import (
    PriceComparisonItem,
    ScrapeResult,
)
from jarvis.security.prompt_guard import PromptGuard

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HTML to Markdown Converter
# ---------------------------------------------------------------------------

class HTMLToMarkdownConverter(HTMLParser):
    """
    Parses HTML documents and renders clean, readable GitHub-Flavored Markdown.
    Removes noisy elements (scripts, styles, ads, navbars, footers).
    """

    NOISY_TAGS = {"script", "style", "noscript", "iframe", "svg", "header", "footer", "nav"}

    def __init__(self) -> None:
        super().__init__()
        self._output_chunks: list[str] = []
        self._tag_stack: list[str] = []
        self._skip_depth: int = 0
        self._list_depth: int = 0
        self._list_index: list[int] = []
        self._in_pre: bool = False
        self._in_code: bool = False
        self._current_href: str | None = None
        self._current_link_text: list[str] = []
        self._table_rows: list[list[str]] = []
        self._current_row: list[str] = []
        self._in_table: bool = False
        self._in_cell: bool = False
        self._current_cell_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = {k.lower(): (v or "") for k, v in attrs}
        tag_lower = tag.lower()

        if tag_lower in self.NOISY_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth > 0:
            return

        self._tag_stack.append(tag_lower)

        if tag_lower in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag_lower[1])
            self._output_chunks.append("\n\n" + ("#" * level) + " ")
        elif tag_lower == "p":
            self._output_chunks.append("\n\n")
        elif tag_lower == "br":
            self._output_chunks.append("\n")
        elif tag_lower == "hr":
            self._output_chunks.append("\n\n---\n\n")
        elif tag_lower in ("strong", "b"):
            self._output_chunks.append("**")
        elif tag_lower in ("em", "i"):
            self._output_chunks.append("*")
        elif tag_lower == "code":
            if not self._in_pre:
                self._output_chunks.append("`")
                self._in_code = True
            else:
                cls_attr = attr_dict.get("class", "")
                if "language-" in cls_attr or cls_attr in ("python", "js", "html", "bash", "json", "rust", "go", "sql"):
                    lang = cls_attr.replace("language-", "").strip()
                    if self._output_chunks and self._output_chunks[-1] == "\n\n```\n":
                        self._output_chunks[-1] = f"\n\n```{lang}\n"
        elif tag_lower == "pre":
            self._in_pre = True
            lang = attr_dict.get("class", "").replace("language-", "").strip()
            self._output_chunks.append(f"\n\n```{lang}\n")
        elif tag_lower == "blockquote":
            self._output_chunks.append("\n\n> ")
        elif tag_lower in ("ul", "ol"):
            self._list_depth += 1
            if tag_lower == "ol":
                self._list_index.append(1)
            else:
                self._list_index.append(0)
            self._output_chunks.append("\n")
        elif tag_lower == "li":
            indent = "  " * (self._list_depth - 1)
            if self._list_index and self._list_index[-1] > 0:
                self._output_chunks.append(f"\n{indent}{self._list_index[-1]}. ")
                self._list_index[-1] += 1
            else:
                self._output_chunks.append(f"\n{indent}- ")
        elif tag_lower == "a":
            self._current_href = attr_dict.get("href")
            self._current_link_text = []
        elif tag_lower == "img":
            alt = attr_dict.get("alt", "image")
            src = attr_dict.get("src", "")
            if src:
                self._output_chunks.append(f"![{alt}]({src})")
        elif tag_lower == "table":
            self._in_table = True
            self._table_rows = []
        elif tag_lower == "tr":
            if self._in_table:
                self._current_row = []
        elif tag_lower in ("td", "th"):
            if self._in_table:
                self._in_cell = True
                self._current_cell_text = []

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()

        if tag_lower in self.NOISY_TAGS:
            if self._skip_depth > 0:
                self._skip_depth -= 1
            return
        if self._skip_depth > 0:
            return

        if self._tag_stack and self._tag_stack[-1] == tag_lower:
            self._tag_stack.pop()

        if tag_lower in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._output_chunks.append("\n")
        elif tag_lower in ("strong", "b"):
            self._output_chunks.append("**")
        elif tag_lower in ("em", "i"):
            self._output_chunks.append("*")
        elif tag_lower == "code":
            if self._in_code and not self._in_pre:
                self._output_chunks.append("`")
                self._in_code = False
        elif tag_lower == "pre":
            self._in_pre = False
            self._output_chunks.append("\n```\n\n")
        elif tag_lower in ("ul", "ol"):
            if self._list_depth > 0:
                self._list_depth -= 1
                if self._list_index:
                    self._list_index.pop()
            self._output_chunks.append("\n")
        elif tag_lower == "a":
            link_text = "".join(self._current_link_text).strip()
            if self._current_href and link_text:
                self._output_chunks.append(f"[{link_text}]({self._current_href})")
            elif link_text:
                self._output_chunks.append(link_text)
            self._current_href = None
            self._current_link_text = []
        elif tag_lower in ("td", "th"):
            if self._in_table and self._in_cell:
                cell_val = "".join(self._current_cell_text).strip().replace("|", "\\|")
                self._current_row.append(cell_val)
                self._in_cell = False
                self._current_cell_text = []
        elif tag_lower == "tr":
            if self._in_table and self._current_row:
                self._table_rows.append(self._current_row)
                self._current_row = []
        elif tag_lower == "table":
            if self._in_table:
                self._render_markdown_table()
                self._in_table = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return

        if self._current_href is not None:
            self._current_link_text.append(data)
        elif self._in_cell:
            self._current_cell_text.append(data)
        else:
            self._output_chunks.append(data)

    def _render_markdown_table(self) -> None:
        """Render collected table rows into markdown grid."""
        if not self._table_rows:
            return

        header = self._table_rows[0]
        col_count = len(header)
        if col_count == 0:
            return

        md_table: list[str] = ["\n\n| " + " | ".join(header) + " |"]
        md_table.append("| " + " | ".join(["---"] * col_count) + " |")

        for row in self._table_rows[1:]:
            padded_row = row + [""] * (col_count - len(row))
            md_table.append("| " + " | ".join(padded_row[:col_count]) + " |")

        md_table.append("\n\n")
        self._output_chunks.append("\n".join(md_table))

    def convert(self, html_content: str) -> str:
        """Convert HTML string to clean Markdown."""
        self._output_chunks = []
        self._skip_depth = 0
        self.feed(html_content)
        raw_md = "".join(self._output_chunks)
        # Collapse multiple blank lines
        cleaned = re.sub(r"\n{3,}", "\n\n", raw_md)
        return cleaned.strip()


# ---------------------------------------------------------------------------
# HTML Table Parser
# ---------------------------------------------------------------------------

class HTMLTableParser:
    """Extracts structured tables from raw HTML into List[List[Dict[str, str]]]."""

    @staticmethod
    def parse_tables(html_content: str) -> list[list[dict[str, str]]]:
        """
        Parses all <table> tags and returns a list of tables.
        Each table is represented as a list of dicts keyed by header names.
        """
        tables: list[list[dict[str, str]]] = []
        table_blocks = re.findall(r"<table[^>]*>(.*?)</table>", html_content, re.IGNORECASE | re.DOTALL)

        for tbl in table_blocks:
            rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tbl, re.IGNORECASE | re.DOTALL)
            if not rows:
                continue

            parsed_rows: list[list[str]] = []
            for row in rows:
                cells = re.findall(r"<(?:td|th)[^>]*>(.*?)</(?:td|th)>", row, re.IGNORECASE | re.DOTALL)
                clean_cells = [
                    html_module.unescape(" ".join(re.sub(r"<[^>]+>", " ", c).split()))
                    for c in cells
                ]
                if clean_cells:
                    parsed_rows.append(clean_cells)

            if not parsed_rows:
                continue

            # Treat first row as headers
            headers = parsed_rows[0]
            table_dict_rows: list[dict[str, str]] = []

            for row in parsed_rows[1:]:
                row_dict: dict[str, str] = {}
                for idx, h in enumerate(headers):
                    key = h if h else f"col_{idx+1}"
                    row_dict[key] = row[idx] if idx < len(row) else ""
                table_dict_rows.append(row_dict)

            if table_dict_rows:
                tables.append(table_dict_rows)

        return tables


# ---------------------------------------------------------------------------
# Structured Data Extractor
# ---------------------------------------------------------------------------

class StructuredDataExtractor:
    """Extracts OpenGraph, Twitter Cards, Schema.org JSON-LD, and metadata from HTML."""

    @staticmethod
    def extract_structured_data(html_content: str, base_url: str = "") -> dict[str, Any]:
        result: dict[str, Any] = {
            "opengraph": {},
            "twitter": {},
            "json_ld": [],
            "meta": {},
        }

        # 1. Meta tags
        meta_tags = re.findall(r"<meta\s+([^>]*?)>", html_content, re.IGNORECASE)
        for tag_str in meta_tags:
            name_m = re.search(r'(?:name|property|itemprop)=[\'"]([^\'"]+)[\'"]', tag_str, re.IGNORECASE)
            content_m = re.search(r'content=[\'"]([^\'"]*?)[\'"]', tag_str, re.IGNORECASE)
            if name_m and content_m:
                key = name_m.group(1).lower()
                val = html_module.unescape(content_m.group(1))
                if key.startswith("og:"):
                    result["opengraph"][key[3:]] = val
                elif key.startswith("twitter:"):
                    result["twitter"][key[8:]] = val
                else:
                    result["meta"][key] = val

        # 2. Schema.org JSON-LD
        json_ld_blocks = re.findall(
            r'<script\s+type=[\'"]application/ld\+json[\'"][^>]*>(.*?)</script>',
            html_content,
            re.IGNORECASE | re.DOTALL,
        )
        for block in json_ld_blocks:
            try:
                parsed_json = json.loads(block.strip())
                result["json_ld"].append(parsed_json)
            except Exception as exc:
                logger.debug(
                    "Failed parsing JSON-LD block (%s).",
                    type(exc).__name__,
                )

        return result

    @staticmethod
    def extract_links_and_images(html_content: str, base_url: str = "") -> tuple[list[str], list[str]]:
        """Extract all unique hyperlinks and image URLs resolved to absolute paths."""
        links: list[str] = []
        images: list[str] = []

        link_matches = re.findall(r'<a\s+[^>]*?href=[\'"]([^\'"]+)[\'"]', html_content, re.IGNORECASE)
        for href in link_matches:
            if href.startswith("javascript:") or href.startswith("#") or href.startswith("mailto:"):
                continue
            abs_url = urllib.parse.urljoin(base_url, href) if base_url else href
            if abs_url not in links:
                links.append(abs_url)

        img_matches = re.findall(r'<img\s+[^>]*?src=[\'"]([^\'"]+)[\'"]', html_content, re.IGNORECASE)
        for src in img_matches:
            if src.startswith("data:"):
                continue
            abs_url = urllib.parse.urljoin(base_url, src) if base_url else src
            if abs_url not in images:
                images.append(abs_url)

        return links, images


# ---------------------------------------------------------------------------
# Price Comparison Aggregator
# ---------------------------------------------------------------------------


class _ObservedOfferCardParser(HTMLParser):
    """Collect title/price evidence only when it shares one product container."""

    _CARD_TAGS = {"article", "div", "li", "section"}
    _VOID_TAGS = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
    _CARD_CLASSES = {
        "item",
        "offer",
        "product",
        "product-card",
        "product-item",
        "product-tile",
        "result-item",
        "search-result",
    }

    def __init__(self) -> None:
        super().__init__()
        self.cards: list[dict[str, str]] = []
        self._frames: list[tuple[str, bool, bool]] = []
        self._card: dict[str, Any] | None = None
        self._card_depth = -1

    @staticmethod
    def _classes(attrs: dict[str, str]) -> set[str]:
        return {token.lower() for token in attrs.get("class", "").split() if token}

    @classmethod
    def _is_card(cls, tag: str, classes: set[str]) -> bool:
        return tag in cls._CARD_TAGS and bool(classes & cls._CARD_CLASSES)

    @staticmethod
    def _is_title(tag: str, classes: set[str]) -> bool:
        return tag in {"h2", "h3"} or any(
            token in {"name", "pro-name", "product-name", "product-title", "title"}
            or token.endswith("-title")
            for token in classes
        )

    @staticmethod
    def _is_price(classes: set[str]) -> bool:
        return any(token == "gia" or "price" in token for token in classes)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.lower(): value or "" for key, value in attrs}
        classes = self._classes(attributes)
        if self._card is None and self._is_card(tag, classes):
            self._card = {"title": [], "price": [], "href": ""}
            self._card_depth = len(self._frames)

        parent_title = self._frames[-1][1] if self._frames else False
        parent_price = self._frames[-1][2] if self._frames else False
        title_scope = parent_title or self._is_title(tag, classes)
        price_scope = parent_price or self._is_price(classes)
        if tag not in self._VOID_TAGS:
            self._frames.append((tag, title_scope, price_scope))

        if self._card is not None:
            href = attributes.get("href", "")
            if href and not self._card["href"]:
                self._card["href"] = href
            data_price = attributes.get("data-price", "")
            if data_price:
                self._card["price"].append(data_price)

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in self._VOID_TAGS:
            self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self._card is None or not self._frames or not data.strip():
            return
        _, title_scope, price_scope = self._frames[-1]
        if title_scope:
            self._card["title"].append(data)
        if price_scope:
            self._card["price"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self._frames:
            return
        self._frames.pop()
        if self._card is not None and len(self._frames) == self._card_depth:
            title = " ".join(" ".join(self._card["title"]).split())
            price = " ".join(" ".join(self._card["price"]).split())
            self.cards.append(
                {"title": title, "price": price, "href": str(self._card["href"])}
            )
            self._card = None
            self._card_depth = -1


class PriceComparisonAggregator:
    """
    Parses and aggregates product pricing information across various eCommerce storefronts.
    Identifies lowest prices, currency formats, stock availability, and merchant titles.
    """

    @staticmethod
    def parse_price_value(price_str: str) -> float | None:
        """
        Normalize price string (e.g. '$1,299.99', '24.990.000 ₫', '1500000 VND') to float.
        """
        if not price_str:
            return None
        # Remove currency symbols and letters
        clean = re.sub(r"[^\d.,]", "", price_str).strip()
        if not clean:
            return None

        # Format detection: Vietnamese / European (dots as thousand separator, comma as decimal)
        # vs US (commas as thousand separator, dot as decimal)
        if "." in clean and "," in clean:
            if clean.rfind(",") > clean.rfind("."):
                # European/VN format: 1.200,50 -> 1200.50
                clean = clean.replace(".", "").replace(",", ".")
            else:
                # US format: 1,200.50 -> 1200.50
                clean = clean.replace(",", "")
        elif "." in clean and clean.count(".") > 1:
            # Multi-dot VN format: 24.990.000 -> 24990000
            clean = clean.replace(".", "")
        elif "," in clean and clean.count(",") > 1:
            # Multi-comma US format: 1,000,000 -> 1000000
            clean = clean.replace(",", "")
        elif "," in clean and len(clean.split(",")[-1]) == 3:
            # Thousand separator without decimal: 24,990 -> 24990
            clean = clean.replace(",", "")
        elif "." in clean and len(clean.split(".")[-1]) == 3:
            # Thousand separator without decimal: 24.990 -> 24990
            clean = clean.replace(".", "")
        elif "," in clean:
            # Single comma decimal: 99,50 -> 99.50
            clean = clean.replace(",", ".")

        try:
            value = float(clean)
            return value if math.isfinite(value) else None
        except ValueError:
            return None

    @classmethod
    def extract_store_products(
        cls,
        store_name: str,
        html_content: str,
        base_url: str = "",
    ) -> list[PriceComparisonItem]:
        """
        Extracts product items and prices from a store's HTML listing.
        """
        items: list[PriceComparisonItem] = []

        # 1. Try extracting from JSON-LD Schema (Product / Offer)
        json_ld_blocks = re.findall(
            r'<script\s+type=[\'"]application/ld\+json[\'"][^>]*>(.*?)</script>',
            html_content,
            re.IGNORECASE | re.DOTALL,
        )
        for block in json_ld_blocks:
            try:
                data = json.loads(block)
                if isinstance(data, list):
                    nodes = data
                elif isinstance(data, dict) and "@graph" in data:
                    nodes = data["@graph"]
                else:
                    nodes = [data]

                for node in nodes:
                    if not isinstance(node, dict) or node.get("@type") not in (
                        "Product",
                        "IndividualProduct",
                    ):
                        continue
                    title = str(node.get("name") or "").strip()
                    offers_value = node.get("offers", {})
                    offers_list = offers_value if isinstance(offers_value, list) else [offers_value]
                    for offers in offers_list:
                        if not isinstance(offers, dict):
                            continue
                        price_val = cls.parse_price_value(str(offers.get("price") or offers.get("lowPrice") or ""))
                        curr = str(offers.get("priceCurrency") or "VND")
                        url_val = str(offers.get("url") or "").strip()
                        if price_val is not None and price_val > 0 and title:
                            availability = str(offers.get("availability") or "")
                            availability_name = availability.rstrip("/").rsplit("/", 1)[-1].lower()
                            in_stock = {
                                "instock": True,
                                "outofstock": False,
                            }.get(availability_name)
                            items.append(
                                PriceComparisonItem(
                                    store_name=store_name,
                                    product_title=title,
                                    price=price_val,
                                    currency=curr,
                                    product_url=(
                                        urllib.parse.urljoin(base_url, url_val)
                                        if url_val
                                        else ""
                                    ),
                                    in_stock=in_stock,
                                    source="json_ld",
                                    metadata={
                                        "evidence": ["title", "price"],
                                        "association": "same_json_ld_product",
                                    },
                                )
                            )
            except Exception:
                pass

        if items:
            return items

        # 2. DOM evidence, scoped to a single product container. Never zip
        # unrelated title and price nodes from different regions of a page.
        parser = _ObservedOfferCardParser()
        parser.feed(html_content)
        for card in parser.cards[:10]:
            title = html_module.unescape(card["title"]).strip()
            price_text = html_module.unescape(card["price"]).strip()
            price = cls.parse_price_value(price_text)
            if len(title) <= 3 or price is None or price <= 0:
                continue
            currency = "USD" if "$" in price_text else "EUR" if "€" in price_text else "VND"
            observed_href = str(card["href"] or "").strip()
            items.append(
                PriceComparisonItem(
                    store_name=store_name,
                    product_title=title,
                    price=price,
                    currency=currency,
                    product_url=(
                        urllib.parse.urljoin(base_url, observed_href)
                        if observed_href
                        else ""
                    ),
                    source="html_regex",
                    metadata={
                        "evidence": ["title", "price"],
                        "association": "same_dom_container",
                    },
                )
            )

        return items

    @classmethod
    def aggregate_and_sort(cls, items: list[PriceComparisonItem]) -> list[PriceComparisonItem]:
        """Sort items by price ascending and tag lowest price."""
        if not items:
            return []
        sorted_items = sorted(items, key=lambda x: x.price)
        return sorted_items


# ---------------------------------------------------------------------------
# WebScraper High-Level Coordinator
# ---------------------------------------------------------------------------

class WebScraper:
    """High-level scraper producing clean Markdown, tables, and structured data."""

    def __init__(self) -> None:
        self.markdown_converter = HTMLToMarkdownConverter()
        self.table_parser = HTMLTableParser()
        self.data_extractor = StructuredDataExtractor()

    def scrape_html(self, html_content: str, url: str = "") -> ScrapeResult:
        """Parse raw HTML content into a full ScrapeResult with PromptGuard sanitization."""
        # 1. Document Title
        title_m = re.search(r"<title[^>]*>(.*?)</title>", html_content, re.IGNORECASE | re.DOTALL)
        raw_title = html_module.unescape(title_m.group(1).strip()) if title_m else ""
        title = PromptGuard.sanitize(raw_title, source=url or "web").clean_text if raw_title else ""

        # 2. Markdown Content
        # HTMLParser instances retain stack state after malformed/unclosed input;
        # use a fresh converter so one origin cannot contaminate the next scrape.
        raw_md = HTMLToMarkdownConverter().convert(html_content)
        md_sanitized = PromptGuard.sanitize(raw_md, source=url or "web") if raw_md else None
        md_content = md_sanitized.clean_text if md_sanitized else ""

        # 3. Plain Text Content
        plain_text_raw = " ".join(re.sub(r"<[^>]+>", " ", html_content).split())
        plain_text_raw = html_module.unescape(plain_text_raw)
        text_sanitized = PromptGuard.sanitize(plain_text_raw, source=url or "web") if plain_text_raw else None
        plain_text = text_sanitized.clean_text if text_sanitized else ""

        # 4. Tables
        tables = self.table_parser.parse_tables(html_content)

        # 5. Structured Data & Links
        structured = self.data_extractor.extract_structured_data(html_content, base_url=url)
        links, images = self.data_extractor.extract_links_and_images(html_content, base_url=url)

        is_suspicious = bool(
            (md_sanitized and md_sanitized.is_suspicious) or
            (text_sanitized and text_sanitized.is_suspicious)
        )

        return ScrapeResult(
            url=url,
            title=title,
            markdown_content=md_content,
            text_content=plain_text,
            structured_data=structured,
            links=links,
            images=images,
            tables=tables,
            metadata={
                "html_size_bytes": len(html_content),
                "tables_count": len(tables),
                "is_suspicious": is_suspicious,
                "prompt_guard_active": True,
            },
        )
