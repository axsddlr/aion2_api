# AION 2 Notices, Events & Server Population API

Read AION 2 announcements, in-game events and live server population as clean JSON, instead of
loading the website in a browser and copy-pasting out of a web page.

No API key, no account, no login. The data is public.

```json
{
  "id": "6ac6a4c0fa34c1011d627a96",
  "title": "Scheduled maintenance: Oct 6 / 7",
  "url": "https://aion2.plaync.com/en-us/board/notice/view?articleId=6ac6a4c0fa34c1011d627a96",
  "posted_at": "2026-10-07T20:00:00.001Z",
  "writer": "admin",
  "is_admin": true,
  "view_count": 4366,
  "has_attachments": true
}
```

**This is unofficial.** It is not affiliated with or supported by NCSOFT, and it can break if
they change things. See [Caveats](#caveats).

---

## Quick start

Pick whichever fits you. You do **not** need both.

### Option A — a web API you can call from anything

Best if you want to fetch data from a script, a bot, a website, or another language.

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt          # Windows
# source .venv/bin/activate && pip install -r requirements.txt       # macOS / Linux

.venv\Scripts\python.exe -m uvicorn app:app --reload                 # Windows
# uvicorn app:app --reload                                           # macOS / Linux
```

It prints `Uvicorn running on http://127.0.0.1:8000`. Leave that terminal open and try:

```bash
curl "http://127.0.0.1:8000/notices?limit=3"
```

> On Windows PowerShell, `curl` is a built-in alias with different options — type
> **`curl.exe`** instead.

There is also a clickable, self-documenting page at
**<http://127.0.0.1:8000/docs>** where you can try every endpoint in the browser.

### Option B — the Python client, no installation

Best if you are writing Python or just want to read notices in a terminal.
It uses only the Python standard library, so there is nothing to install:

```bash
python aion2_api.py list -n 5
```

```
2026-10-07  6ac6a4c0fa34c1011d627a96  Scheduled maintenance: Oct 6 / 7
2026-10-05  6ab3f7806b722c561dc6a621  Graphics Card Giveaway
2026-10-05  6ac3eb6e9ed1202b9b8fb5b8  Customization Voucher to All Players
2026-10-05  6ac3bfa5feeef62e67566809  Thank you for 400,000 Active Players
2026-10-05  6ac3983171f8fb7c2a7a33b8  [Notice] Server Matchmaking Information (Asia)
```

---

## The web API

Five addresses. Four return data.

| Address | What you get |
|---|---|
| `GET /notices` | The newest notices |
| `GET /notices/{article_id}` | One notice, including its full text |
| `GET /events` | Current in-game events |
| `GET /servers` | Player counts for every server |
| `GET /` | A reminder of the above |

`/notices`, `/events` and `/servers` need no arguments at all. Everything else is optional:

| Query parameter | Applies to | Default | What it does |
|---|---|---|---|
| `board` | `/notices` | `notice_en` | Which language board to read |
| `limit` | `/notices`, `/events` | `20` | How many items to return (1–200) |
| `pinned` | `/notices` | `false` | Return only the pinned / important notices |
| `status` | `/events` | `RUNNING` | `RUNNING`, `ALL` or `CLOSED` |
| `country` | `/events` | `US` | Country tag, e.g. `US`, `DE`, `FR`, `JP` |
| `name` | `/servers` | – | Server name, e.g. `Israphel` |
| `region` | `/servers` | – | Region, e.g. `NA East`, `Europe`, `Asia` |

Available boards: `notice_en`, `notice_de`, `notice_fr`, `notice_es`, `notice_pt`.

### Examples

```bash
curl "http://127.0.0.1:8000/notices"                            # the newest 20
curl "http://127.0.0.1:8000/notices?limit=5"                    # just 5
curl "http://127.0.0.1:8000/notices?pinned=true"                # only the pinned ones
curl "http://127.0.0.1:8000/notices?board=notice_de"            # the German board
curl "http://127.0.0.1:8000/notices/6ac6a4c0fa34c1011d627a96"   # one notice, full text
curl "http://127.0.0.1:8000/events"                             # current events
curl "http://127.0.0.1:8000/events?country=JP"                  # another region's events
curl "http://127.0.0.1:8000/servers"                            # every server's population
curl "http://127.0.0.1:8000/servers?name=Zikel"                 # that name in all 5 regions
curl "http://127.0.0.1:8000/servers?name=Zikel&region=NA East"  # exactly one server
curl "http://127.0.0.1:8000/servers?region=Asia"                # one region
```

### What the responses look like

`GET /notices` returns a plain JSON array (shown trimmed here):

```json
[
  {
    "id": "6ac6a4c0fa34c1011d627a96",
    "title": "Scheduled maintenance: Oct 6 / 7",
    "summary": "Hello Daevas,We will be performing our weekly scheduled game server ma...",
    "url": "https://aion2.plaync.com/en-us/board/notice/view?articleId=6ac6a4c0fa34c1011d627a96",
    "posted_at": "2026-10-07T20:00:00.001Z",
    "updated_at": "2026-10-06T11:50:08.107Z",
    "writer": "admin",
    "is_admin": true,
    "view_count": 4366,
    "like_count": 0,
    "comment_count": 0,
    "has_attachments": true,
    "thumbnails": ["https://fizz-download.playnccdn.com/lg/file/AION/download_thumbnail/1a0fcfba189-..."],
    "tags": ["CommentWriteOff", "Lang:en", "CommentUiOff"]
  }
]
```

`GET /notices/{id}` returns one object with the same fields plus `body`, `attachments` and the
neighbouring article ids:

```json
{
  "id": "6ac3bfa5feeef62e67566809",
  "title": "Thank you for 400,000 Active Players",
  "body": "Daevas!\n\nThank you for helping us reach 400,000 active players! ...",
  "attachments": {
    "files": [
      {
        "fileName": "announcements_EN.jpg",
        "mimeType": "image/jpeg",
        "fileSize": 19830,
        "fileUrl": "https://fizz-download.playnccdn.com/lg/file/AION/download/1a10ca24a62-..."
      }
    ],
    "thumbnailUrl": ""
  },
  "prev_id": "6ac3983171f8fb7c2a7a33b8",
  "next_id": "6ac3eb6e9ed1202b9b8fb5b8"
}
```

`GET /events` returns events with a banner image and a date window:

```json
[
  {
    "id": "63106",
    "key": "B69064BAEAA44F3E88609080B58F8C90",
    "title": "[Notice] New Attendance Event Announcement",
    "url": "https://aion2.plaync.com/en-us/eventon/board/event_notice/view?articleId=50000002",
    "image": "https://fizz-download.playnccdn.com/download/v2/buckets/marketing-platform/files/1a0f369ab0d-...",
    "image_small": "https://fizz-download.playnccdn.com/download/v2/buckets/marketing-platform/files/1a0f369ab0d-...",
    "starts_at": "2026-09-30T13:00:01Z",
    "ends_at": "2026-12-16T07:30:01Z",
    "status": "RUNNING",
    "tags": ["TYPE_DAILY", "COUNTRY_US", "DOMAIN_AION2_GLOBAL", "MKT_PROMOTION"]
  }
]
```

`GET /servers` returns one row per server, with how full it is:

```json
[
  {
    "name": "Zikel",
    "status": "Online",
    "faction": "Asmodian",
    "region": "NA East",
    "population_percent": 83.0,
    "current": 6409,
    "max": 7700,
    "queue": null,
    "badges": ["Advanced Access"],
    "note": "Character creation blocked"
  }
]
```

### When something goes wrong

| Status | Meaning |
|---|---|
| `404` | No such article, or a board name that does not exist (the message lists the valid ones) |
| `422` | A parameter is out of range or unknown, e.g. `limit=999` or `status=NOPE` |
| `502` | The upstream source failed or is unreachable |
| `503` | Something upstream is blocking or rate-limiting us — wait and retry |

---

## The Python client

```python
from aion2_api import Aion2Board

board = Aion2Board("notice_en")          # or "notice_de", "notice_fr", "notice_es", "notice_pt"

for notice in board.iter_notices(limit=20):     # newest first
    print(notice["posted_at"], notice["title"])
    print(notice["url"])

one = board.get_notice("6ac6a4c0fa34c1011d627a96")
print(one["title"], one["view_count"])
print(one["body"])                              # full text, HTML already stripped
```

### Events

```python
from aion2_api import Aion2Events

events = Aion2Events()                          # US / English, running events
for event in events.iter_events(limit=10):
    print(event["status"], event["starts_at"], event["title"])
    print(event["url"], event["image"])

Aion2Events(country="DE")                       # another region
Aion2Events(status="CLOSED")                    # ended events
```

### Server population

```python
from aion2_api import Aion2Servers

servers = Aion2Servers()
for s in servers.servers():                     # every server
    print(f"{s['name']:12} {s['region']:8} {s['population_percent']:>4}%")

servers.servers(name="Zikel")                   # this name in every region (5 rows)
servers.server("Zikel", region="NA East")       # one server
```

### Command line

```bash
python aion2_api.py list -n 20                  # newest 20 notices
python aion2_api.py list -n 100 --json          # same, as JSON
python aion2_api.py view <article_id>           # one notice, full text
python aion2_api.py view <article_id> --html    # raw article HTML
python aion2_api.py pinned                      # pinned / important notices
python aion2_api.py board                       # board metadata
python aion2_api.py --board notice_de list -n 5 # another language
python aion2_api.py events -n 10                # current events
python aion2_api.py events --json               # events as JSON
python aion2_api.py events --country JP         # another region
python aion2_api.py servers                     # every server's population
python aion2_api.py servers --name Zikel        # that name in all regions
python aion2_api.py servers --name Zikel --region "NA East"
python aion2_api.py servers --json              # as JSON
```

`python aion2_api.py --help` lists everything.

---

## What the fields mean

Notice fields (`/notices`, `/notices/{id}`):

| Field | Meaning |
|---|---|
| `id` | Unique article id — pass it to `/notices/{id}` |
| `title` | Notice headline |
| `summary` | Opening of the notice, HTML stripped |
| `url` | The notice on the official website, in the right language |
| `posted_at` / `updated_at` | ISO 8601 UTC timestamps |
| `posted_epoch` | Same time as a Unix timestamp in seconds |
| `writer` | Author name; `admin` for official NCSOFT posts |
| `is_admin` | `true` when posted by NCSOFT staff |
| `view_count`, `like_count`, `comment_count` | Counters as shown on the site |
| `has_attachments` | `true` if the notice carries images or files |
| `thumbnails` | Image URLs belonging to the notice |
| `tags` | Internal flags, e.g. `Lang:en`, `CommentWriteOff` |
| `body` | *(detail only)* The full notice text, HTML stripped |
| `attachments.files[]` | *(detail only)* `fileName`, `mimeType`, `fileSize`, `fileUrl` |
| `prev_id` / `next_id` | *(detail only)* Neighbouring articles; may be `null` |

Event fields (`/events`):

| Field | Meaning |
|---|---|
| `id` | Event id |
| `key` | Stable event key |
| `title` | Event name |
| `url` | The event's page on the official site |
| `image` / `image_small` | Banner image (and its smaller variant) |
| `starts_at` / `ends_at` | Event window, ISO 8601 UTC |
| `status` | `RUNNING`, `UPCOMING` or `ENDED` — worked out from the date window |
| `tags` | Region, domain and type tags, e.g. `COUNTRY_US`, `TYPE_DAILY` |

Server fields (`/servers`):

| Field | Meaning |
|---|---|
| `name` | Server name, e.g. `Zikel` |
| `status` | `Online` (or `Offline`) |
| `faction` | `Asmodian` or `Elyos` — each server houses only one |
| `region` | `Europe`, `NA East`, `NA West`, `Asia` or `SA` |
| `population_percent` | How full the server is |
| `current` | Players online now |
| `max` | Server capacity |
| `queue` | Login queue, or `null` when there is none |
| `badges` | Access flags, e.g. `Advanced Access` |
| `note` | Site note, e.g. `Character creation blocked` |

`name` alone is **not** unique — every server name exists once per region, so `name` + `region`
is the real key.

---

## Rate limits and politeness

Nothing here is needed to make the code work. It is what keeps you from being rate-limited, and
it lives in one place (`_fetch()` in `aion2_api.py`) so every client gets it.

| Measure | Default | Why |
|---|---|---|
| Proper User-Agent | `aion2-api/1.0 (notices board)` | `product/version (comment)`, one per source. Says what is calling. |
| Matching `Accept` | JSON for the APIs, HTML for the scrape | Each source is told what we want back. |
| Spacing per host | 1 second | Two requests to one host are never sent closer together than this. |
| Response cache | 60 seconds | A repeat read is served locally and never reaches them. |
| `Retry-After` | honoured | When a server says how long to wait, wait that long. |
| Retry policy | 429/503 only, twice | Those mean "come back later". A `403` is a deliberate block, so it is not retried. |

Repeating the same read 15 times causes **0** extra network requests. If you poll, that is what
protects you — not hiding what you are.

Two optional environment variables:

| Variable | Effect |
|---|---|
| `AION2_CONTACT` | Added to every User-Agent, e.g. `aion2-api/1.0 (notices board; +https://you.example)`. **Set this** if you deploy publicly. |
| `AION2_USER_AGENT` | Replaces the whole User-Agent for every source, if you need full control. |

Tune `MIN_REQUEST_INTERVAL`, `CACHE_TTL` and `MAX_RETRIES` at the top of `aion2_api.py`.

If a source starts refusing you, the fix is to slow down and cache harder, or to ask the operator
— not to disguise the client. A browser-automation dependency is not needed for any of these
sources and is not installed.

---

## Files

| File | What it is |
|---|---|
| `aion2_api.py` | The client library and CLI. Standard library only. |
| `app.py` | The FastAPI web service (`/notices`, `/notices/{id}`, `/events`, `/servers`). |
| `test_aion2.py` | Offline checks. No network, no dependencies. |
| `requirements.txt` | The two packages the web service needs. |

### Checks

```bash
python test_aion2.py
```

16 checks, no network and no pytest — just `assert`s. Covers the server-population table parser,
the notice paging, the locale mapping, the event status maths, and the rate-limit behaviour
(caching, per-host spacing, `Retry-After`, and not retrying a `403`).

---

## Caveats

- **Unofficial and unsupported.** These are private endpoints. NCSOFT can change or block them at
  any time, and a breaking change here needs a code update — nothing in the repo can adapt for you.
- **`/servers` reads a fan site, not NCSOFT.** [aion2.gaming.tools](https://aion2.gaming.tools/server-status)
  is an unaffiliated community project, and that page is plain HTML, so this is the most fragile
  endpoint: it breaks if the page is redesigned, and it is rate-limited. Cache it.
- **Be polite.** It is public data, but do not hammer it. Results are cached for 60 seconds.
- **`502` is often just a blip.** A dropped connection or DNS hiccup on your side surfaces as
  `502`. Trying again usually works.
- **View counts drift.** `view_count` goes up when the notice is read, so it changes between runs
  and is never perfectly stable.
- **Read-only.** This only reads data. It cannot post, comment, or log in.
