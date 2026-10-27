"""Crawl logic: walk categories and listing pages, optionally product pages."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional, Protocol

from .fetch import FetchError
from .models import Book
from .parse import ParseError, parse_categories, parse_listing, parse_product

log = logging.getLogger(__name__)

BASE_URL = "https://books.toscrape.com/"


class PageSource(Protocol):
    def get(self, url: str) -> str: ...


@dataclass
class Filters:
    categories: list[str] = field(default_factory=list)  # case-insensitive names
    min_rating: int = 0
    max_price: Optional[float] = None
    in_stock_only: bool = False

    def keep(self, book: Book) -> bool:
        if book.rating < self.min_rating:
            return False
        if self.max_price is not None and book.price > self.max_price:
            return False
        if self.in_stock_only and not book.in_stock:
            return False
        return True


@dataclass
class ScrapeResult:
    books: list[Book]
    pages_visited: int
    errors: list[str]
    categories: list[str]


def _select_categories(all_cats: dict[str, str], wanted: Iterable[str]) -> dict[str, str]:
    wanted = [w.strip().lower() for w in wanted if w.strip()]
    if not wanted:
        return all_cats
    by_lower = {name.lower(): (name, url) for name, url in all_cats.items()}
    missing = [w for w in wanted if w not in by_lower]
    if missing:
        raise ValueError(
            f"unknown categor{'y' if len(missing) == 1 else 'ies'}: {', '.join(missing)}. "
            f"Available: {', '.join(sorted(all_cats))}"
        )
    return dict(by_lower[w] for w in wanted)


def scrape(
    source: PageSource,
    base_url: str = BASE_URL,
    filters: Optional[Filters] = None,
    details: bool = False,
    max_pages: Optional[int] = None,
    progress: Callable[[str], None] = lambda msg: None,
) -> ScrapeResult:
    """Scrape the catalogue category by category.

    Walking categories (instead of the flat "all books" listing) costs a few
    extra requests but gives every book its category without fetching each
    product page. ``max_pages`` caps the total listing pages visited, which is
    handy for quick test runs.
    """
    filters = filters or Filters()
    errors: list[str] = []
    pages = 0

    home = source.get(base_url)
    cats = _select_categories(parse_categories(home, base_url), filters.categories)
    books: list[Book] = []
    seen: set[str] = set()

    for name, url in cats.items():
        next_url: Optional[str] = url
        while next_url:
            if max_pages is not None and pages >= max_pages:
                progress(f"Stopped after {pages} pages (--max-pages)")
                next_url = None
                break
            try:
                listing = parse_listing(source.get(next_url), next_url, category=name)
            except (FetchError, ParseError) as exc:
                errors.append(str(exc))
                log.error("%s", exc)
                break
            pages += 1
            for book in listing.books:
                if book.url not in seen:  # a book can appear in only one category, but be safe
                    seen.add(book.url)
                    books.append(book)
            label = f"{listing.page}/{listing.total_pages}" if listing.page else "1/1"
            progress(f"{name}: page {label}, {len(books)} books so far")
            next_url = listing.next_url
        if max_pages is not None and pages >= max_pages:
            break

    kept = [b for b in books if filters.keep(b)]

    if details:
        for i, book in enumerate(kept, 1):
            try:
                info = parse_product(source.get(book.url), book.url)
            except (FetchError, ParseError) as exc:
                errors.append(str(exc))
                log.error("%s", exc)
                continue
            book.upc = info["upc"]
            book.stock_count = info["stock_count"]
            book.num_reviews = info["num_reviews"]
            book.description = info["description"]
            if i % 25 == 0 or i == len(kept):
                progress(f"Details: {i}/{len(kept)}")

    kept.sort(key=lambda b: (b.category, b.title))
    return ScrapeResult(books=kept, pages_visited=pages, errors=errors, categories=list(cats))
