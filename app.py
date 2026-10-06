"""FastAPI service exposing the reverse-engineered AION 2 (Global) APIs.

    GET /notices              newest notices (no arguments needed)
    GET /notices/{id}         one notice, with its full text
    GET /events               current events from /eventon
    GET /servers              server population (third-party source)

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
    DEFAULT_BOARD,
    GLOBAL_BOARDS,
    Aion2ApiError,
    Aion2Board,
    Aion2Events,
    Aion2Servers,
)

app = FastAPI(
    title="AION 2 Notices, Events & Server Population",
    version="3.0.0",
    description=(
        "Unofficial read-only JSON API for AION 2.\n\n"
        "* **GET /notices** — newest notices, or `?board=notice_de` for another language\n"
        "* **GET /notices/{id}** — one notice, including its full text\n"
        "* **GET /events** — current in-game events\n"
        "* **GET /servers** — player counts per server\n\n"
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


# ------------------------------------------------------------------ plumbing


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


# -------------------------------------------------------------------- routes


@app.get("/", tags=["start here"], summary="What this is and how to call it")
def root() -> Dict[str, Any]:
    return {
        "what": "Unofficial JSON API for the AION 2 announcement board, events and server population",
        "how_to_use": {
            "newest notices": "/notices",
            "how many": "/notices?limit=50",
            "just the pinned ones": "/notices?pinned=true",
            "one notice": "/notices/{id}",
            "other language": "/notices?board=notice_de",
            "current events": "/events",
            "server population": "/servers",
            "one server": "/servers?name=Israphel&region=Europe",
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
        return [Notice(**board.normalize(item)) for item in board.pinned()]
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
    """Player counts per server.

    Sourced from the community site aion2.gaming.tools, which is **not** an NCSOFT
    service - it has no JSON API, so this scrapes its page and is the most fragile
    endpoint here.

    A name on its own is ambiguous: the same server name exists in every region, so
    combine `name` with `region` when you want exactly one row.
    """
    return [ServerStatus(**s) for s in Aion2Servers().servers(name=name, region=region)]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8000")))
