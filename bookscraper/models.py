"""Data model for a scraped book."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class Book:
    """One product from the catalogue.

    Fields marked "details only" are filled in only when product pages are
    fetched (``--details``); otherwise they stay ``None``.
    """

    title: str
    price: float  # in GBP
    rating: int  # 1-5 stars
    in_stock: bool
    url: str
    category: str = ""
    image_url: str = ""
    # details only
    upc: Optional[str] = None
    stock_count: Optional[int] = None
    num_reviews: Optional[int] = None
    description: Optional[str] = None
    extra: dict = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("extra")
        return d


# Column order used by every exporter.
COLUMNS = [
    "title",
    "category",
    "price",
    "rating",
    "in_stock",
    "stock_count",
    "upc",
    "num_reviews",
    "url",
    "image_url",
    "description",
]
