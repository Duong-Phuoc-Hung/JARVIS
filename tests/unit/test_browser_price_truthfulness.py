"""Truthfulness regressions for browser price extraction."""

from __future__ import annotations

import json

from jarvis.browser.models import PriceComparisonItem
from jarvis.browser.scraper import PriceComparisonAggregator


def test_regex_price_without_title_does_not_create_an_offer() -> None:
    html = '<span class="price">₫1.250.000</span>'

    items = PriceComparisonAggregator.extract_store_products(
        "TestStore",
        html,
        "https://example.test/search",
    )

    assert items == []


def test_regex_offer_keeps_unevidenced_stock_and_shipping_unknown() -> None:
    html = """
    <article class="product-item">
        <h3 class="product-title">Evidence-backed Keyboard</h3>
        <span class="price">₫1.250.000</span>
    </article>
    """

    items = PriceComparisonAggregator.extract_store_products(
        "TestStore",
        html,
        "https://example.test/search",
    )

    assert len(items) == 1
    assert items[0].product_title == "Evidence-backed Keyboard"
    assert items[0].price == 1_250_000.0
    assert items[0].product_url == ""
    assert items[0].in_stock is None
    assert items[0].shipping_cost is None


def test_regex_does_not_pair_title_and_price_from_unrelated_containers() -> None:
    html = """
    <header><h2 class="title">Unrelated Heading</h2></header>
    <footer><span class="price">$99.00</span></footer>
    """

    items = PriceComparisonAggregator.extract_store_products(
        "TestStore",
        html,
        "https://example.test/search",
    )

    assert items == []


def test_regex_currency_comes_from_the_observed_offer_not_other_page_text() -> None:
    html = """
    <article class="product-item">
      <h3 class="product-title">Evidence-backed Keyboard</h3>
      <span class="price">1.250.000 ₫</span>
    </article>
    <footer>International support: $</footer>
    """

    items = PriceComparisonAggregator.extract_store_products(
        "TestStore",
        html,
        "https://example.test/search",
    )

    assert len(items) == 1
    assert items[0].currency == "VND"
    assert items[0].metadata["association"] == "same_dom_container"


def test_json_ld_offer_without_availability_keeps_stock_unknown() -> None:
    html = """
    <script type="application/ld+json">
    {
        "@type": "Product",
        "name": "Evidence-backed Mouse",
        "offers": {
            "@type": "Offer",
            "price": "499000",
            "priceCurrency": "VND"
        }
    }
    </script>
    """

    items = PriceComparisonAggregator.extract_store_products(
        "TestStore",
        html,
        "https://example.test/search",
    )

    assert len(items) == 1
    assert items[0].product_title == "Evidence-backed Mouse"
    assert items[0].product_url == ""
    assert items[0].in_stock is None


def test_json_ld_zero_or_non_finite_price_does_not_create_an_offer() -> None:
    html = """
    <script type="application/ld+json">
    [
      {"@type":"Product","name":"Zero Placeholder","offers":{"price":"0"}},
      {"@type":"Product","name":"Invalid Placeholder","offers":{"price":"NaN"}}
    ]
    </script>
    """

    items = PriceComparisonAggregator.extract_store_products(
        "TestStore",
        html,
        "https://example.test/search",
    )

    assert items == []


def test_price_parser_rejects_numeric_overflow() -> None:
    assert PriceComparisonAggregator.parse_price_value("9" * 10_000) is None


def test_price_item_serializes_unknown_metadata_without_fabrication() -> None:
    item = PriceComparisonItem(
        store_name="TestStore",
        product_title="Evidence-backed Monitor",
        price=4_900_000.0,
        product_url="https://example.test/products/monitor",
        source="json_ld",
        metadata={"evidence": ["title", "price"]},
    )

    payload = item.to_dict()

    assert payload["in_stock"] is None
    assert payload["shipping_cost"] is None
    assert payload["metadata"] == {"evidence": ["title", "price"]}
    json.dumps(payload)
