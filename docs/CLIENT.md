# Python client and CLI

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

Or look up a character by name:

```bash
python aion2_api.py character s6x --server Siel
```

```
s6x  Lv45 Chanter  Siel (Elyos)  CP 48326
  Might                            25  Attack increase +2.5%
  ...
Gear:
  MainHand     Spiritforged Staff +11  [Unique]
  ...
```

The same lookup over the web API: `curl "http://127.0.0.1:8000/characters/s6x?server=Siel"`.

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

`Aion2ServersV2` reads the same site's JSON loader instead: server ids, maintenance and
creation-lock flags, `population_percent` (0–100, as in v1), a `crowding` label (`normal`, `busy`
or `full`) and a 24-hour `population_history`, but no current/max/queue counts. Regions are
codes, as in the roster:

```python
from aion2_api import Aion2ServersV2

for s in Aion2ServersV2().servers(region="naw"):
    print(f"{s['name']:12} {s['population_percent']:>5}%  {s['crowding']}")
```

`balance()` compares the factions over the last day, from the same fetch:

```python
bal = Aion2ServersV2().balance(region="eu")
eu = bal["regions"][0]
print(f"EU: {eu['elyos_share_percent']}% Elyos, {eu['asmodian_share_percent']}% Asmodian")
for p in bal["pairs"]:
    e, a = p["elyos"], p["asmodian"]
    print(f"{e['name']} {e['average_population_percent']}%  vs  {a['name']} {a['average_population_percent']}%")
```

### Characters

Look a character up by **name**, or paste a character link from a fan site such as
[aionflex.gg](https://aionflex.gg) (anything with `?id=...&server=...` works). Either way the
data comes straight from NCSOFT — the link is only a way to carry the character id.

```python
from aion2_api import (
    resolve_character, get_character, get_daevanion_board, render_daevanion_board,
)

c = resolve_character("s6x", server="Siel")     # or a link; -> character_id, server_id, region
data = get_character(c["character_id"], c["server_id"], c["region"])

print(data["profile"]["className"], data["profile"]["combatPower"])
for stat in data["stat"]["statList"]:            # Might, Dexterity, ... Item Level
    print(stat["name"], stat["value"], stat["statSecondList"])
for item in data["equipment"]["equipmentList"]:  # one per equipped slot
    print(item["slotPosName"], item["name"], item["enchantLevel"], item["grade"])

boards = data["daevanion"]["boardList"]          # this character's boards (ids like 81, 82, ...)
board = get_daevanion_board(c["character_id"], c["server_id"], boards[0]["id"], c["region"])
print(render_daevanion_board(board["nodeList"]))  # 15x15 text grid
```

- **Names are not unique.** The same name can exist on several servers. `resolve_character`
  raises `LookupError` listing the candidates; pass `server=` (name or id) to pick one.
- **A server id is faster than a name.** Server ids are unique and encode the region
  (`1101` → `nae`), so `server="1101"` searches one region (~2s) where `server="Siel"` has to
  search all five (~6s) — server names repeat in every region. A resolved name is remembered
  for an hour, so repeat lookups skip the search either way.
- **`region` comes from NCSOFT, not from a guess.** The id-to-region map is read from NCSOFT's
  own server list (`/api/gameinfo/servers`) and cached for an hour — one request per region the
  first time (~4s), nothing after that. If that list is unreachable the code falls back to the
  id's second digit, which is how the mapping was originally derived.
- **`region` is optional.** Search already knows it. With only an id and server, the lookup
  tries `nae`, `naw`, `eu`, `la` and `as` until one answers (`region=GLOBAL` in a link is not a
  real region and is treated the same way).
- **Board nodes place themselves.** Every node in `nodeList` carries its own `row` and `col`
  (1–15); `type` `None` marks an empty cell. Draw them on a 15×15 grid and the board's shape
  appears.

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
python aion2_api.py servers --v2 --region naw   # v2: ids, flags, 24h population (JSON)
python aion2_api.py character s6x --server Siel # stats + gear (server: name or id)
python aion2_api.py character "<character link>" # same, from an aionflex.gg-style link
python aion2_api.py character s6x --server Siel --json  # everything: titles, ranking, skills, pet
python aion2_api.py daevanion s6x --server Siel # list the character's Daevanion boards
python aion2_api.py daevanion s6x --server Siel --board nezekan  # draw one (name or id)
```

`daevanion --board` prints the board as a grid: `S` start, `#`/`o` stat node and `*`/`+` skill
node (unlocked/locked), `.` empty — followed by the bonuses unlocked on it.

Quote links in the shell — they contain `&`.

`python aion2_api.py --help` lists everything.

---
