# API reference

Every response shape and every field. The endpoint list itself is in the
[README](../README.md#the-web-api).

## Responses

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

`GET /servers/roster` returns the server list itself, straight from NCSOFT — identity only, with no
`status` and no population, because NCSOFT publishes neither:

```json
[
  {
    "server_id": "1101",
    "name": "Siel",
    "short_name": "SIE",
    "faction": "Elyos",
    "region": "nae"
  }
]
```

`region` here is the code form (`nae`, `naw`, `eu`, `la`, `as`), not the display name `/servers`
uses (`NA East`, `Europe`, ...) — it is the same value the character routes take as `?server=`.

`GET /v2/servers` returns the same servers with more detail: how full each one is as a percentage
plus a plain-word `crowding` label, status flags, and the last 24 hours (shortened here):

```json
[
  {
    "id": 2202,
    "name": "Zikel",
    "region": "naw",
    "faction": "Asmodian",
    "online": true,
    "maintenance": false,
    "creation_blocked": true,
    "population_percent": 20.0,
    "crowding": "normal",
    "is_new": false,
    "first_seen": "2026-10-01T00:00:00.000Z",
    "observed_at": "2026-10-17T21:34:06.716Z",
    "population_history": [
      {"time": "2026-10-17T19:00:00Z", "population_percent": 17.3},
      {"time": "2026-10-17T20:00:00Z", "population_percent": 19.0}
    ]
  }
]
```

Read it as: Zikel (NA West) is online and 20% full, which the site calls normal; new characters
cannot be created there.

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
| `population_percent` | How full the server is — `null` if the site omits that column |
| `current` | Players online now — `null` if the site omits that column |
| `max` | Server capacity — `null` if the site omits that column |
| `queue` | Login queue, or `null` when there is none |
| `badges` | Access flags, e.g. `Advanced Access` |
| `note` | Site note, e.g. `Character creation blocked` |

`name` alone is **not** unique — every server name exists once per region, so `name` + `region`
is the real key.

The four population columns are **optional**. The page does not always render them, so any of
`population_percent`, `current`, `max` and `queue` can be `null` in an otherwise valid response —
treat `null` as "not published", never as zero. A row that stops short of those columns is kept,
with the missing numbers `null`, rather than dropped. `name`, `status`, `faction` and `region` are
always present; if one of those disappears the table has really changed and `/servers` returns a
`502`.

Roster fields (`/servers/roster`), first-party:

| Field | Meaning |
|---|---|
| `server_id` | NCSOFT server id, e.g. `1101` — unique across Global; its 2nd digit is the region |
| `name` | Server name, e.g. `Siel` |
| `short_name` | Three-letter tag, e.g. `SIE` |
| `faction` | `Elyos` or `Asmodian` — every server houses exactly one |
| `region` | `nae`, `naw`, `eu`, `la` or `as` |

There is deliberately no `status`, `population_percent`, `current`, `max` or `queue` here: NCSOFT
publishes none of those, so `/servers/roster` is identity only. Call `/servers` for the numbers.
Use this endpoint when you want the roster from a source that cannot break the way a scraped page
can — it reads NCSOFT's own server list and is cached for an hour.

Server fields (`/v2/servers`), same community source as `/servers` but read from its JSON loader:

| Field | Meaning |
|---|---|
| `id` | NCSOFT server id, the same as `server_id` in `/servers/roster` |
| `name` | Server name |
| `region` | `nae`, `naw`, `eu`, `la` or `as` — also what `?region=` takes |
| `faction` | `Asmodian` or `Elyos` |
| `online` / `maintenance` / `creation_blocked` | Status flags |
| `population_percent` | How full the server is, `0`–`100` — same as in `/servers` |
| `crowding` | `normal`, `busy` (80% or more) or `full` (100%) — the site's green / amber / red |
| `is_new` / `first_seen` | Whether the site lists it as new, and since when |
| `observed_at` | When the site last read this server |
| `population_history` | Last 24 hours of `population_percent`, hourly: `[{"time": "2026-10-17T20:00:00Z", "population_percent": 17.0}]` |

There are no `current`, `max` or `queue` fields: the loader does not carry them.

`/v2/servers` is rate-limited to the site's own cadence: the site re-checks every server once a
minute, and the service fetches once per re-check, about 15s after it, however many requests it
gets. Data is therefore 15–75s old. If the site errors or blocks, the last good data keeps being
served (check `observed_at` for its age) while the service backs off 1, 2, 4… minutes, up to 10.
Only with nothing cached yet — or if the site changes its data format — does it return `502`;
`/servers` keeps working either way. The limit is per process, so replicas each poll.

`GET /v2/balance` compares the two factions over the last day, from the same fetch (and the same
rate limit) as `/v2/servers`. `?region=` takes `nae`, `naw`, `eu`, `la` or `as`; shortened here:

```json
{
  "period_hours": 24,
  "regions": [
    {
      "region": "eu",
      "elyos_share_percent": 40.6,
      "asmodian_share_percent": 59.4,
      "prime_time": {
        "start": "2026-10-17T17:00:00Z",
        "end": "2026-10-17T21:00:00Z",
        "elyos_share_percent": 41.0,
        "asmodian_share_percent": 59.0
      },
      "history": [
        {"time": "2026-10-16T23:00:00Z", "elyos_share_percent": 39.4, "asmodian_share_percent": 60.6}
      ]
    }
  ],
  "pairs": [
    {
      "region": "eu",
      "elyos": {"id": 1301, "name": "Siel", "average_population_percent": 42.9,
                "prime_time_population_percent": 59.8, "creation_blocked_hours": 24.0},
      "asmodian": {"id": 2301, "name": "Israphel", "average_population_percent": 41.8,
                   "prime_time_population_percent": 54.5, "creation_blocked_hours": 24.0},
      "history": [
        {"time": "2026-10-16T23:00:00Z", "elyos_population_percent": 40.1, "asmodian_population_percent": 38.6}
      ]
    }
  ]
}
```

Read it as: over the last day, 59% of EU's players were Asmodian. Siel (Elyos) and its partner
Israphel (Asmodian) were about equally full, and both blocked new characters all day.

| Field | Meaning |
|---|---|
| `period_hours` | How far back the figures go — `24` |
| `regions[].elyos_share_percent` / `asmodian_share_percent` | Each faction's share of the region's players; the two add up to 100 |
| `regions[].prime_time` | The region's busiest 4 hours, and the shares during them |
| `regions[].history` | The shares hour by hour |
| `pairs[].elyos` / `pairs[].asmodian` | The two servers that are partners: `id`, `name`, how full each was on average and in prime time (`0`–`100`), and `creation_blocked_hours` — how many of the 24 hours new characters could not be made there |
| `pairs[].history` | How full each was, hour by hour |

A share is `null` when neither faction had anyone on in that hour. If the site stops sending
balance data, `/v2/balance` returns `502` and `/v2/servers` is unaffected.

Character data (`get_character`) is NCSOFT's own JSON, passed through unchanged — two responses
merged into one dict:

| Key | From | Contains |
|---|---|---|
| `profile` | info | Name, level, class, race, server, combat power, title, profile image |
| `stat.statList[]` | info | `name`, `value`, `type` and the bonus text in `statSecondList` |
| `title`, `ranking` | info | Titles and ranking entries |
| `daevanion.boardList[]` | info | Board `id`, `name`, `openNodeCount` / `totalNodeCount`, `openPercent` |
| `equipment.equipmentList[]` | equipment | Equipped items: `slotPosName`, `name`, `enchantLevel`, `grade`, `icon` |
| `equipment.skinList[]` | equipment | Cosmetic skins |
| `petwing` | equipment | `pet`, `wing`, `wingSkin` |
| `skill.skillList[]` | equipment | Skills with `skillLevel`, `category`, `equip` |

A Daevanion board (`get_daevanion_board`) has `nodeList[]` (`row`, `col`, `type` —
`Start`/`Stat`/`SkillLevel`/`None`, `open`, `grade`, `name`, `effectList`) plus
`openStatEffectList` and `openSkillEffectList`.

Endpoints behind them (no key, no login):

| Call | Endpoint |
|---|---|
| Search by name | `GET https://api-search.plaync.com/aion2global/search/v2/character?keyword=&region=&localeInfo=en-US` |
| Info | `GET https://aion2.plaync.com/api/character/info?region=&lang=en-US&characterId=&serverId=` |
| Equipment | `GET https://aion2.plaync.com/api/character/equipment` (same parameters) |
| Daevanion board | `GET https://aion2.plaync.com/api/character/daevanion/detail` (same, plus `boardId=`) |

`region` must be the real one (`nae`, `naw`, `eu`, `la`, `as`) or the answer is a bare `404`.
Character ids end in `=`; search returns them already encoded (`%3D`) and fan-site links
double-encode them (`%253D`) — the client undoes both.

---

## Rate limits and politeness

Nothing here is needed to make the code work. It is what keeps you from being rate-limited, and
it lives in one place (`_fetch()` in `aion2_api.py`) so every client gets it.

| Measure | Default | Why |
|---|---|---|
| Proper User-Agent | `aion2-api/1.0.0 (notices board)` | `product/version (comment)`, one per source. Says what is calling. |
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
| `AION2_CONTACT` | Added to every User-Agent, e.g. `aion2-api/1.0.0 (notices board; +https://you.example)`. **Set this** if you deploy publicly. |
| `AION2_USER_AGENT` | Replaces the whole User-Agent for every source, if you need full control. |

Tune `MIN_REQUEST_INTERVAL`, `CACHE_TTL` and `MAX_RETRIES` at the top of `aion2_api.py`.

If a source starts refusing you, the fix is to slow down and cache harder, or to ask the operator
— not to disguise the client. A browser-automation dependency is not needed for any of these
sources and is not installed.

---
