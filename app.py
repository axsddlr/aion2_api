"""FastAPI service exposing the reverse-engineered AION 2 (Global) APIs.

    GET /notices              newest notices (no arguments needed)
    GET /notices/{id}         one notice, with its full text
    GET /events               current events from /eventon
    GET /servers              server population (third-party source)
    GET /servers/roster       the server list itself (first-party, no population)
    GET /v2/servers           server status with ids, flags and 24h population (third-party)
    GET /characters/search    find characters by name
    GET /characters/{name}    stats, gear, skills (?server= when the name is ambiguous)
    GET /characters/{name}/daevanion[/{board}]   Daevanion boards

Run:
    uvicorn app:app --reload
    python app.py

The underlying client (`aion2_api.py`) uses blocking urllib, so every route is a
plain `def` — FastAPI runs those in a threadpool instead of blocking the loop.
Upstream failures are mapped to HTTP statuses in one place, see `api_error` below.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from aion2_api import (
    APP_VERSION,
    DEFAULT_BOARD,
    GLOBAL_BOARDS,
    Aion2ApiError,
    Aion2Board,
    Aion2Events,
    Aion2Servers,
    Aion2ServersV2,
    CharacterLookupError,
    character_endpoint,
    find_board,
    get_character,
    get_daevanion_board,
    resolve_character,
    search_characters,
    server_list,
)

app = FastAPI(
    title="AION 2 Notices, Events, Servers & Characters",
    version=APP_VERSION,
    description=(
        "Unofficial read-only JSON API for AION 2.\n\n"
        "* **GET /notices** — newest notices, or `?board=notice_de` for another language\n"
        "* **GET /notices/{id}** — one notice, including its full text\n"
        "* **GET /events** — current in-game events\n"
        "* **GET /servers** — how full each server is\n"
        "* **GET /v2/servers** — the same as a percentage plus `normal` / `busy` / `full`, "
        "status flags and the last 24 hours\n"
        "* **GET /characters/{name}** — a character's stats, gear and skills\n"
        "* **GET /characters/{name}/daevanion** — their Daevanion boards\n\n"
        "No API key or login is needed; the data is public."
    ),
)


# --------------------------------------------------------------------- schemas


class Notice(BaseModel):
    id: str = Field(description="Article id, use it with /notices/{id}")
    title: str
    summary: str = ""
    url: str = Field(description="Human-readable page on aion2.plaync.com")
    posted_at: Optional[str] = None
    updated_at: Optional[str] = None
    posted_epoch: Optional[int] = None
    writer: Optional[str] = None
    is_admin: bool = False
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    has_attachments: bool = False
    thumbnails: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)


class Attachment(BaseModel):
    fileId: Optional[str] = None
    fileName: Optional[str] = None
    fileUrl: Optional[str] = None
    mimeType: Optional[str] = None
    fileSize: Optional[int] = None
    thumbnailUrl: Optional[str] = None


class Attachments(BaseModel):
    files: List[Attachment] = Field(default_factory=list)
    thumbnailUrl: str = ""


class NoticeDetail(Notice):
    body: Optional[str] = Field(None, description="Notice text, HTML stripped")
    attachments: Attachments = Field(default_factory=Attachments)
    prev_id: Optional[str] = Field(None, description="Previous (newer) notice id")
    next_id: Optional[str] = Field(None, description="Next (older) notice id")


class Event(BaseModel):
    id: Optional[str] = None
    key: Optional[str] = Field(None, description="Stable event key")
    title: str = ""
    url: Optional[str] = Field(None, description="Event page on aion2.plaync.com")
    image: Optional[str] = Field(None, description="Banner image URL")
    image_small: Optional[str] = Field(None, description="Smaller banner variant")
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None
    status: Optional[str] = Field(None, description="RUNNING, UPCOMING or ENDED")
    tags: List[str] = Field(default_factory=list)


class ServerStatus(BaseModel):
    name: str
    status: Optional[str] = Field(None, description="Online or Offline")
    faction: Optional[str] = None
    region: Optional[str] = Field(None, description="Europe, NA East, NA West, Asia or SA")
    population_percent: Optional[float] = Field(None, description="How full the server is")
    current: Optional[int] = Field(None, description="Players online now")
    max: Optional[int] = None
    queue: Optional[int] = None
    badges: List[str] = Field(default_factory=list)
    note: Optional[str] = None


class PopulationPoint(BaseModel):
    time: str = Field(description="Start of the hour, ISO 8601 UTC")
    population_percent: Optional[float] = Field(None, description="How full the server was, 0-100")


class ServerStatusV2(BaseModel):
    id: Optional[int] = Field(None, description="NCSOFT server id, as in /servers/roster")
    name: str
    region: str = Field(description="nae, naw, eu, la or as")
    faction: Optional[str] = None
    online: Optional[bool] = None
    maintenance: Optional[bool] = None
    creation_blocked: Optional[bool] = None
    population_percent: Optional[float] = Field(None, description="How full the server is, 0-100")
    crowding: Optional[Literal["normal", "busy", "full"]] = Field(
        None, description="normal, busy (80%+) or full (100%), as the site colours it"
    )
    is_new: Optional[bool] = None
    first_seen: Optional[str] = None
    observed_at: Optional[str] = None
    population_history: List[PopulationPoint] = Field(default_factory=list, description="Last 24 hours of population_percent")


class ServerRosterEntry(BaseModel):
    """NCSOFT's own view of a server: identity only, no population and no status."""

    server_id: str = Field(description="NCSOFT server id, e.g. 1101")
    name: Optional[str] = None
    short_name: Optional[str] = None
    faction: Optional[str] = Field(None, description="Elyos or Asmodian")
    region: str = Field(description="nae, naw, eu, la or as")


class CharacterHit(BaseModel):
    character_id: str = Field(description="NCSOFT character id")
    name: str
    level: Optional[int] = None
    server_id: str
    server_name: Optional[str] = None
    region: str = Field(description="nae, naw, eu, la or as")


# ------------------------------------------------------------------ plumbing


def server_query(
    server: Optional[str] = Query(
        None, description="Server name or id, e.g. Siel or 1101 - needed when the name exists on several"
    ),
) -> Optional[str]:
    return server


def get_board(
    board: str = Query(
        DEFAULT_BOARD,
        description="Board to read. The suffix is the language.",
        examples=["notice_en"],
    ),
) -> Aion2Board:
    # Upstream answers an unknown board with an empty list, which reads like
    # "no notices". Fail loudly instead.
    if board not in GLOBAL_BOARDS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown board '{board}'. Available boards: {', '.join(GLOBAL_BOARDS)}",
        )
    return Aion2Board(board)


@app.exception_handler(Aion2ApiError)
async def api_error(request: Request, exc: Aion2ApiError) -> JSONResponse:
    """One place to turn an upstream failure into a sensible HTTP status.

    Keeps every route free of try/except. 403/429 means something upstream is
    blocking us - most likely Cloudflare on the third-party server-population
    host, which rate-limits - so say that rather than a misleading 502.
    """
    if exc.status in (403, 429):
        status, detail = 503, f"Blocked or rate-limited upstream (HTTP {exc.status}): {exc.url}"
    elif exc.status == 404:
        status, detail = 404, str(exc)
    else:
        status, detail = 502, f"Upstream API failed: {exc}"
    return JSONResponse(status_code=status, content={"detail": detail})


@app.exception_handler(CharacterLookupError)
async def character_lookup_error(request: Request, exc: CharacterLookupError) -> JSONResponse:
    """No such name -> 404. Several -> 409 with the candidates, so a caller can retry with ?server=."""
    if not exc.candidates:
        return JSONResponse(status_code=404, content={"detail": str(exc)})
    return JSONResponse(status_code=409, content={"detail": str(exc), "candidates": exc.candidates})


# -------------------------------------------------------------------- routes


@app.get("/", tags=["start here"], summary="What this is and how to call it")
def root() -> Dict[str, Any]:
    return {
        "what": "Unofficial JSON API for the AION 2 announcement board, events, server population and characters",
        "how_to_use": {
            "newest notices": "/notices",
            "how many": "/notices?limit=50",
            "just the pinned ones": "/notices?pinned=true",
            "one notice": "/notices/{id}",
            "other language": "/notices?board=notice_de",
            "current events": "/events",
            "server population": "/servers",
            "one server": "/servers?name=Israphel&region=Europe",
            "the roster itself (first-party)": "/servers/roster",
            "server status with ids and 24h population": "/v2/servers?region=naw",
            "find a character": "/characters/search?name=s6x",
            "character stats and gear": "/characters/s6x?server=Siel",
            "their Daevanion boards": "/characters/s6x/daevanion?server=Siel",
            "one board": "/characters/s6x/daevanion/Nezekan?server=Siel",
        },
        "boards": GLOBAL_BOARDS,
        "browsable_docs": "/docs",
    }


@app.get(
    "/notices",
    tags=["notices"],
    summary="Newest notices",
    response_model=List[Notice],
)
def notices(
    limit: int = Query(20, ge=1, le=200, description="How many notices to return"),
    pinned: bool = Query(False, description="Return only the pinned/top notices"),
    board: Aion2Board = Depends(get_board),
) -> List[Notice]:
    if pinned:
        return [Notice(**board.normalize(item)) for item in board.pinned()[:limit]]
    return [Notice(**n) for n in board.iter_notices(limit=limit)]


@app.get(
    "/notices/{article_id}",
    tags=["notices"],
    summary="One notice, with its full text",
    response_model=NoticeDetail,
)
def notice(article_id: str, board: Aion2Board = Depends(get_board)) -> NoticeDetail:
    return NoticeDetail(**board.get_notice(article_id))


@app.get(
    "/events",
    tags=["events"],
    summary="Current events from /eventon",
    response_model=List[Event],
)
def events(
    limit: int = Query(20, ge=1, le=200, description="How many events to return"),
    status: Literal["RUNNING", "ALL", "CLOSED"] = Query(
        "RUNNING", description="RUNNING and ALL currently return the same set"
    ),
    country: str = Query("US", description="Country tag, e.g. US, DE, FR, JP"),
) -> List[Event]:
    client = Aion2Events(country=country, status=status)
    return [Event(**e) for e in client.iter_events(limit=limit)]


@app.get(
    "/servers",
    tags=["servers"],
    summary="Server population (third-party source)",
    response_model=List[ServerStatus],
)
def servers(
    name: Optional[str] = Query(None, description="Server name, e.g. Israphel"),
    region: Optional[str] = Query(None, description="Region filter, e.g. 'NA East', Europe, Asia"),
) -> List[ServerStatus]:
    """How full each server is.

    Sourced from the community site aion2.gaming.tools, which is **not** an NCSOFT
    service - this scrapes its page's HTML and is the most fragile endpoint here.
    `/v2/servers` reads the same site's JSON loader instead.

    A name on its own is ambiguous: the same server name exists in every region, so
    combine `name` with `region` when you want exactly one row.
    """
    return [ServerStatus(**s) for s in Aion2Servers().servers(name=name, region=region)]


@app.get(
    "/v2/servers",
    tags=["servers"],
    summary="Server status with ids, flags and 24h population (third-party source)",
    response_model=List[ServerStatusV2],
)
def servers_v2(
    name: Optional[str] = Query(None, description="Server name, e.g. Israphel"),
    region: Optional[Literal["nae", "naw", "eu", "la", "as"]] = Query(None, description="Region code"),
) -> List[ServerStatusV2]:
    """Same community source as `/servers`, read from its JSON loader instead of its HTML.

    Adds NCSOFT server ids, maintenance and creation-lock flags and a 24-hour population
    history. It has no current/max/queue counts; `population_percent` means the same
    as in v1. Upstream is fetched about once a minute, just after the
    site's own refresh, however many requests arrive; on upstream errors the last
    good data is served while it backs off. 502 only when nothing is cached yet.
    """
    return [ServerStatusV2(**s) for s in Aion2ServersV2().servers(name=name, region=region)]


@app.get(
    "/servers/roster",
    tags=["servers"],
    summary="Server roster, straight from NCSOFT (no population)",
    response_model=List[ServerRosterEntry],
)
def servers_roster() -> List[ServerRosterEntry]:
    """The servers themselves: ids, names, factions and regions.

    First-party, read from NCSOFT's own server list rather than the community site,
    so it survives a redesign of that page. NCSOFT publishes **no** population, status
    or queue data, so none of those fields are here - call `/servers` for those.

    Cached for an hour; the first request costs one upstream call per region.
    """
    return [ServerRosterEntry(**row) for row in server_list()]


@app.get(
    "/characters/search",
    tags=["characters"],
    summary="Find characters by name",
    response_model=List[CharacterHit],
)
def character_search(
    name: str = Query(..., min_length=1, description="Name or part of one"),
    region: Optional[Literal["nae", "naw", "eu", "la", "as"]] = Query(
        None, description="Only this region (default: all)"
    ),
) -> List[CharacterHit]:
    """Partial matches, across every Global region unless `region` is given.

    Reads the first page (20) per region.
    """
    return [CharacterHit(**c) for c in search_characters(name, region)]


@app.get("/characters/{name}", tags=["characters"], summary="A character's stats, gear and skills")
def character(name: str, server: Optional[str] = Depends(server_query)) -> Dict[str, Any]:
    """NCSOFT's info and equipment responses, merged and passed through unchanged:
    `profile`, `stat.statList`, `title`, `ranking`, `daevanion.boardList`,
    `equipment`, `petwing`, `skill.skillList`.

    404 when no character has that exact name; 409 (with `candidates`) when
    several do - add `?server=`.
    """
    c = resolve_character(name, server)
    return get_character(c["character_id"], c["server_id"], c["region"])


@app.get("/characters/{name}/daevanion", tags=["characters"], summary="A character's Daevanion boards")
def character_daevanion(name: str, server: Optional[str] = Depends(server_query)) -> List[Dict[str, Any]]:
    """Board `id`, `name`, `openNodeCount`, `totalNodeCount`, `openPercent`."""
    c = resolve_character(name, server)
    info, _ = character_endpoint("info", c["character_id"], c["server_id"], c["region"])
    return (info.get("daevanion") or {}).get("boardList") or []


@app.get(
    "/characters/{name}/daevanion/{board}",
    tags=["characters"],
    summary="One Daevanion board, node by node",
)
def character_daevanion_board(
    name: str, board: str, server: Optional[str] = Depends(server_query)
) -> Dict[str, Any]:
    """`board` is a board name (e.g. Nezekan) or id.

    `nodeList` is the full 15x15 grid: each node has its own `row` and `col`
    (1-15), and `type` None marks an empty cell.
    """
    c = resolve_character(name, server)
    info, region = character_endpoint("info", c["character_id"], c["server_id"], c["region"])
    boards = (info.get("daevanion") or {}).get("boardList") or []
    found = find_board(boards, board)
    if not found:
        raise HTTPException(
            status_code=404,
            detail=f"No board '{board}'. This character has: {', '.join(b['name'] for b in boards)}",
        )
    return {"board": found, **get_daevanion_board(c["character_id"], c["server_id"], found["id"], region)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8000")))
