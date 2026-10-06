"""Offline self-checks for the logic that has no server to catch it.

Run: python test_aion2.py

No network, no pytest, no fixtures on disk. The HTML below is a trimmed copy of
the real gaming.tools table, including the awkward bits: a name, a tooltipped
badge and a note sharing one cell, and a "-" where a number would be.
"""

import re
from io import BytesIO
from urllib.error import HTTPError

import aion2_api
from aion2_api import (
    Aion2ApiError,
    Aion2Board,
    Aion2Events,
    Aion2Servers,
    locale_for_board,
    strip_html,
)

# Two servers, the second carrying a badge + note and a "-" queue.
FIXTURE = """
<table>
<thead><tr>
  <th><span>Status</span></th><th><span>Server</span></th><th><span>Faction</span></th>
  <th><span>Region</span></th><th><span>Population</span></th><th><span>Current</span></th>
  <th><span>Max</span></th><th><span>Queue</span></th><th><span>24h</span></th>
</tr></thead>
<tbody>
<tr>
  <td><span>Online</span></td>
  <td><div><span>Israphel</span></div></td>
  <td><span>Asmodian</span></td>
  <td><span>Europe</span></td>
  <td><div><div style="width: 52%"></div></div></td>
  <td>3,929</td><td>7,500</td><td>-</td>
  <td><svg viewBox="0 0 120 34"><rect width="4" height="10"></rect></svg></td>
</tr>
<tr>
  <td><span>Online</span></td>
  <td><div><span>Israphel</span> <span title="Advanced Access">EA</span>
      <span>Character creation blocked</span></div></td>
  <td><span>Elyos</span></td>
  <td><span>NA East</span></td>
  <td><div><div style="width: 83%"></div></div></td>
  <td>6,401</td><td>7,700</td><td>120</td>
  <td><svg viewBox="0 0 120 34"><rect width="4" height="10"></rect></svg></td>
</tr>
</tbody>
</table>
"""


def fixture_servers():
    """Aion2Servers with its network call replaced by FIXTURE."""
    client = Aion2Servers()
    client.html = lambda: FIXTURE
    return client


def test_strip_html():
    assert strip_html("<p>Hello&nbsp;<b>Daevas</b></p><p>Second</p>") == "Hello Daevas\nSecond"
    assert strip_html(None) == ""
    assert strip_html("<script>evil()</script>Keep") == "Keep"
    # tags must never survive into the output
    assert "<" not in strip_html("<div data-x='1'>text</div>")


def test_server_table_parsing():
    rows = fixture_servers().servers()
    assert len(rows) == 2, rows

    first, second = rows
    assert first["name"] == "Israphel"
    assert first["region"] == "Europe"
    assert first["population_percent"] == 52.0
    assert first["current"] == 3929 and first["max"] == 7500
    assert first["queue"] is None, "a '-' cell must not become 0"
    assert first["badges"] == [] and first["note"] is None

    # The name/badge/note all live in one cell and must be separated.
    assert second["name"] == "Israphel", second
    assert second["badges"] == ["Advanced Access"]
    assert second["note"] == "Character creation blocked"
    assert second["faction"] == "Elyos"
    assert second["queue"] == 120
    assert second["current"] == 6401


def test_server_filters():
    client = fixture_servers()
    # same name in two regions -> both returned, which is why region exists
    assert len(client.servers(name="Israphel")) == 2
    assert len(client.servers(name="israphel")) == 2, "name match must be case-insensitive"
    assert len(client.servers(name="Israphel", region="NA East")) == 1
    assert len(client.servers(region="europe")) == 1, "region match must be case-insensitive"
    assert client.servers(name="Nobody") == []
    assert client.server("Nobody") is None
    assert client.server("Israphel", region="Europe")["region"] == "Europe"


def test_event_status():
    events = Aion2Events()
    assert events.event_status("2000-01-01T00:00:00Z", "2000-02-01T00:00:00Z") == "ENDED"
    assert events.event_status("2099-01-01T00:00:00Z", "2099-02-01T00:00:00Z") == "UPCOMING"
    assert events.event_status("2000-01-01T00:00:00Z", "2099-01-01T00:00:00Z") == "RUNNING"
    # malformed input must not raise
    assert events.event_status(None, None) == "RUNNING"
    assert events.event_status("not-a-date", "also-bad") == "RUNNING"


def test_event_tags_and_normalize():
    assert Aion2Events(country="US").tags == "MKT_PROMOTION,DOMAIN_AION2_GLOBAL,COUNTRY_US,"
    # already-prefixed input must not double up
    assert Aion2Events(country="COUNTRY_de").tags.endswith("COUNTRY_DE,")

    item = {
        "idx": 123,
        "itemKey": "KEY",
        "itemTitle": "  Spaced Title  ",
        "itemStart": "2000-01-01T00:00:00Z",
        "itemEnd": "2000-02-01T00:00:00Z",
        "marketingEntrySet": [
            {"entryDevice": "MOBILE", "entryUrl": "/mobile"},
            {"entryDevice": "NORMAL", "entryUrl": "/en-us/eventon/board/x/view?articleId=1"},
        ],
        "marketingItemAdditionSet": [
            {"additionType": "eventListImgUrl", "additionData": "https://img/big"},
            {"additionType": "eventListSmallImgUrl", "additionData": "https://img/small"},
        ],
        "marketingTagItemSet": [{"tagKey": "COUNTRY_US"}, {"tagKey": None}],
    }
    event = Aion2Events().normalize(item)
    assert event["id"] == "123", "ids must be strings, like notices"
    assert event["title"] == "Spaced Title"
    assert event["url"] == "https://aion2.plaync.com/en-us/eventon/board/x/view?articleId=1"
    assert event["image"] == "https://img/big" and event["image_small"] == "https://img/small"
    assert event["status"] == "ENDED"
    assert event["tags"] == ["COUNTRY_US"], "None tag keys must be dropped"


def test_board_referer_uses_resolved_locale():
    # Regression: the Referer used to interpolate the raw `locale` argument, which
    # is None by default, producing ".../None/board/notice/list".
    for alias, expected in [("notice_en", "en-us"), ("notice_de", "de-de")]:
        client = Aion2Board(alias)
        assert client.locale == expected
        assert f"/{expected}/" in client._headers["Referer"], client._headers["Referer"]
    assert "None" not in Aion2Board("notice_en")._headers["Referer"]


def test_board_cursor_paging():
    """Paging must follow the cursor, stop at `limit`, and not repeat items."""
    pages = {
        "0": {"contentList": [{"id": "a"}, {"id": "b"}], "hasMore": True},
        "b": {"contentList": [{"id": "c"}, {"id": "d"}], "hasMore": True},
        "d": {"contentList": [{"id": "e"}], "hasMore": False},
    }
    seen_cursors = []
    board = Aion2Board("notice_en")

    def fake_page(cursor="0", size=18, direction="BEFORE"):
        seen_cursors.append(cursor)
        return pages[cursor]

    board.page = fake_page
    assert [a["id"] for a in board.articles()] == ["a", "b", "c", "d", "e"]
    assert seen_cursors == ["0", "b", "d"], seen_cursors
    assert [a["id"] for a in board.articles(limit=3)] == ["a", "b", "c"]
    assert [a["id"] for a in board.articles(limit=1)] == ["a"]


def test_locale_mapping():
    assert locale_for_board("notice_pt") == "pt-br"
    assert locale_for_board("notice_xx") == "en-us", "unknown language falls back"


# --- politeness layer: no network, no real sleeping -------------------------


class FakeResponse:
    def __init__(self, body):
        self._body = body.encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeHTTPError(HTTPError):
    """An HTTPError whose Retry-After we control."""

    def __init__(self, code, retry_after=None):
        headers = {"Retry-After": retry_after} if retry_after is not None else {}
        super().__init__("http://x", code, "boom", headers, BytesIO(b"body"))


def with_fakes(responses):
    """Patch urlopen/sleep for the duration of a test.

    `responses` is consumed one per call; an int is treated as an HTTP error code.
    Returns (network_calls, sleep_lengths) lists.
    """
    calls, sleeps = [], []
    queue = list(responses)
    real_urlopen, real_sleep = aion2_api.urllib.request.urlopen, aion2_api.time.sleep

    def fake_urlopen(req, timeout=None):
        calls.append(req.full_url)
        item = queue.pop(0)
        if isinstance(item, int):
            raise FakeHTTPError(item)
        if isinstance(item, Exception):
            raise item
        return FakeResponse(item)

    aion2_api.urllib.request.urlopen = fake_urlopen
    aion2_api.time.sleep = lambda s: sleeps.append(s)
    return calls, sleeps, (real_urlopen, real_sleep)


def restore(originals):
    aion2_api.urllib.request.urlopen, aion2_api.time.sleep = originals


def test_cache_avoids_second_request():
    """The whole point: polling must not re-hit the server every time."""
    aion2_api.clear_cache()
    # Two queued responses: the second fetch is the one we force via clear_cache().
    calls, sleeps, originals = with_fakes(['{"a": 1}', '{"a": 1}'])
    try:
        first = aion2_api.get_json("https://example.test/x", {}, 5)
        second = aion2_api.get_json("https://example.test/x", {}, 5)
        assert first == second == {"a": 1}
        assert len(calls) == 1, f"cache miss - server hit {len(calls)} times"
        assert sleeps == [], "a cache hit must not wait on the throttle"
        aion2_api.clear_cache()
        aion2_api.get_json("https://example.test/x", {}, 5)
        assert len(calls) == 2, "clear_cache() must force a fresh request"
    finally:
        restore(originals)
        aion2_api.clear_cache()


def test_throttle_spaces_requests_per_host():
    aion2_api.clear_cache()
    calls, sleeps, originals = with_fakes(['{"a": 1}', '{"b": 2}', '{"c": 3}'])
    try:
        aion2_api.get_json("https://example.test/1", {}, 5)
        aion2_api.get_json("https://example.test/2", {}, 5)  # same host -> waits
        assert sleeps and sleeps[0] > 0, "second call to a host must be spaced out"
        aion2_api.get_json("https://other.test/1", {}, 5)  # different host -> no wait
        assert len(sleeps) == 1, f"throttle is per-host, got sleeps={sleeps}"
        assert len(calls) == 3
    finally:
        restore(originals)
        aion2_api.clear_cache()


def test_retry_honours_retry_after():
    aion2_api.clear_cache()
    # A 7s Retry-After can only come from the header - the throttle would be ~1s -
    # so sleeps[0] == 7 proves the server's own instruction was obeyed.
    calls, sleeps, originals = with_fakes([FakeHTTPError(429, "7"), '{"ok": 1}'])
    try:
        assert aion2_api.get_json("https://example.test/x", {}, 5) == {"ok": 1}
        assert len(calls) == 2, "a 429 must be retried"
        assert sleeps and sleeps[0] == 7.0, f"Retry-After: 7 not honoured, sleeps={sleeps}"
    finally:
        restore(originals)
        aion2_api.clear_cache()


def test_retry_stops_and_does_not_hammer():
    aion2_api.clear_cache()
    calls, sleeps, originals = with_fakes([503, 503, 503, 503])
    try:
        try:
            aion2_api.get_json("https://example.test/x", {}, 5)
            raise AssertionError("expected Aion2ApiError")
        except Aion2ApiError as exc:
            assert exc.status == 503
        assert len(calls) == aion2_api.MAX_RETRIES + 1, f"attempts={len(calls)}"
    finally:
        restore(originals)
        aion2_api.clear_cache()


def test_forbidden_is_not_retried():
    """A 403 is a deliberate block; retrying it makes things worse."""
    aion2_api.clear_cache()
    calls, sleeps, originals = with_fakes([403])
    try:
        try:
            aion2_api.get_json("https://example.test/x", {}, 5)
            raise AssertionError("expected Aion2ApiError")
        except Aion2ApiError as exc:
            assert exc.status == 403
        assert len(calls) == 1, "403 must not be retried"
        assert sleeps == [], "403 must not trigger a backoff"
    finally:
        restore(originals)
        aion2_api.clear_cache()


def test_retry_delay_bounds():
    assert aion2_api.retry_delay(FakeHTTPError(429, "12"), 0) == 12.0
    assert aion2_api.retry_delay(FakeHTTPError(429, "9999"), 0) == 60.0, "cap at a minute"
    assert aion2_api.retry_delay(FakeHTTPError(429, "0"), 0) == 1.0, "floor at a second"
    assert aion2_api.retry_delay(FakeHTTPError(429, "garbage"), 3) == 8.0, "else backoff"
    assert aion2_api.retry_delay(FakeHTTPError(503), 0) == 1.0


def test_user_agent_is_proper_and_honest():
    """A proper UA is product/version plus a comment - never a browser disguise."""
    ua = aion2_api.USER_AGENT
    assert "Mozilla" not in ua, f"do not impersonate a browser: {ua!r}"
    assert aion2_api.DEFAULT_HEADERS["User-Agent"] == ua
    # RFC 9110: product/version, then a parenthesised comment.
    assert re.match(r"^[a-z0-9-]+/\d+(\.\d+)* \([^)]*\)$", ua), ua

    # Each source says what it is, rather than sharing one vague string.
    from aion2_api import Aion2Board, Aion2Events, Aion2Servers

    agents = {
        "board": Aion2Board("notice_en")._headers["User-Agent"],
        "events": Aion2Events()._headers["User-Agent"],
        "servers": Aion2Servers()._headers["User-Agent"],
    }
    assert len(set(agents.values())) == 3, f"per-source UAs should differ: {agents}"
    assert "notices board" in agents["board"]
    assert "events" in agents["events"]
    assert "server status" in agents["servers"]
    for name, value in agents.items():
        assert "Mozilla" not in value, f"{name} impersonates a browser"
        assert re.match(r"^[a-z0-9-]+/\d+(\.\d+)* \([^)]*\)$", value), value
    # Each UA is paired with an Accept matching what that source returns.
    assert "json" in Aion2Board("notice_en")._headers["Accept"]
    assert "html" in Aion2Servers()._headers["Accept"]


def test_user_agent_contact_and_override():
    """AION2_CONTACT adds reachability; AION2_USER_AGENT replaces everything."""
    real_contact, real_override = aion2_api.CONTACT, aion2_api._UA_OVERRIDE
    try:
        aion2_api.CONTACT, aion2_api._UA_OVERRIDE = "https://example.com/me", ""
        with_contact = aion2_api.build_user_agent("notices board")
        assert with_contact == "aion2-api/1.0 (notices board; +https://example.com/me)"

        aion2_api.CONTACT = ""
        assert aion2_api.build_user_agent("notices board") == "aion2-api/1.0 (notices board)"

        aion2_api._UA_OVERRIDE = "custom/9.9 (mine)"
        assert aion2_api.build_user_agent("notices board") == "custom/9.9 (mine)"
        assert aion2_api.build_user_agent("anything") == "custom/9.9 (mine)"
    finally:
        aion2_api.CONTACT, aion2_api._UA_OVERRIDE = real_contact, real_override


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print(f"\n{len(tests)} checks passed (offline, no network)")


if __name__ == "__main__":
    main()
