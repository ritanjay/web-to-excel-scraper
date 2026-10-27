from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
BASE = "https://books.toscrape.com/"
CAT = BASE + "catalogue/category/books/"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class FakeSite:
    """Serves fixture pages by URL and records what was requested."""

    def __init__(self, pages=None):
        self.pages = pages or {
            BASE: load("home.html"),
            CAT + "travel_2/index.html": load("travel_page1.html"),
            CAT + "travel_2/page-2.html": load("travel_page2.html"),
            CAT + "poetry_23/index.html": load("poetry_page1.html"),
        }
        self.product = load("product.html")
        self.requested = []

    def get(self, url: str) -> str:
        self.requested.append(url)
        if url in self.pages:
            return self.pages[url]
        if "/catalogue/" in url and url.endswith("/index.html") and "/category/" not in url:
            return self.product
        from bookscraper.fetch import FetchError

        raise FetchError(f"{url}: HTTP 404")


@pytest.fixture
def site():
    return FakeSite()
