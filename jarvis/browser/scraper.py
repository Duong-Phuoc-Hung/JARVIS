"""
Web Scraping, HTML to Markdown Conversion, and Structured Data Extraction.

Provides:
- HTMLToMarkdownConverter: Cleans raw HTML and converts headings, lists, tables, and links to Markdown.
- HTMLTableParser: Parses HTML tables into structured List[Dict[str, str]] records.
- StructuredDataExtractor: Extracts OpenGraph, Twitter Cards, Meta tags, and Schema.org JSON-LD scripts.
- PriceComparisonAggregator: Extracts normalized price comparison items across diverse eCommerce formats.
- WebScraper: High-level scraper producing comprehensive ScrapeResult objects.
"""

from html.parser import HTMLParser
import html as html_module
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
import urllib.parse

from jarvis.browser.models import (
    PriceComparisonItem,
    ScrapeResult,
)

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
        self._output_chunks: List[str] = []
        self._tag_stack: List[str] = []
        self._skip_depth: int = 0
        self._list_depth: int = 0
        self._list_index: List[int] = []
        self._in_pre: bool = False
        self._in_code: bool = False
        self._current_href: Optional[str] = None
        self._current_link_text: List[str] = []
        self._table_rows: List[List[str]] = []
        self._current_row: List[str] = []
        self._in_table: bool = False
        self._in_cell: bool = False
        self._current_cell_text: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
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
        elif tag_lower == "pre":
            self._in_pre = True
            lang = attr_dict.get("class", "").replace("language-", "")
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

        md_table: List[str] = ["\n\n| " + " | ".join(header) + " |"]
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
    def parse_tables(html_content: str) -> List[List[Dict[str, str]]]:
        """
        Parses all <table> tags and returns a list of tables.
        Each table is represented as a list of dicts keyed by header names.
        """
        tables: List[List[Dict[str, str]]] = []
        table_blocks = re.findall(r"<table[^>]*>(.*?)</table>", html_content, re.IGNORECASE | re.DOTALL)

        for tbl in table_blocks:
            rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tbl, re.IGNORECASE | re.DOTALL)
            if not rows:
                continue

            parsed_rows: List[List[str]] = []
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
            table_dict_rows: List[Dict[str, str]] = []

            for row in parsed_rows[1:]:
                row_dict: Dict[str, str] = {}
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
    def extract_structured_data(html_content: str, base_url: str = "") -> Dict[str, Any]:
        result: Dict[str, Any] = {
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
                logger.debug("Failed parsing JSON-LD block: %s", exc)

        return result

    @staticmethod
    def extract_links_and_images(html_content: str, base_url: str = "") -> Tuple[List[str], List[str]]:
        """Extract all unique hyperlinks and image URLs resolved to absolute paths."""
        links: List[str] = []
        images: List[str] = []

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

class PriceComparisonAggregator:
    """
    Parses and aggregates product pricing information across various eCommerce storefronts.
    Identifies lowest prices, currency formats, stock availability, and merchant titles.
    """

    @staticmethod
    def parse_price_value(price_str: str) -> Optional[float]:
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
            return float(clean)
        except ValueError:
            return None

    @classmethod
    def extract_store_products(
        cls,
        store_name: str,
        html_content: str,
        base_url: str = "",
    ) -> List[PriceComparisonItem]:
        """
        Extracts product items and prices from a store's HTML listing.
        """
        items: List[PriceComparisonItem] = []

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
                    if node.get("@type") in ("Product", "IndividualProduct"):
                        title = node.get("name", "")
                        offers = node.get("offers", {})
                        if isinstance(offers, list) and offers:
                            offers = offers[0]
                        price_val = offers.get("price") or offers.get("lowPrice")
                        curr = offers.get("priceCurrency", "VND")
                        url_val = offers.get("url", base_url)
                        if price_val and title:
                            items.append(
                                PriceComparisonItem(
                                    store_name=store_name,
                                    product_title=title,
                                    price=float(price_val),
                                    currency=curr,
                                    product_url=urllib.parse.urljoin(base_url, url_val),
                                    in_stock=offers.get("availability", "").endswith("InStock"),
                                    source="json_ld",
                                )
                            )
            except Exception:
                pass

        if items:
            return items

        # 2. DOM Pattern Matching for Product Cards
        # Match common eCommerce price selectors and patterns
        price_patterns = [
            r'class=[\'"][^\'"]*(?:price|gia|current-price|price-box)[^\'"]*[\'"][^>]*>([^<]+<)?([^<]+)',
            r'data-price=[\'"]([^\'"]+)[\'"]',
            r'(?:₫|\$|VND|€)\s*([\d.,]+)',
            r'([\d.,]+)\s*(?:₫|VND|đ)',
        ]

        title_patterns = [
            r'class=[\'"][^\'"]*(?:product-title|title|name|pro-name)[^\'"]*[\'"][^>]*>(?:<a[^>]*>)?([^<]+)',
            r'<h[23][^>]*>(?:<a[^>]*>)?([^<]+)</h[23]>',
        ]

        titles = []
        for tp in title_patterns:
            matches = re.findall(tp, html_content, re.IGNORECASE)
            for m in matches:
                clean_t = html_module.unescape(m.strip())
                if len(clean_t) > 3 and clean_t not in titles:
                    titles.append(clean_t)

        prices = []
        for pp in price_patterns:
            matches = re.findall(pp, html_content, re.IGNORECASE)
            for m in matches:
                p_text = m if isinstance(m, str) else (m[1] if len(m) > 1 and m[1] else m[0])
                p_val = cls.parse_price_value(p_text)
                if p_val and p_val > 0 and p_val not in prices:
                    prices.append(p_val)

        # Pair titles with prices
        for idx, p in enumerate(prices[:10]):
            t = titles[idx] if idx < len(titles) else f"{store_name} Product Offer #{idx+1}"
            currency = "USD" if "$" in html_content else "VND"
            items.append(
                PriceComparisonItem(
                    store_name=store_name,
                    product_title=t,
                    price=p,
                    currency=currency,
                    product_url=base_url,
                    in_stock=True,
                    source="html_regex",
                )
            )

        return items

    @classmethod
    def aggregate_and_sort(cls, items: List[PriceComparisonItem]) -> List[PriceComparisonItem]:
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
        """Parse raw HTML content into a full ScrapeResult."""
        # 1. Document Title
        title_m = re.search(r"<title[^>]*>(.*?)</title>", html_content, re.IGNORECASE | re.DOTALL)
        title = html_module.unescape(title_m.group(1).strip()) if title_m else ""

        # 2. Markdown Content
        md_content = self.markdown_converter.convert(html_content)

        # 3. Plain Text Content
        plain_text = " ".join(re.sub(r"<[^>]+>", " ", html_content).split())
        plain_text = html_module.unescape(plain_text)

        # 4. Tables
        tables = self.table_parser.parse_tables(html_content)

        # 5. Structured Data & Links
        structured = self.data_extractor.extract_structured_data(html_content, base_url=url)
        links, images = self.data_extractor.extract_links_and_images(html_content, base_url=url)

        return ScrapeResult(
            url=url,
            title=title,
            markdown_content=md_content,
            text_content=plain_text,
            structured_data=structured,
            links=links,
            images=images,
            tables=tables,
            metadata={"html_size_bytes": len(html_content), "tables_count": len(tables)},
        )
