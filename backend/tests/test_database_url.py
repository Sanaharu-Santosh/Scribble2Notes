"""Connection strings copied from a hosting provider have to just work.

Each case here is a real URL shape a provider hands out, and each failure mode
it guards is one that surfaces at deploy time with a message that does not
mention the URL at all.
"""

from __future__ import annotations

import pytest

from app.config import normalize_database_url


def test_the_sync_scheme_is_switched_to_the_async_driver():
    """Providers hand out postgres:// or postgresql://. Left alone, SQLAlchemy
    loads the sync driver and the app dies on the first query with
    'greenlet_spawn has not been called' — which says nothing about the URL."""
    assert normalize_database_url("postgres://u:p@host/db").startswith("postgresql+asyncpg://")
    assert normalize_database_url("postgresql://u:p@host/db").startswith("postgresql+asyncpg://")


def test_an_explicit_driver_is_left_alone():
    url = "postgresql+asyncpg://u:p@host/db"
    assert normalize_database_url(url) == url


def test_sslmode_is_renamed_to_the_parameter_asyncpg_accepts():
    """asyncpg takes the same values under the name `ssl`; given `sslmode` it
    raises TypeError: unexpected keyword argument."""
    result = normalize_database_url("postgresql://u:p@host/db?sslmode=require")

    assert "ssl=require" in result
    assert "sslmode" not in result


@pytest.mark.parametrize("mode", ["disable", "allow", "prefer", "require", "verify-full"])
def test_every_sslmode_value_survives_the_rename(mode):
    assert f"ssl={mode}" in normalize_database_url(f"postgresql://u:p@host/db?sslmode={mode}")


def test_channel_binding_is_dropped():
    """Neon includes it; asyncpg rejects it and negotiates channel binding
    itself."""
    result = normalize_database_url(
        "postgresql://u:p@host/db?sslmode=require&channel_binding=require"
    )

    assert "channel_binding" not in result
    assert "ssl=require" in result


def test_a_full_neon_url_comes_out_usable():
    neon = (
        "postgresql://sanah:secret@ep-cool-name-123.ap-southeast-1.aws.neon.tech/"
        "scribble2notes?sslmode=require&channel_binding=require"
    )

    result = normalize_database_url(neon)

    assert result.startswith("postgresql+asyncpg://")
    assert "ep-cool-name-123.ap-southeast-1.aws.neon.tech" in result
    assert result.endswith("?ssl=require")


def test_other_parameters_are_preserved():
    result = normalize_database_url("postgresql://u:p@host/db?application_name=scribble")
    assert "application_name=scribble" in result


def test_credentials_and_path_are_untouched():
    result = normalize_database_url("postgresql://user:p%40ss@host:5433/my_db")

    assert "user:p%40ss@host:5433" in result
    assert result.endswith("/my_db")
