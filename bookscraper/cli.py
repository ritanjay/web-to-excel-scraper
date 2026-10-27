"""Command-line interface."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Optional, Sequence

from . import __version__
from .export import write_csv, write_excel, write_json
from .fetch import Fetcher, FetchError
from .parse import ParseError
from .scrape import BASE_URL, Filters, scrape

EXAMPLES = """
examples:
  bookscraper -o books.xlsx
  bookscraper --category Travel --category Poetry --details -o picks.xlsx
  bookscraper --min-rating 4 --max-price 20 --in-stock -o bargains.xlsx --csv bargains.csv
  bookscraper --max-pages 3 --cache .cache -o quick-test.xlsx
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bookscraper",
        description="Scrape books.toscrape.com into a formatted Excel workbook (plus CSV/JSON).",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    out = p.add_argument_group("output")
    out.add_argument(
        "-o",
        "--out",
        type=Path,
        default=Path("books.xlsx"),
        help="Excel file to write (default: books.xlsx)",
    )
    out.add_argument("--csv", type=Path, help="also write a CSV file")
    out.add_argument("--json", type=Path, help="also write a JSON file")

    what = p.add_argument_group("what to scrape")
    what.add_argument(
        "-c",
        "--category",
        action="append",
        default=[],
        help="only this category (repeatable, case-insensitive)",
    )
    what.add_argument(
        "--details",
        action="store_true",
        help="also open each product page for UPC, stock count, reviews, description",
    )
    what.add_argument("--max-pages", type=int, help="stop after N listing pages (quick runs)")

    flt = p.add_argument_group("filters")
    flt.add_argument("--min-rating", type=int, default=0, choices=range(0, 6), metavar="0-5")
    flt.add_argument("--max-price", type=float, help="maximum price in GBP")
    flt.add_argument("--in-stock", action="store_true", help="only books in stock")

    net = p.add_argument_group("politeness / network")
    net.add_argument(
        "--delay", type=float, default=0.5, help="seconds between requests (default 0.5)"
    )
    net.add_argument("--retries", type=int, default=3)
    net.add_argument("--cache", type=Path, help="cache pages in this folder for fast re-runs")
    net.add_argument("--base-url", default=BASE_URL, help=argparse.SUPPRESS)

    p.add_argument("-q", "--quiet", action="store_true", help="no progress output")
    p.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    return p


def describe_filters(args: argparse.Namespace) -> str:
    parts = []
    if args.category:
        parts.append("categories=" + ", ".join(args.category))
    if args.min_rating:
        parts.append(f"rating>={args.min_rating}")
    if args.max_price is not None:
        parts.append(f"price<=£{args.max_price:g}")
    if args.in_stock:
        parts.append("in stock only")
    if args.max_pages:
        parts.append(f"max {args.max_pages} pages")
    return "; ".join(parts)


def main(argv: Optional[Sequence[str]] = None, fetcher: Optional[Fetcher] = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    say = (lambda m: None) if args.quiet else (lambda m: print(m, file=sys.stderr, flush=True))

    fetcher = fetcher or Fetcher(delay=args.delay, retries=args.retries, cache_dir=args.cache)
    filters = Filters(
        categories=args.category,
        min_rating=args.min_rating,
        max_price=args.max_price,
        in_stock_only=args.in_stock,
    )

    started = time.monotonic()
    try:
        result = scrape(
            fetcher,
            base_url=args.base_url,
            filters=filters,
            details=args.details,
            max_pages=args.max_pages,
            progress=say,
        )
    except ValueError as exc:  # e.g. unknown category
        print(f"bookscraper: {exc}", file=sys.stderr)
        return 2
    except (FetchError, ParseError) as exc:
        print(f"bookscraper: {exc}", file=sys.stderr)
        return 1

    written = [
        write_excel(
            result.books, args.out, source_url=args.base_url, filters_desc=describe_filters(args)
        )
    ]
    if args.csv:
        written.append(write_csv(result.books, args.csv))
    if args.json:
        written.append(write_json(result.books, args.json))

    elapsed = time.monotonic() - started
    say(
        f"\nDone: {len(result.books)} books from {result.pages_visited} pages in {elapsed:.1f}s "
        f"({fetcher.requests_made} requests, {fetcher.cache_hits} from cache)"
    )
    for path in written:
        say(f"  wrote {path}")
    if result.errors:
        say(f"  {len(result.errors)} page(s) failed; first error: {result.errors[0]}")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
