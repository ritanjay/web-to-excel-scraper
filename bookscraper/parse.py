"""HTML parsing for books.toscrape.com.

Every function here is pure (HTML string in, data out) so it can be tested
offline against saved pages and reused for other sites with similar markup.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .models import Book

RATING_WORDS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}

_PRICE_RE = re.compile(r"(\d+(?:[.,]\d+)?)")
_STOCK_RE = re.compile(r"\((\d+)\s+available\)")
_PAGE_RE = re.compile(r"Page\s+(\d+)\s+of\s+(\d+)", re.I)


class ParseError(ValueError):
    """Raised when a page does not have the structure we expect."""


@dataclass
class ListingPage:
    books: list[Book]
    next_url: Optional[str]
    page: Optional[int] = None
    total_pages: Optional[int] = None


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def parse_price(text: str) -> float:
    """Extract a price from text like "£51.77".

    Also copes with mis-decoded pages ("Â£51.77") and thousands separators.
    """
    cleaned = text.replace(",", "")
    m = _PRICE_RE.search(cleaned)
    if not m:
        raise ParseError(f"no price in {text!r}")
    return float(m.group(1))


def parse_rating(tag) -> int:
    """Read the star rating from a ``<p class="star-rating Three">`` tag."""
    if tag is None:
        return 0
    for cls in tag.get("class", []):
        if cls in RATING_WORDS:
            return RATING_WORDS[cls]
    return 0


def parse_listing(html: str, page_url: str, category: str = "") -> ListingPage:
    """Parse a catalogue/category listing page."""
    soup = _soup(html)
    pods = soup.select("article.product_pod")
    if not pods and not soup.select_one("ol.row, section"):
        raise ParseError(f"{page_url}: not a listing page")

    books = []
    for pod in pods:
        link = pod.select_one("h3 a")
        price = pod.select_one(".price_color")
        if link is None or price is None:
            raise ParseError(f"{page_url}: product card without title or price")
        img = pod.select_one(".image_container img")
        availability = pod.select_one(".availability")
        books.append(
            Book(
                # The visible link text is truncated ("A Light in the ..."); the
                # title attribute has the full name.
                title=(link.get("title") or link.get_text()).strip(),
                price=parse_price(price.get_text()),
                rating=parse_rating(pod.select_one("p.star-rating")),
                in_stock="in stock" in (availability.get_text().lower() if availability else ""),
                url=urljoin(page_url, link["href"]),
                category=category,
                image_url=urljoin(page_url, img["src"]) if img and img.get("src") else "",
            )
        )

    nxt = soup.select_one("ul.pager li.next a")
    page = total = None
    current = soup.select_one("ul.pager li.current")
    if current:
        m = _PAGE_RE.search(current.get_text())
        if m:
            page, total = int(m.group(1)), int(m.group(2))
    return ListingPage(
        books=books,
        next_url=urljoin(page_url, nxt["href"]) if nxt else None,
        page=page,
        total_pages=total,
    )


def parse_categories(html: str, page_url: str) -> dict[str, str]:
    """Return {category name: absolute URL} from the sidebar.

    The top-level "Books" entry (which lists everything) is skipped.
    """
    soup = _soup(html)
    links = soup.select(".side_categories ul li ul li a")
    if not links:
        raise ParseError(f"{page_url}: no category sidebar found")
    return {a.get_text(strip=True): urljoin(page_url, a["href"]) for a in links}


def parse_product(html: str, page_url: str) -> dict:
    """Parse a product page into a dict of detail fields."""
    soup = _soup(html)
    main = soup.select_one(".product_main")
    if main is None:
        raise ParseError(f"{page_url}: not a product page")

    table = {}
    for row in soup.select("table.table tr"):
        th, td = row.find("th"), row.find("td")
        if th and td:
            table[th.get_text(strip=True)] = td.get_text(strip=True)

    availability = table.get("Availability", "")
    stock = _STOCK_RE.search(availability)

    desc = None
    header = soup.select_one("#product_description")
    if header:
        p = header.find_next_sibling("p")
        if p:
            desc = p.get_text(strip=True)

    crumbs = [li.get_text(strip=True) for li in soup.select("ul.breadcrumb li")]
    category = crumbs[-2] if len(crumbs) >= 3 else ""

    reviews = table.get("Number of reviews")
    return {
        "title": main.find("h1").get_text(strip=True) if main.find("h1") else "",
        "price": parse_price(main.select_one(".price_color").get_text()),
        "rating": parse_rating(main.select_one("p.star-rating")),
        "upc": table.get("UPC"),
        "stock_count": int(stock.group(1)) if stock else 0,
        "in_stock": "in stock" in availability.lower(),
        "num_reviews": int(reviews) if reviews and reviews.isdigit() else None,
        "description": desc,
        "category": category,
    }
