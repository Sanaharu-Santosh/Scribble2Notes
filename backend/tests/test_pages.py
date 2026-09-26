"""Saving and reopening pages, against a real PostgreSQL.

Not SQLite standing in for it: the schema leans on JSONB and a descending
composite index, and a test suite that runs on a different database than
production is a test suite that agrees with you right up until deployment.

If Postgres isn't running these skip with instructions rather than failing —
the rest of the suite needs no database at all.
"""

from __future__ import annotations

import asyncio
import io
import os
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings
from app.db.session import get_engine, get_sessionmaker
from app.services.storage.registry import get_storage
from tests.conftest import use_settings

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://scribble:scribble@localhost:5432/scribble2notes_test",
)

SCENE = [
    {"id": "s2n:heading:b0", "type": "text", "x": 100, "y": 110, "text": "Unit 4"},
    {"id": "s2n:cell:b2:0:0", "type": "rectangle", "x": 100, "y": 450, "width": 340},
    {"id": "user-arrow", "type": "arrow", "x": 200, "y": 900, "points": [[0, 0], [80, 20]]},
]


async def _reset_database() -> None:
    """Empty the tables using a throwaway engine.

    Its own engine on purpose: the cached one belongs to whichever event loop
    the app runs in, and asyncpg connections do not survive being used from a
    different loop.
    """
    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("TRUNCATE pages, users CASCADE"))
    finally:
        await engine.dispose()


def _database_reachable() -> bool:
    try:
        asyncio.run(_reset_database())
    except Exception:
        return False
    return True


@pytest.fixture(scope="session")
def database_ready() -> bool:
    """Point the app at the test database once, for the whole session.

    Once, not per test: the engine holds a connection pool bound to the event
    loop it was created in, so rebuilding it between tests both leaks
    connections and risks using a pool from a loop that has closed.
    """
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    return _database_reachable()


@pytest.fixture
def db(database_ready, monkeypatch, tmp_path):
    if not database_ready:
        pytest.skip(
            "No test database. Start Postgres and run: "
            "alembic upgrade head (see README: Saving pages)"
        )

    # Not the database URL — that is fixed for the session above. These are the
    # per-test knobs: a private storage directory and a known user.
    use_settings(
        monkeypatch,
        storage_backend="local",
        storage_local_dir=str(tmp_path / "storage"),
        dev_user_email="tester@localhost",
    )
    get_storage.cache_clear()

    asyncio.run(_reset_database())
    yield
    get_storage.cache_clear()


def _new_page(client, **overrides):
    body = {"title": "Unit 4 notes", "page_width": 1240, "page_height": 1754, "scene": SCENE}
    body.update(overrides)
    response = client.post("/api/pages", json=body)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def page_png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (120, 160), "white").save(buffer, format="PNG")
    return buffer.getvalue()


# --------------------------------------------------------------------------
# Round trip
# --------------------------------------------------------------------------


def test_a_saved_page_comes_back_identical(db, client):
    """The scene is the document. If it doesn't round trip byte-for-byte, the
    user's edits are quietly being altered by the act of saving them."""
    created = _new_page(client)

    fetched = client.get(f"/api/pages/{created['id']}").json()

    assert fetched["scene"] == SCENE
    assert fetched["title"] == "Unit 4 notes"
    assert (fetched["page_width"], fetched["page_height"]) == (1240, 1754)


def test_the_list_omits_the_scene(db, client):
    """The scene is the large part and useless until a page is opened."""
    _new_page(client)

    listed = client.get("/api/pages").json()

    assert len(listed) == 1
    assert listed[0]["element_count"] == 3
    assert "scene" not in listed[0]


def test_pages_are_listed_newest_first(db, client):
    first = _new_page(client, title="Older")
    second = _new_page(client, title="Newer")

    listed = client.get("/api/pages").json()

    assert [page["title"] for page in listed] == ["Newer", "Older"]
    assert {page["id"] for page in listed} == {first["id"], second["id"]}


def test_saving_an_edit_replaces_the_scene(db, client):
    page = _new_page(client)
    edited = [*SCENE, {"id": "user-text", "type": "text", "text": "added later"}]

    updated = client.put(f"/api/pages/{page['id']}", json={"scene": edited}).json()

    assert updated["element_count"] == 4
    assert client.get(f"/api/pages/{page['id']}").json()["scene"] == edited


def test_renaming_does_not_require_resending_the_scene(db, client):
    page = _new_page(client)

    renamed = client.put(f"/api/pages/{page['id']}", json={"title": "Renamed"}).json()

    assert renamed["title"] == "Renamed"
    assert client.get(f"/api/pages/{page['id']}").json()["scene"] == SCENE


def test_deleting_a_page_makes_it_gone(db, client):
    page = _new_page(client)

    assert client.delete(f"/api/pages/{page['id']}").status_code == 204
    assert client.get(f"/api/pages/{page['id']}").status_code == 404
    assert client.get("/api/pages").json() == []


# --------------------------------------------------------------------------
# Scans go through the storage seam, not into the row
# --------------------------------------------------------------------------


def test_a_scan_can_be_stored_and_read_back(db, client, page_png):
    page = _new_page(client)

    uploaded = client.put(
        f"/api/pages/{page['id']}/scan", files={"file": ("page.png", page_png, "image/png")}
    ).json()
    assert uploaded["has_scan"] is True

    fetched = client.get(f"/api/pages/{page['id']}/scan")
    assert fetched.status_code == 200
    assert fetched.content == page_png


def test_a_page_without_a_scan_says_so(db, client):
    page = _new_page(client)

    assert client.get(f"/api/pages/{page['id']}").json()["has_scan"] is False
    assert client.get(f"/api/pages/{page['id']}/scan").status_code == 404


def test_deleting_a_page_takes_its_scan_with_it(db, client, page_png):
    """Otherwise every deleted page leaves its scan behind in storage forever."""
    page = _new_page(client)
    client.put(
        f"/api/pages/{page['id']}/scan", files={"file": ("page.png", page_png, "image/png")}
    )

    storage_dir = Path(get_settings().storage_local_dir)
    assert len(list(storage_dir.rglob("*.png"))) == 1

    client.delete(f"/api/pages/{page['id']}")

    assert list(storage_dir.rglob("*.png")) == []


# --------------------------------------------------------------------------
# Ownership — the schema is multi-user even though sign-in is not built
# --------------------------------------------------------------------------


def test_another_users_page_is_not_found(db, client, monkeypatch):
    """404 rather than 403: a 403 confirms the id exists, which is more than a
    stranger should learn."""
    page = _new_page(client)

    use_settings(monkeypatch, dev_user_email="someone-else@localhost")

    assert client.get(f"/api/pages/{page['id']}").status_code == 404
    assert client.get("/api/pages").json() == []


def test_another_user_cannot_overwrite_or_delete(db, client, monkeypatch):
    page = _new_page(client)
    use_settings(monkeypatch, dev_user_email="someone-else@localhost")

    assert client.put(f"/api/pages/{page['id']}", json={"title": "hijacked"}).status_code == 404
    assert client.delete(f"/api/pages/{page['id']}").status_code == 404
