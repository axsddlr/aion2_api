# Developing

Repo layout, what the checks are, and how CI and releases work.

## Files

| File | What it is |
|---|---|
| `aion2_api.py` | The client library and CLI (notices, events, servers, characters). Standard library only. |
| `app.py` | The FastAPI web service (`/notices`, `/events`, `/servers`, `/characters`). |
| `test_aion2.py` | Offline checks for the client and CLI. No network, no dependencies. |
| `test_app.py` | Offline checks for the web API routes. Needs the dev dependency `httpx2`. |
| `pyproject.toml` | Project metadata, the two dependencies the web service needs, and the `dev` group for tests. |
| `uv.lock` | Pinned dependency versions, written by `uv sync`. Commit it. |
| `.github/workflows/` | CI on every push and PR; releases from tags. |
| `LICENSE` | MIT. Use the code, ship it, fork it — keep the copyright notice. |
| `Dockerfile` | Two-stage image: 91 MB on Alpine, non-root, with a healthcheck. |
| `.dockerignore` | Keeps the build context to a few hundred kB — no `.venv`, `.git` or captures. |
| `compose.yaml` | Runs the image as a service: read-only rootfs, restart policy, port override. |

### Checks

```bash
uv run python test_aion2.py   # client + CLI
uv run python test_app.py     # web API routes
```

No network and no pytest — just `assert`s.

`test_aion2.py` (34 checks, standard library only) covers the server-population table parser
(including a page that drops the optional population columns, one that drops a required one, and a
row cut short of the optional columns),
the notice paging, the locale mapping, the event status maths, the rate-limit behaviour
(caching, per-host spacing for simultaneous callers, `Retry-After`, and not retrying a `403`),
and the character code (link parsing, region fallback, the first-party roster and its faction
mapping, the roster-backed region lookup and its offline fallback, name resolution and its cache,
Daevanion grid placement).

`test_app.py` (12 checks) drives the FastAPI app through its test client with the upstream calls
faked: search and its `region` validation, `?server=` pass-through, `409` with `candidates` for
an ambiguous name, `404` for an unknown name or board, a `/servers` response whose optional
population columns are `null`, `/servers/roster` and its `502` when the upstream list fails,
board lookup by name or id, and how upstream failures map to `404` / `502` / `503`. It needs `httpx2`, which `uv sync` installs from
the `dev` group; the web service itself does not depend on it.

Both counts above are asserted by `test_documented_check_counts_match_the_suites`, so this page
cannot quietly drift from the suites: add or remove a test and that check fails until the number
here matches again.

The scrape itself can be checked against reality, which is the thing a parser cannot tell you:

```bash
uv run python aion2_api.py servers --check
```

That compares every row with NCSOFT's own roster and exits non-zero naming any server the page is
missing, inventing, duplicating, or filing under a region label nobody recognises. It is the check
to put on a timer: a silent page change keeps the parser perfectly happy while the numbers go wrong,
which is exactly what made the optional-columns bug hard to notice.

### Continuous integration

GitHub Actions (`.github/workflows/ci.yml`) runs both suites on every push to `main` and every
pull request, against Python 3.9, 3.10, 3.11, 3.12 and 3.13. 3.9 is the floor `pyproject.toml`
promises, so it is tested rather than assumed. A second job compares `uv.lock` with
`pyproject.toml` and fails the build when the lock is stale — a dependency added or removed
without re-locking breaks the build before anyone else runs it. Neither suite touches the network,
so CI needs no network access and no secrets. It runs the same two commands you do:

```bash
uv run python test_aion2.py
uv run python test_app.py
```

A green local run is the green CI will report.

### Releases

Pushing a tag such as `v1.0.0` starts `.github/workflows/release.yml`. It first checks that the tag
matches the `version` in `pyproject.toml`, so a `v1.0.0` tag on a tree that still says `0.9.0`
stops there instead of publishing a release that misstates what it contains. Then it runs both
suites, with the same commands CI uses. Only when the two agree and the checks pass does it publish
a GitHub Release with notes generated from the commits since the last tag. The order, then: bump
`version`, commit, tag, push the tag.

---
