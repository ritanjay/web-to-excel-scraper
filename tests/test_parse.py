import pytest

from bookscraper.parse import (
    ParseError,
    parse_categories,
    parse_listing,
    parse_price,
    parse_product,
)

from .conftest import BASE, CAT, load


@pytest.mark.parametrize(
    "text,expected",
    [("£51.77", 51.77), ("Â£44.34", 44.34), ("£1,234.50", 1234.5), (" 12 ", 12.0)],
)
def test_parse_price(text, expected):
    assert parse_price(text) == pytest.approx(expected)


def test_parse_price_rejects_garbage():
    with pytest.raises(ParseError):
        parse_price("free")


def test_listing_fields_and_absolute_urls():
    url = CAT + "travel_2/index.html"
    page = parse_listing(load("travel_page1.html"), url, category="Travel")
    # Full titles come from the title attribute, not the truncated link text.
    assert [b.title for b in page.books] == [
        "It's Only the Himalayas",
        "Full Moon over Noah’s Ark: An Odyssey to Mount Ararat and Beyond",
    ]
    first = page.books[0]
    assert first.price == pytest.approx(45.17)
    assert first.rating == 2
    assert first.in_stock is True
    assert first.category == "Travel"
    assert first.url == BASE + "catalogue/its-only-the-himalayas_981/index.html"
    assert first.image_url.startswith(BASE + "media/cache/")
    assert page.next_url == CAT + "travel_2/page-2.html"
    assert (page.page, page.total_pages) == (1, 2)


def test_listing_last_page_and_out_of_stock():
    url = CAT + "travel_2/page-2.html"
    page = parse_listing(load("travel_page2.html"), url)
    assert page.next_url is None
    assert page.books[0].in_stock is False
    assert page.books[0].price == pytest.approx(44.34)  # mis-decoded "Â£" handled


def test_listing_without_pager():
    page = parse_listing(load("poetry_page1.html"), CAT + "poetry_23/index.html")
    assert len(page.books) == 2
    assert page.next_url is None
    assert page.page is None


def test_categories_skip_top_level_and_strip_whitespace():
    cats = parse_categories(load("home.html"), BASE)
    assert cats == {
        "Travel": CAT + "travel_2/index.html",
        "Poetry": CAT + "poetry_23/index.html",
    }


def test_product_details():
    info = parse_product(
        load("product.html"), BASE + "catalogue/a-light-in-the-attic_1000/index.html"
    )
    assert info["title"] == "A Light in the Attic"
    assert info["upc"] == "a897fe39b1053632"
    assert info["stock_count"] == 22
    assert info["num_reviews"] == 0
    assert info["rating"] == 3
    assert info["category"] == "Poetry"
    assert info["description"].startswith("It's hard to imagine")


def test_wrong_page_type_is_reported():
    with pytest.raises(ParseError):
        parse_product(load("travel_page1.html"), "x")
    with pytest.raises(ParseError):
        parse_categories("<html><body>nothing</body></html>", "x")
