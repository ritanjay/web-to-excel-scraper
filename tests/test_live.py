"""Smoke test against the real site. Skipped by default; run with: pytest -m live"""

import pytest

from bookscraper.fetch import Fetcher
from bookscraper.parse import parse_product
from bookscraper.scrape import Filters, scrape

pytestmark = pytest.mark.live


def test_real_site_selectors_still_work():
    fetcher = Fetcher(delay=0.5)
    result = scrape(fetcher, filters=Filters(categories=["Travel", "Poetry"]))
    assert result.errors == []
    assert len(result.books) >= 20  # Travel has 11, Poetry 19 at the time of writing
    for book in result.books:
        assert book.title and not book.title.endswith("...")
        assert 0 < book.price < 1000
        assert 1 <= book.rating <= 5
        assert book.url.startswith("https://books.toscrape.com/catalogue/")
    info = parse_product(fetcher.get(result.books[0].url), result.books[0].url)
    assert info["upc"] and len(info["upc"]) == 16
