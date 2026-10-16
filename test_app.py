"""Offline checks for the web API's character routes and error mapping.

Needs the dev dependency httpx (FastAPI's TestClient): `uv sync` installs it.
Run: uv run python test_app.py

The client functions app.py imports are swapped for fakes, so nothing touches
the network - these check routing, status codes and response shapes only.
"""

from __future__ import annotations

from contextlib import contextmanager

from fastapi.testclient import TestClient

import app
from aion2_api import Aion2ApiError, CharacterLookupError

client = TestClient(app.app)

S6X = {"character_id": "a=", "server_id": "1101", "region": "nae"}
HITS = [
    {"character_id": "a=", "name": "s6x", "level": 45, "server_id": "1101", "server_name": "Siel", "region": "nae"},
    {"character_id": "c=", "name": "s6x", "level": 24, "server_id": "1505", "server_name": "Yustiel", "region": "as"},
]
BOARDS = [{"id": 81, "name": "Nezekan", "openPercent": 49}, {"id": 82, "name": "Zikel", "openPercent": 43}]


@contextmanager
def fakes(**replacements):
    """Swap names in app's namespace (where the routes look them up) for a test."""
    real = {name: getattr(app, name) for name in replacements}
    for name, fake in replacements.items():
        setattr(app, name, fake)
    try:
        yield
    finally:
        for name, value in real.items():
            setattr(app, name, value)


def resolves_to(ids):
    return lambda name, server=None: dict(ids)


def raises(exc):
    def fake(*args, **kwargs):
        raise exc

    return fake


def info_with_boards(endpoint, character_id, server_id, region=None, timeout=25.0, **extra):
    assert endpoint == "info"
    return {"daevanion": {"boardList": BOARDS}}, region


def test_search_returns_hits_and_validates_region():
    seen = []

    def fake_search(name, region=None):
        seen.append((name, region))
        return HITS

    with fakes(search_characters=fake_search):
        r = client.get("/characters/search", params={"name": "s6x", "region": "nae"})
        assert r.status_code == 200, r.text
        assert [h["server_name"] for h in r.json()] == ["Siel", "Yustiel"]
        assert seen == [("s6x", "nae")]

        assert client.get("/characters/search", params={"name": "s6x", "region": "xx"}).status_code == 422
        assert client.get("/characters/search").status_code == 422, "name is required"


def test_character_passes_server_through():
    seen = []

    def fake_resolve(name, server=None):
        seen.append((name, server))
        return dict(S6X)

    with fakes(resolve_character=fake_resolve, get_character=lambda cid, sid, region: {"profile": {"characterName": "s6x"}}):
        r = client.get("/characters/s6x", params={"server": "Siel"})
        assert r.status_code == 200, r.text
        assert r.json() == {"profile": {"characterName": "s6x"}}
        assert seen == [("s6x", "Siel")]


def test_ambiguous_name_is_409_with_candidates():
    exc = CharacterLookupError("2 characters named 's6x': ...; pick a server", HITS)
    with fakes(resolve_character=raises(exc)):
        r = client.get("/characters/s6x")
        assert r.status_code == 409, r.text
        body = r.json()
        assert "pick a server" in body["detail"]
        assert [c["server_id"] for c in body["candidates"]] == ["1101", "1505"]


def test_unknown_name_is_404():
    with fakes(resolve_character=raises(CharacterLookupError("0 characters named 'nobody'", []))):
        for path in ("/characters/nobody", "/characters/nobody/daevanion", "/characters/nobody/daevanion/81"):
            r = client.get(path)
            assert r.status_code == 404, (path, r.text)
            assert "candidates" not in r.json()


def test_daevanion_board_list_and_one_board():
    fetched = []

    def fake_board(cid, sid, board_id, region=None):
        fetched.append(board_id)
        return {"nodeList": [{"row": 8, "col": 8, "type": "Start"}]}

    with fakes(
        resolve_character=resolves_to(S6X),
        character_endpoint=info_with_boards,
        get_daevanion_board=fake_board,
    ):
        r = client.get("/characters/s6x/daevanion")
        assert r.status_code == 200 and [b["name"] for b in r.json()] == ["Nezekan", "Zikel"], r.text

        for board in ("Nezekan", "nezekan", "81"):  # by name, any case, or by id
            r = client.get(f"/characters/s6x/daevanion/{board}")
            assert r.status_code == 200, (board, r.text)
            assert r.json()["board"]["id"] == 81
            assert r.json()["nodeList"][0]["type"] == "Start"
        assert fetched == [81, 81, 81]

        r = client.get("/characters/s6x/daevanion/nope")
        assert r.status_code == 404 and "Nezekan, Zikel" in r.json()["detail"], r.text
        assert fetched == [81, 81, 81], "an unknown board must not be fetched"


def test_upstream_errors_map_to_http_statuses():
    cases = [(404, 404), (403, 503), (429, 503), (500, 502), (0, 502)]
    for upstream, expected in cases:
        with fakes(resolve_character=resolves_to(S6X), get_character=raises(Aion2ApiError(upstream, "https://x", "boom"))):
            r = client.get("/characters/s6x")
            assert r.status_code == expected, (upstream, r.status_code, r.text)


def test_root_lists_character_routes():
    r = client.get("/")
    assert r.status_code == 200
    assert any("/characters/" in v for v in r.json()["how_to_use"].values())


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print(f"\n{len(tests)} route checks passed (offline, no network)")


if __name__ == "__main__":
    main()
