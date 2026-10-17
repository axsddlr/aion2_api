# AION 2 Notices, Events, Servers & Characters API

[![CI](https://github.com/axsddlr/aion2_api/actions/workflows/ci.yml/badge.svg)](https://github.com/axsddlr/aion2_api/actions/workflows/ci.yml)

Read AION 2 announcements, in-game events, live server population and any character's stats,
gear and Daevanion boards as clean JSON, instead of loading the website in a browser and
copy-pasting out of a web page.

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

Fastest path, no Python needed — build the image and start it:

```bash
docker build -t aion2-api . && docker run -d --name aion2 -p 8000:8000 aion2-api
curl "http://127.0.0.1:8000/notices?limit=3"
```

Or, if you are a Python user, [uv](https://docs.astral.sh/uv/) creates the environment and
installs the pinned dependencies in one command:

```bash
uv sync
uv run uvicorn app:app --reload
```

Either way the service is on <http://127.0.0.1:8000>, with a clickable page at
**<http://127.0.0.1:8000/docs>** where you can try every endpoint in the browser. There is no
`requirements.txt` — `pyproject.toml` is the source of truth for dependencies and `uv.lock`
pins them.

Prefer reading notices in a terminal? The client needs nothing installed at all:

```bash
python aion2_api.py list -n 5
```

## Where to go next

| If you want to… | Read |
|---|---|
| Call the HTTP API | the endpoint table and examples below |
| Know what a field means, or see a full response | [docs/API.md](docs/API.md) |
| Use the Python client or the `aion2_api.py` CLI | [docs/CLIENT.md](docs/CLIENT.md) |
| Build, size or harden the container | [docs/DOCKER.md](docs/DOCKER.md) |
| Work on the code, run checks, cut a release | [docs/DEVELOPING.md](docs/DEVELOPING.md) |

## The web API

| Address | What you get |
|---|---|
| `GET /notices` | The newest notices |
| `GET /notices/{article_id}` | One notice, including its full text |
| `GET /events` | Current in-game events |
| `GET /servers` | How full every server is |
| `GET /servers/roster` | The server list itself, straight from NCSOFT — no population |
| `GET /v2/servers` | How full every server is (percent + `normal`/`busy`/`full`), status flags, last 24 hours |
| `GET /characters/search?name=` | Characters whose name contains `name` |
| `GET /characters/{name}` | One character's stats, gear, skills, titles and ranking |
| `GET /characters/{name}/daevanion` | That character's Daevanion boards |
| `GET /characters/{name}/daevanion/{board}` | One board, node by node (`board` is a name like `Nezekan`, or an id) |
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
| `name` / `region` | `/v2/servers` | – | Server name; region as `nae`, `naw`, `eu`, `la` or `as` |
| `region` | `/characters/search` | all | One of `nae`, `naw`, `eu`, `la`, `as` |
| `server` | `/characters/{name}...` | – | Server name or id, e.g. `Siel` or `1101` — needed when the name exists on more than one server. An id is faster: it searches one region instead of five |

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
curl "http://127.0.0.1:8000/servers/roster"                      # the server list NCSOFT publishes
curl "http://127.0.0.1:8000/v2/servers?region=naw"              # v2: percent full, crowding, 24h history
curl "http://127.0.0.1:8000/characters/search?name=s6x"         # who is called that, where
curl "http://127.0.0.1:8000/characters/s6x?server=Siel"         # stats, gear, skills
curl "http://127.0.0.1:8000/characters/s6x/daevanion?server=Siel"          # their boards
curl "http://127.0.0.1:8000/characters/s6x/daevanion/Nezekan?server=Siel"  # one board
```

Character responses are NCSOFT's own JSON passed through — see
[what the fields mean](docs/API.md#what-the-fields-mean). A name that exists on several servers answers
`409` with the choices, so a client can show them and retry with `?server=`:

```json
{
  "detail": "2 characters named 's6x': s6x (Siel 1101, nae), s6x (Yustiel 1505, as); pick a server",
  "candidates": [
    {"character_id": "rKx-d-9c8YwO5HqimeieGOdLR7ZXFay1iDzckIR5EsM=", "name": "s6x", "level": 45,
     "server_id": "1101", "server_name": "Siel", "region": "nae"},
    {"character_id": "Tm_y1mYmkY9R4VUZfgwDvyF6kOoq5gy78fVeyyQxqTM=", "name": "s6x", "level": 24,
     "server_id": "1505", "server_name": "Yustiel", "region": "as"}
  ]
}
```


### A response

`GET /notices` returns a plain JSON array; every other route returns the same kind of shape.
Samples for all of them are in [docs/API.md](docs/API.md#responses).

```json
[
  {
    "id": "6ac6a4c0fa34c1011d627a96",
    "title": "Scheduled maintenance: Oct 6 / 7",
    "url": "https://aion2.plaync.com/en-us/board/notice/view?articleId=6ac6a4c0fa34c1011d627a96",
    "posted_at": "2026-10-07T20:00:00.001Z",
    "writer": "admin",
    "is_admin": true,
    "tags": ["CommentWriteOff", "Lang:en", "CommentUiOff"]
  }
]
```

### When something goes wrong

| Status | Meaning |
|---|---|
| `404` | No such article, or a board name that does not exist (the message lists the valid ones), or no character with that exact name |
| `409` | Several characters share that name — the body lists `candidates`; add `?server=` |
| `422` | A parameter is out of range or unknown, e.g. `limit=999` or `status=NOPE` |
| `502` | The upstream source failed or is unreachable |
| `503` | Something upstream is blocking or rate-limiting us — wait and retry |

---


## Rate limits and politeness

It is public data, and the client is already polite for you — cached reads, requests spaced per
host, `Retry-After` honoured. Do not work around that if you run something busy. The exact limits,
the reasoning behind each, and the two optional environment variables are in
[docs/API.md](docs/API.md#rate-limits-and-politeness).

## Caveats

- **Unofficial and unsupported.** These are private endpoints. NCSOFT can change or block them at
  any time, and a breaking change here needs a code update — nothing in the repo can adapt for you.
- **`/servers` reads a fan site, not NCSOFT.** [aion2.gaming.tools](https://aion2.gaming.tools/server-status)
  is an unaffiliated community project, and that page is plain HTML, so this is the most fragile
  endpoint: it breaks if the page is redesigned, and it is rate-limited. Cache it.
- **Name search reads one page.** The first 20 results per region. If many longer names contain
  the one you want, it can fall off that page and you get "0 characters named ..." — use a link
  or the character id instead.
- **Be polite.** It is public data, but do not hammer it. Results are cached for 60 seconds.
- **`502` is often just a blip.** A dropped connection or DNS hiccup on your side surfaces as
  `502`. Trying again usually works.
- **View counts drift.** `view_count` goes up when the notice is read, so it changes between runs
  and is never perfectly stable.
- **Read-only.** This only reads data. It cannot post, comment, or log in.

---


## Licence

MIT — see [LICENSE](LICENSE). Use it, modify it, ship it, embed it in your own project; just keep
the copyright notice. No warranty.

That covers the **code in this repository**. The **data** is not ours: notices, events and character
data belong to NCSOFT, and the server-population table comes from
[aion2.gaming.tools](https://aion2.gaming.tools/server-status), an unaffiliated community site.
Credit them, respect their terms, and keep your requests polite.
