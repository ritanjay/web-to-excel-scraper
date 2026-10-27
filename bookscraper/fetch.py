"""Polite HTTP fetching: robots.txt, rate limiting, retries and an optional cache."""

from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests

log = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "bookscraper/1.0 (+https://github.com/ritanjay/web-to-excel-scraper; portfolio demo)"
)
RETRY_STATUS = {429, 500, 502, 503, 504}


class FetchError(RuntimeError):
    """Raised when a URL cannot be fetched after all retries."""


class BlockedByRobots(FetchError):
    """Raised when robots.txt disallows a URL."""


class Fetcher:
    """Fetches pages one at a time, politely.

    * Checks robots.txt once per host and refuses disallowed URLs.
    * Waits at least ``delay`` seconds between requests (or the site's
      Crawl-delay, whichever is larger).
    * Retries timeouts, connection errors, 429 and 5xx with exponential backoff.
    * Optionally caches pages on disk so re-runs do not hit the site again.
    """

    def __init__(
        self,
        delay: float = 0.5,
        retries: int = 3,
        timeout: float = 20.0,
        cache_dir: Optional[Path] = None,
        user_agent: str = DEFAULT_USER_AGENT,
        respect_robots: bool = True,
        session: Optional[requests.Session] = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.delay = delay
        self.retries = retries
        self.timeout = timeout
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.user_agent = user_agent
        self.respect_robots = respect_robots
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", user_agent)
        self._sleep = sleep
        self._clock = clock
        self._last_request: Optional[float] = None
        self._robots: dict[str, Optional[RobotFileParser]] = {}
        self.requests_made = 0
        self.cache_hits = 0

    # ------------------------------------------------------------------ robots
    def _robots_for(self, url: str) -> Optional[RobotFileParser]:
        parts = urlsplit(url)
        host = f"{parts.scheme}://{parts.netloc}"
        if host not in self._robots:
            parser = RobotFileParser()
            try:
                text = self._request(f"{host}/robots.txt", allow_404=True)
            except FetchError:
                text = ""
            parser.parse(text.splitlines())
            self._robots[host] = parser
            crawl_delay = parser.crawl_delay(self.user_agent)
            if crawl_delay and float(crawl_delay) > self.delay:
                log.info("robots.txt asks for a %ss crawl delay", crawl_delay)
                self.delay = float(crawl_delay)
        return self._robots[host]

    def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        robots = self._robots_for(url)
        return robots is None or robots.can_fetch(self.user_agent, url)

    # ------------------------------------------------------------------- cache
    def _cache_path(self, url: str) -> Optional[Path]:
        if not self.cache_dir:
            return None
        return self.cache_dir / (hashlib.sha1(url.encode()).hexdigest() + ".html")

    # ----------------------------------------------------------------- request
    def _wait_turn(self) -> None:
        if self._last_request is not None:
            elapsed = self._clock() - self._last_request
            if elapsed < self.delay:
                self._sleep(self.delay - elapsed)
        self._last_request = self._clock()

    def _request(self, url: str, allow_404: bool = False) -> str:
        last_error: Optional[str] = None
        for attempt in range(self.retries + 1):
            self._wait_turn()
            self.requests_made += 1
            try:
                resp = self.session.get(url, timeout=self.timeout)
            except requests.RequestException as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            else:
                if resp.status_code == 404 and allow_404:
                    return ""
                if resp.status_code in RETRY_STATUS:
                    last_error = f"HTTP {resp.status_code}"
                elif resp.status_code >= 400:
                    raise FetchError(f"{url}: HTTP {resp.status_code}")
                else:
                    # The site does not always declare a charset, and requests
                    # then falls back to ISO-8859-1 ("Â£" instead of "£").
                    return resp.content.decode("utf-8", errors="replace")
            if attempt < self.retries:
                backoff = min(30.0, 2.0**attempt)
                log.warning("%s failed (%s); retrying in %.0fs", url, last_error, backoff)
                self._sleep(backoff)
        raise FetchError(f"{url}: giving up after {self.retries + 1} attempts ({last_error})")

    def get(self, url: str) -> str:
        """Return the page body as text."""
        cache = self._cache_path(url)
        if cache and cache.exists():
            self.cache_hits += 1
            return cache.read_text(encoding="utf-8")
        if not self.allowed(url):
            raise BlockedByRobots(f"robots.txt disallows {url}")
        text = self._request(url)
        if cache:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(text, encoding="utf-8")
        return text
