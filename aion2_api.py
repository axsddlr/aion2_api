"""Unofficial client for the AION 2 (Global) board and event APIs.

Reverse-engineered from the XHR traffic of https://aion2.plaync.com/en-us/board/notice/list
and https://aion2.plaync.com/en-us/eventon

Discovered endpoints (host: https://api-global-community.plaync.com/aion2_global):

  GET /board/{boardAlias}                          board metadata (id, name, ACLs, categories)
  GET /board/{boardAlias}/noticeArticle            pinned / top notices
  GET /board/{boardAlias}/article/search/moreArticle
        ?isVote=true&moreSize=18&moreDirection=BEFORE&previousArticleId={cursor}
                                                   the actual paged list (cursor = previousArticleId)
  GET /board/{boardAlias}/article/{articleId}      single article incl. HTML body

Events live on a separate promotion backend (host: https://promotion.plaync.com/{locale}):

  GET /eventon/item?tag={tags}&status={status}&pageSize={n}&page={p}
                                                   the event list (page-numbered)

No cookies, no auth, no API key are required for reads.

Requires only the Python standard library (3.9+).
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Dict, Iterator, List, Optional, Tuple

API_BASE = "https://api-global-community.plaync.com/aion2_global"
WEB_BASE = "https://aion2.plaync.com"

DEFAULT_BOARD = "notice_en"
# The board alias encodes the language; these are the ones AION 2 Global ships.
GLOBAL_BOARDS = ["notice_en", "notice_de", "notice_fr", "notice_es", "notice_pt"]
# Language suffix -> the locale the public site uses in its URLs.
LOCALE_BY_LANG = {
    "en": "en-us",
    "de": "de-de",
    "fr": "fr-fr",
    "es": "es-es",
    "pt": "pt-br",
    "ja": "ja-jp",
}


def locale_for_board(board_alias: str, default: str = "en-us") -> str:
    """Map a board alias (e.g. 'notice_de') to its site locale ('de-de')."""
    return LOCALE_BY_LANG.get(board_alias.rsplit("_", 1)[-1].lower(), default)


# --- user agents ------------------------------------------------------------
# User-Agent per RFC 9110: `product/version` followed by a comment. What makes a
# bot's UA *proper* is contact details in that comment, so the operator of a site
# you read can reach you. Set AION2_CONTACT to a URL or email and it is included;
# AION2_USER_AGENT replaces the whole string for every source if you need that.
APP_NAME = "aion2-api"
APP_VERSION = "1.0"
CONTACT = os.environ.get("AION2_CONTACT", "").strip()
_UA_OVERRIDE = os.environ.get("AION2_USER_AGENT", "").strip()


def build_user_agent(purpose: str) -> str:
    """A proper User-Agent naming what is calling and how to contact the caller."""
    if _UA_OVERRIDE:
        return _UA_OVERRIDE
    comment = f"{purpose}; +{CONTACT}" if CONTACT else purpose
    return f"{APP_NAME}/{APP_VERSION} ({comment})"


USER_AGENT = build_user_agent("AION 2 notices reader")

# --- politeness -------------------------------------------------------------
# We are a guest on someone else's server. These cost nothing, and they - not
# disguises - are what actually keeps you from being rate-limited.
MIN_REQUEST_INTERVAL = 1.0  # seconds between requests to the same host
CACHE_TTL = 60.0  # reuse a fetched response for this long instead of re-fetching
MAX_RETRIES = 2  # only for 429/503, which explicitly mean "come back later"
MAX_CACHE_ENTRIES = 512  # crude ceiling: the cache is dropped wholesale when hit

DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

_TAG_RE = re.compile(r"<[^>]+>")
_BR_RE = re.compile(r"<\s*br\s*/?\s*>|</\s*(?:p|div|li|tr)\s*>", re.I)
# Invisible characters the notice HTML actually contains: zero-width spaces and a
# non-breaking space used for indentation. They look like nothing but break naive
# string handling (and console output), so drop/normalise them.
_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]")


class Aion2ApiError(RuntimeError):
    """Raised when the API answers with a non-2xx status."""

    def __init__(self, status: int, url: str, body: str):
        super().__init__(f"HTTP {status} for {url}: {body[:300]}")
        self.status = status
        self.url = url
        self.body = body


def strip_html(fragment: Optional[str]) -> str:
    """Turn an article HTML body into readable plain text."""
    if not fragment:
        return ""
    text = _BR_RE.sub("\n", fragment)
    text = re.sub(r"<script.*?</script>|<style.*?</style>", "", text, flags=re.S | re.I)
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    text = _ZERO_WIDTH_RE.sub("", text).replace("\xa0", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# --- the single place every request goes through ----------------------------

_last_request: Dict[str, float] = {}
_response_cache: Dict[str, Tuple[float, str]] = {}


def clear_cache() -> None:
    """Forget cached responses and the throttle clock."""
    _last_request.clear()
    _response_cache.clear()


def _throttle(url: str) -> None:
    """Wait if we called this host too recently."""
    host = urllib.parse.urlsplit(url).netloc
    waited = time.monotonic() - _last_request.get(host, 0.0)
    if waited < MIN_REQUEST_INTERVAL:
        time.sleep(MIN_REQUEST_INTERVAL - waited)
    _last_request[host] = time.monotonic()


def retry_delay(exc: urllib.error.HTTPError, attempt: int) -> float:
    """How long to wait before retrying: the server's Retry-After, else backoff.

    Clamped so we neither hammer (floor 1s) nor hang all day (ceiling 60s).
    """
    retry_after = exc.headers.get("Retry-After") if exc.headers else None
    try:
        delay = float(retry_after)
    except (TypeError, ValueError):
        delay = 2.0**attempt
    return min(max(delay, 1.0), 60.0)


def _fetch(url: str, headers: Dict[str, str], timeout: float) -> str:
    """GET a URL as text, politely: spaced out, cached, and backed off on 429/503."""
    now = time.monotonic()
    cached = _response_cache.get(url)
    if cached and now - cached[0] < CACHE_TTL:
        return cached[1]

    attempt = 0
    while True:
        _throttle(url)
        try:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
            if len(_response_cache) >= MAX_CACHE_ENTRIES:
                _response_cache.clear()  # ponytail: crude bound, LRU if it ever matters
            _response_cache[url] = (time.monotonic(), raw)
            return raw
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            # 429/503 mean "come back later", so do exactly that. A 403 is a
            # deliberate block - retrying it just makes things worse.
            if exc.code in (429, 503) and attempt < MAX_RETRIES:
                time.sleep(retry_delay(exc, attempt))
                attempt += 1
                continue
            raise Aion2ApiError(exc.code, url, body) from exc
        except urllib.error.URLError as exc:
            raise Aion2ApiError(0, url, str(exc.reason)) from exc


def get_json(url: str, headers: Dict[str, str], timeout: float, params: Optional[Dict[str, Any]] = None) -> Any:
    """GET a URL and decode the JSON body."""
    if params:
        clean = {k: v for k, v in params.items() if v is not None}
        url = f"{url}?{urllib.parse.urlencode(clean)}"
    raw = _fetch(url, headers, timeout)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise Aion2ApiError(0, url, f"not JSON: {raw[:300]}") from exc


def get_text(url: str, headers: Dict[str, str], timeout: float) -> str:
    """GET a URL and return the body as text (for sources that are not JSON)."""
    return _fetch(url, headers, timeout)


class Aion2Board:
    """Read-only client for one board (default: the English notice board)."""

    def __init__(
        self,
        board_alias: str = DEFAULT_BOARD,
        *,
        locale: Optional[str] = None,
        timeout: float = 20.0,
        headers: Optional[Dict[str, str]] = None,
    ):
        self.board_alias = board_alias
        self.locale = locale or locale_for_board(board_alias)
        self.timeout = timeout
        self.base = API_BASE
        self._headers = dict(DEFAULT_HEADERS)
        self._headers["User-Agent"] = build_user_agent("notices board")
        section = board_alias.split("_")[0]
        self._headers["Referer"] = f"{WEB_BASE}/{self.locale}/board/{section}/list"
        if headers:
            self._headers.update(headers)

    # ---------------------------------------------------------------- transport

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        return get_json(f"{self.base}/{path.lstrip('/')}", self._headers, self.timeout, params)

    # ------------------------------------------------------------------ endpoints

    def board_info(self) -> Dict[str, Any]:
        """Board metadata: id, name, type, categories, permissions."""
        return self._get(f"/board/{self.board_alias}")

    def pinned(self) -> List[Dict[str, Any]]:
        """Pinned / top notices (always shown first on the site)."""
        data = self._get(f"/board/{self.board_alias}/noticeArticle")
        # Each entry is {"articleMeta": {...article fields...}, "articleContent": {...}}
        return [(entry.get("articleMeta") or entry) for entry in (data.get("noticesList") or [])]

    def page(self, cursor: str = "0", size: int = 18, direction: str = "BEFORE") -> Dict[str, Any]:
        """One raw page of the article list. `cursor` is a previousArticleId ('0' = newest)."""
        return self._get(
            f"/board/{self.board_alias}/article/search/moreArticle",
            {
                "isVote": "true",
                "moreSize": size,
                "moreDirection": direction,
                "previousArticleId": cursor,
            },
        )

    def articles(self, limit: Optional[int] = None, size: int = 18) -> Iterator[Dict[str, Any]]:
        """Yield articles newest-first, following the cursor until `limit` or the last page."""
        cursor, yielded = "0", 0
        while True:
            data = self.page(cursor=cursor, size=size)
            items = data.get("contentList") or []
            if not items:
                return
            for item in items:
                yield item
                yielded += 1
                if limit is not None and yielded >= limit:
                    return
            if not data.get("hasMore"):
                return
            cursor = items[-1]["id"]

    def article(self, article_id: str) -> Dict[str, Any]:
        """Full article, including `content.content` (HTML body) and prev/next links."""
        return self._get(f"/board/{self.board_alias}/article/{article_id}")

    def article_url(self, article_id: str) -> str:
        """Human-facing URL for an article."""
        section = self.board_alias.split("_")[0]
        return f"{WEB_BASE}/{self.locale}/board/{section}/view?articleId={article_id}"

    # -------------------------------------------------------------- normalisation

    def normalize(self, item: Dict[str, Any], body: Optional[str] = None) -> Dict[str, Any]:
        """Flatten a raw list/article entry into a stable, scraping-friendly dict."""
        ts = item.get("timestamps") or {}
        reactions = item.get("reactions") or {}
        writer = ((item.get("writer") or {}).get("loginUser")) or {}
        return {
            "id": item.get("id"),
            "title": (item.get("title") or "").strip(),
            "summary": strip_html(item.get("summary")),
            "url": self.article_url(item.get("id", "")),
            "posted_at": ts.get("postedAt"),
            "updated_at": ts.get("updatedAt"),
            "posted_epoch": ts.get("postedEpoch"),
            "writer": writer.get("name"),
            "is_admin": bool(writer.get("admin")),
            "view_count": reactions.get("viewCount", 0),
            "like_count": reactions.get("likeCount", 0),
            "comment_count": reactions.get("commentCount", 0),
            "has_attachments": bool(item.get("hasAttachments")),
            "thumbnails": item.get("thumbnailUrlList") or [],
            "tags": item.get("metaTags") or [],
            "body": strip_html(body) if body is not None else None,
        }

    def iter_notices(self, limit: Optional[int] = None, size: int = 18) -> Iterator[Dict[str, Any]]:
        """Normalized articles, newest-first (pinned notices are NOT included here)."""
        for item in self.articles(limit=limit, size=size):
            yield self.normalize(item)

    def get_notice(self, article_id: str) -> Dict[str, Any]:
        """Normalized single article with its full plain-text body.

        The detail response nests things: `article.contentMeta` holds the article
        metadata (same shape as a list entry) while `article.content.content`
        holds the HTML body.
        """
        data = self.article(article_id)
        article = data.get("article") or {}
        if not article.get("contentMeta"):
            # The API answers 200 with an empty envelope for unknown ids.
            raise Aion2ApiError(404, self.article_url(article_id), "article not found")
        meta = dict(article.get("contentMeta") or {})
        body_container = article.get("content") or {}
        meta.setdefault("id", article_id)

        result = self.normalize(meta, body=body_container.get("content"))
        # Shape: {"files": [{fileUrl, fileName, mimeType, fileSize, ...}], "thumbnailUrl": str}
        result["attachments"] = body_container.get("attachments") or {}
        if body_container.get("tags"):
            result["tags"] = body_container["tags"]
        prev_next = data.get("prevNextArticle") or {}
        result["prev_id"] = (prev_next.get("previousArticle") or {}).get("id")
        result["next_id"] = (prev_next.get("nextArticle") or {}).get("id")
        return result


# ------------------------------------------------------------------- events (eventon)

# The /eventon page is a different system from the boards: a marketing/promotion
# backend with page-numbered paging rather than the board API's cursor.
PROMOTION_BASE = "https://promotion.plaync.com"

# Valid values the API accepts for `status` (others answer HTTP 400).
EVENT_STATUSES = ["RUNNING", "ALL", "CLOSED"]


class Aion2Events:
    """Read-only client for the /eventon event list.

    Discovered endpoints (host: https://promotion.plaync.com/{locale}):

      GET /eventon/item?tag={tags}&status={status}&pageSize={n}&page={p}
              the event list; a Spring page: {content: [...], totalPages, last, ...}
      GET /eventon/on                             the ON_* promotion groups
      GET /eventon/domain/tag                     tag definitions

    `tag` is required - omitting it returns HTTP 400. `status=RUNNING` and
    `status=ALL` currently return the same set; `CLOSED` returns ended events.
    """

    def __init__(
        self,
        locale: str = "en-us",
        *,
        domain: str = "DOMAIN_AION2_GLOBAL",
        country: str = "US",
        status: str = "RUNNING",
        timeout: float = 20.0,
        headers: Optional[Dict[str, str]] = None,
    ):
        self.locale = locale
        self.domain = domain
        self.country = country
        self.status = status
        self.timeout = timeout
        self.base = f"{PROMOTION_BASE}/{locale}"
        self._headers = dict(DEFAULT_HEADERS)
        self._headers["User-Agent"] = build_user_agent("events")
        self._headers["Referer"] = f"{WEB_BASE}/{locale}/eventon"
        if headers:
            self._headers.update(headers)

    @property
    def tags(self) -> str:
        """The tag filter the site itself sends. The trailing comma is required.

        Note the country is a tag *key* ('COUNTRY_US'), not a bare code - passing
        'US' produces a filter that matches nothing and returns an empty list.
        """
        country = self.country.upper()
        if not country.startswith("COUNTRY_"):
            country = f"COUNTRY_{country}"
        return f"MKT_PROMOTION,{self.domain},{country},"

    def page(self, page: int = 1, page_size: int = 12, status: Optional[str] = None) -> Dict[str, Any]:
        """One raw page of events. `page` is 1-based."""
        if (status or self.status) not in EVENT_STATUSES:
            raise ValueError(f"status must be one of {EVENT_STATUSES}, got {status or self.status!r}")
        return get_json(
            f"{self.base}/eventon/item",
            self._headers,
            self.timeout,
            {
                "tag": self.tags,
                "status": status or self.status,
                "pageSize": page_size,
                "page": page,
            },
        )

    def events(
        self,
        limit: Optional[int] = None,
        page_size: int = 12,
        status: Optional[str] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Yield raw event items, following pages until `limit` or the last page."""
        page, yielded = 1, 0
        while True:
            data = self.page(page=page, page_size=page_size, status=status)
            items = data.get("content") or []
            if not items:
                return
            for item in items:
                yield item
                yielded += 1
                if limit is not None and yielded >= limit:
                    return
            if data.get("last") or page >= (data.get("totalPages") or 1):
                return
            page += 1

    def event_status(self, starts_at: Optional[str], ends_at: Optional[str]) -> str:
        """Derive UPCOMING / RUNNING / ENDED from the event's date window."""
        now = datetime.now(timezone.utc)

        def parse(value: Optional[str]) -> Optional[datetime]:
            if not value:
                return None
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None

        start, end = parse(starts_at), parse(ends_at)
        if start and now < start:
            return "UPCOMING"
        if end and now > end:
            return "ENDED"
        return "RUNNING"

    def normalize(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Flatten a raw event item into a stable dict."""
        additions = {
            a.get("additionType"): a.get("additionData")
            for a in (item.get("marketingItemAdditionSet") or [])
        }
        entries = item.get("marketingEntrySet") or []
        # Prefer the desktop entry; MOBILE ones point at the same place.
        link = next((e for e in entries if e.get("entryDevice") == "NORMAL"), entries[0] if entries else {})
        url = link.get("entryUrl") or None
        if url and url.startswith("/"):
            url = f"{WEB_BASE}{url}"
        starts_at, ends_at = item.get("itemStart"), item.get("itemEnd")
        idx = item.get("idx")
        return {
            "id": str(idx) if idx is not None else None,
            "key": item.get("itemKey"),
            "title": (item.get("itemTitle") or "").strip(),
            "url": url,
            "image": additions.get("eventListImgUrl"),
            "image_small": additions.get("eventListSmallImgUrl"),
            "starts_at": starts_at,
            "ends_at": ends_at,
            "status": self.event_status(starts_at, ends_at),
            "tags": [t.get("tagKey") for t in (item.get("marketingTagItemSet") or []) if t.get("tagKey")],
        }

    def iter_events(
        self,
        limit: Optional[int] = None,
        page_size: int = 12,
        status: Optional[str] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Normalized events."""
        for item in self.events(limit=limit, page_size=page_size, status=status):
            yield self.normalize(item)


# --------------------------------------------------------- servers (gaming.tools)

# Third-party community site - NOT an NCSOFT endpoint. It has no JSON API, so the
# server table is parsed out of the page's HTML. robots.txt allows this path.
GAMING_TOOLS_BASE = "https://aion2.gaming.tools"
SERVER_STATUS_PATH = "/server-status"


def _cell_text(cell: Dict[str, Any]) -> str:
    return " ".join(f["text"] for f in cell["frags"]).strip()


def _to_int(text: str) -> Optional[int]:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else None


class _ServerTableParser(HTMLParser):
    """Pull the server table out of the gaming.tools page.

    The page is server-rendered with no JSON behind it, so the only way in is the
    markup. Text is kept as fragments because a cell can mix a name, a badge and a
    note ("Israphel", "EA" tooltipped "Advanced Access", "Character creation blocked").
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.headers: List[Dict[str, Any]] = []
        self.rows: List[List[Dict[str, Any]]] = []
        self._in_cell: Optional[str] = None
        self._frags: List[Dict[str, Any]] = []
        self._spans: List[Optional[str]] = []
        self._width: Optional[float] = None
        self._row: List[Dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: List[Any]) -> None:
        a = dict(attrs)
        if tag in ("th", "td"):
            self._in_cell = tag
            self._frags, self._spans, self._width = [], [], None
        elif self._in_cell:
            if tag == "span":
                self._spans.append(a.get("title"))
            # The population bar is an inline width percentage.
            m = re.search(r"width:\s*([\d.]+)%", a.get("style", ""))
            if m:
                self._width = float(m.group(1))

    def handle_data(self, data: str) -> None:
        if self._in_cell and data.strip():
            self._frags.append(
                {"text": data.strip(), "title": self._spans[-1] if self._spans else None}
            )

    def handle_endtag(self, tag: str) -> None:
        if tag == "span" and self._spans:
            self._spans.pop()
        elif tag in ("th", "td") and self._in_cell:
            cell = {"frags": self._frags, "width": self._width}
            (self.headers if tag == "th" else self._row).append(cell)
            self._in_cell = None
        elif tag == "tr" and self._row:
            self.rows.append(self._row)
            self._row = []


class Aion2Servers:
    """Server population, read from the community site aion2.gaming.tools.

    Unlike the other clients this one parses HTML, because the page has no JSON
    API behind it. Treat it as the most fragile source here: the site is a fan
    project (not NCSOFT) and sits behind Cloudflare.
    """

    def __init__(
        self,
        locale: str = "",
        *,
        timeout: float = 25.0,
        headers: Optional[Dict[str, str]] = None,
    ):
        self.locale = locale
        prefix = f"/{locale}" if locale else ""
        self.url = f"{GAMING_TOOLS_BASE}{prefix}{SERVER_STATUS_PATH}"
        self.timeout = timeout
        self._headers = {
            "User-Agent": build_user_agent("server status"),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        if headers:
            self._headers.update(headers)

    def html(self) -> str:
        """The raw page."""
        return get_text(self.url, self._headers, self.timeout)

    def servers(
        self,
        name: Optional[str] = None,
        region: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """All servers, optionally filtered.

        A server name on its own is ambiguous - the same name exists in every
        region, so pass `region` too when you want exactly one.
        """
        parser = _ServerTableParser()
        parser.feed(self.html())
        if not parser.rows:
            raise Aion2ApiError(0, self.url, "no server table found on the page")

        columns = [_cell_text(c) for c in parser.headers]
        try:
            idx = {c: i for i, c in enumerate(columns)}
            i_name, i_status = idx["Server"], idx["Status"]
            i_faction, i_region = idx["Faction"], idx["Region"]
            i_pop, i_cur, i_max, i_queue = (
                idx["Population"],
                idx["Current"],
                idx["Max"],
                idx["Queue"],
            )
        except KeyError as exc:
            raise Aion2ApiError(0, self.url, f"unexpected table columns: {columns}") from exc

        out: List[Dict[str, Any]] = []
        for row in parser.rows:
            if len(row) <= max(idx.values()):
                continue

            frags = row[i_name]["frags"]
            plain = [f for f in frags if not f["title"]]
            server_name = plain[0]["text"] if plain else None
            if not server_name:
                continue
            note = " ".join(f["text"] for f in plain[1:]).strip() or None
            record = {
                "name": server_name,
                "status": _cell_text(row[i_status]),
                "faction": _cell_text(row[i_faction]),
                "region": _cell_text(row[i_region]),
                "population_percent": row[i_pop]["width"],
                "current": _to_int(_cell_text(row[i_cur])),
                "max": _to_int(_cell_text(row[i_max])),
                "queue": _to_int(_cell_text(row[i_queue])),
                "badges": [f["title"] for f in frags if f["title"]],
                "note": note,
            }
            if name and record["name"].lower() != name.lower():
                continue
            if region and region.lower() not in (record["region"] or "").lower():
                continue
            out.append(record)
        return out

    def server(self, name: str, region: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """One server by name (and region, if the name is ambiguous)."""
        matches = self.servers(name=name, region=region)
        return matches[0] if matches else None


# --------------------------------------------------------------------------- CLI


def _print_table(rows: List[Dict[str, Any]]) -> None:
    for r in rows:
        date = (r.get("posted_at") or "")[:10]
        print(f"{date}  {r.get('id')}  {r.get('title')[:80]}")


def _print_events(rows: List[Dict[str, Any]]) -> None:
    for r in rows:
        window = f"{(r.get('starts_at') or '')[:10]} -> {(r.get('ends_at') or '')[:10]}"
        print(f"{window}  {r.get('status',''):8}  {(r.get('title') or '')[:70]}")
        if r.get("url"):
            print(f"            {r['url']}")


def _print_servers(rows: List[Dict[str, Any]]) -> None:
    for r in rows:
        pct = r.get("population_percent")
        bar = f"{pct:g}%" if pct is not None else "-"
        cur = r.get("current")
        cap = r.get("max")
        queue = r.get("queue")
        line = (
            f"{r.get('name',''):14} {r.get('region',''):8} {r.get('faction',''):9} "
            f"{bar:>5}  {cur if cur is not None else '-':>6}"
            f" / {cap if cap is not None else '-':<6}"
        )
        if queue:
            line += f"  queue {queue}"
        print(line)
        if r.get("note"):
            print(f"{'':14} {r['note']}")


def main(argv: Optional[List[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(
        prog="aion2_api",
        description="Scrape the AION 2 Global board and event APIs (no key needed).",
    )
    p.add_argument("--board", default=DEFAULT_BOARD, help=f"board alias (default {DEFAULT_BOARD})")
    p.add_argument("--locale", default=None, help="override the locale used for the public web URL")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("board", help="show board metadata")
    s = sub.add_parser("pinned", help="show pinned notices")
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("list", help="list articles (newest first)")
    s.add_argument("-n", "--limit", type=int, default=10)
    s.add_argument("--size", type=int, default=18, help="page size requested per API call")
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("view", help="show one article and its body")
    s.add_argument("article_id")
    s.add_argument("--html", action="store_true", help="print raw HTML instead of plain text")
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("events", help="list /eventon events")
    s.add_argument("-n", "--limit", type=int, default=10)
    s.add_argument("--status", default="RUNNING", choices=EVENT_STATUSES)
    s.add_argument("--country", default="US", help="country tag, e.g. US, DE, FR")
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("servers", help="server population from aion2.gaming.tools")
    s.add_argument("--name", help="server name, e.g. Israphel (may exist in several regions)")
    s.add_argument("--region", help="region filter, e.g. 'NA East', Europe, Asia")
    s.add_argument("--json", action="store_true")

    args = p.parse_args(argv)

    try:
        if args.cmd == "servers":
            items = Aion2Servers().servers(name=args.name, region=args.region)
            if args.json:
                print(json.dumps(items, ensure_ascii=False, indent=2))
            else:
                _print_servers(items)
            return 0

        if args.cmd == "events":
            events = Aion2Events(
                args.locale or "en-us", country=args.country, status=args.status
            )
            items = list(events.iter_events(limit=args.limit))
            if args.json:
                print(json.dumps(items, ensure_ascii=False, indent=2))
            else:
                _print_events(items)
            return 0

        board = Aion2Board(args.board, locale=args.locale)
        if args.cmd == "board":
            print(json.dumps(board.board_info(), ensure_ascii=False, indent=2))
        elif args.cmd == "pinned":
            items = [board.normalize(i) for i in board.pinned()]
            print(json.dumps(items, ensure_ascii=False, indent=2) if args.json else "")
            if not args.json:
                _print_table(items)
        elif args.cmd == "list":
            items = list(board.iter_notices(limit=args.limit, size=args.size))
            if args.json:
                print(json.dumps(items, ensure_ascii=False, indent=2))
            else:
                _print_table(items)
        elif args.cmd == "view":
            data = board.article(args.article_id)
            raw = ((data.get("article") or {}).get("content") or {}).get("content", "")
            if args.json:
                print(json.dumps(board.get_notice(args.article_id), ensure_ascii=False, indent=2))
            elif args.html:
                print(raw)
            else:
                n = board.get_notice(args.article_id)
                print(f"{n['title']}\n{n['url']}\nposted: {n['posted_at']}  views: {n['view_count']}\n")
                print(n["body"])
    except Aion2ApiError as exc:
        print(f"API error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
