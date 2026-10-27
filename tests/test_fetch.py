import pytest
import requests

from bookscraper.fetch import BlockedByRobots, Fetcher, FetchError


class Resp:
    def __init__(self, status=200, body=b""):
        self.status_code = status
        self.content = body if isinstance(body, bytes) else body.encode("utf-8")


class FakeSession:
    """Returns queued responses per URL; an Exception in the queue is raised."""

    def __init__(self, routes):
        self.routes = {k: list(v) for k, v in routes.items()}
        self.headers = {}
        self.calls = []

    def get(self, url, timeout=None):
        self.calls.append(url)
        queue = self.routes.get(url)
        if not queue:
            return Resp(404)
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        return item


class Clock:
    def __init__(self):
        self.t = 0.0
        self.sleeps = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(round(s, 3))
        self.t += s


def make(routes, **kw):
    clock = Clock()
    f = Fetcher(session=FakeSession(routes), sleep=clock.sleep, clock=clock.now, **kw)
    return f, clock


ROBOTS = "https://example.com/robots.txt"


def test_decodes_utf8_even_without_charset():
    f, _ = make({"https://example.com/a": [Resp(200, "£51.77".encode())]}, delay=0)
    assert f.get("https://example.com/a") == "£51.77"


def test_robots_disallow_is_respected():
    routes = {
        ROBOTS: [Resp(200, "User-agent: *\nDisallow: /private/\n")],
        "https://example.com/ok": [Resp(200, "fine")],
    }
    f, _ = make(routes, delay=0)
    assert f.get("https://example.com/ok") == "fine"
    with pytest.raises(BlockedByRobots):
        f.get("https://example.com/private/x")
    # robots.txt is fetched once per host
    assert f.session.calls.count(ROBOTS) == 1


def test_robots_can_be_disabled():
    routes = {
        ROBOTS: [Resp(200, "User-agent: *\nDisallow: /\n")],
        "https://example.com/x": [Resp(200, "ok")],
    }
    f, _ = make(routes, delay=0, respect_robots=False)
    assert f.get("https://example.com/x") == "ok"


def test_crawl_delay_from_robots_is_honoured():
    routes = {
        ROBOTS: [Resp(200, "User-agent: *\nCrawl-delay: 2\n")],
        "https://example.com/a": [Resp(200, "a")],
        "https://example.com/b": [Resp(200, "b")],
    }
    f, clock = make(routes, delay=0.1)
    f.get("https://example.com/a")
    f.get("https://example.com/b")
    assert f.delay == 2.0
    assert 2.0 in clock.sleeps


def test_rate_limit_between_requests():
    routes = {"https://example.com/1": [Resp(200, "1")], "https://example.com/2": [Resp(200, "2")]}
    f, clock = make(routes, delay=0.5, respect_robots=False)
    f.get("https://example.com/1")
    f.get("https://example.com/2")
    assert clock.sleeps == [0.5]


def test_retries_transient_errors_then_succeeds():
    url = "https://example.com/flaky"
    routes = {url: [Resp(503), requests.ConnectionError("reset"), Resp(200, "ok")]}
    f, clock = make(routes, delay=0, retries=3, respect_robots=False)
    assert f.get(url) == "ok"
    assert f.requests_made == 3
    assert clock.sleeps == [1.0, 2.0]  # exponential backoff


def test_gives_up_after_retries():
    url = "https://example.com/down"
    f, _ = make({url: [Resp(500)]}, delay=0, retries=2, respect_robots=False)
    with pytest.raises(FetchError, match="3 attempts"):
        f.get(url)


def test_client_errors_are_not_retried():
    url = "https://example.com/missing"
    f, _ = make({}, delay=0, retries=3, respect_robots=False)
    with pytest.raises(FetchError, match="404"):
        f.get(url)
    assert f.requests_made == 1


def test_cache_avoids_second_request(tmp_path):
    url = "https://example.com/page"
    f, _ = make(
        {url: [Resp(200, "cached body")]}, delay=0, respect_robots=False, cache_dir=tmp_path
    )
    assert f.get(url) == "cached body"
    f2, _ = make({}, delay=0, respect_robots=False, cache_dir=tmp_path)
    assert f2.get(url) == "cached body"
    assert f2.requests_made == 0 and f2.cache_hits == 1
