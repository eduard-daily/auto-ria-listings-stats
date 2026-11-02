import sys

import pytest
from alembic import command
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from helpers import alembic_config
from ria_stats import api, collector, locking, photo_store, photos, seed, update  # noqa: F401 (imported so they exist)


def modules_with_a_session_factory():
    """Every ria_stats module that opens its own sessions, found by looking rather than by a list
    that someone has to remember to extend."""
    return [m for name, m in list(sys.modules.items()) if name.startswith("ria_stats") and hasattr(m, "SessionLocal")]


@pytest.fixture(autouse=True)
def never_touch_the_real_database(monkeypatch):
    """A test that does not use the `db` fixture must fail instead of quietly using data/ria.db."""

    def refuse(*args, **kwargs):
        raise RuntimeError("a test tried to open the real database; use the `db` fixture")

    for module in modules_with_a_session_factory():
        monkeypatch.setattr(module, "SessionLocal", refuse)


@pytest.fixture
def db(tmp_path, monkeypatch):
    """A fresh SQLite database built by the real migrations (so the views exist), seeded with
    Mazda MX-5. Returns the session factory; every module that opens sessions uses it."""
    path = tmp_path / "ria.db"
    monkeypatch.setattr("ria_stats.db.DB_PATH", path)  # alembic/env.py reads this when it runs
    command.upgrade(alembic_config(), "head")

    engine = create_engine(f"sqlite:///{path}")
    event.listen(engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
    session_factory = sessionmaker(engine)
    for module in modules_with_a_session_factory():
        monkeypatch.setattr(module, "SessionLocal", session_factory)
    monkeypatch.setattr(locking, "LOCK_PATH", tmp_path / "update.lock")
    monkeypatch.setattr(photo_store, "PHOTOS_DIR", tmp_path / "photos")

    with session_factory.begin() as session:
        seed.seed(session)
    return session_factory


@pytest.fixture
def age_days(db):
    """Moves everything recorded so far back in time, to simulate days passing."""

    def shift(days: int) -> None:
        with db.begin() as session:
            for table, column in (
                ("discovery_runs", "started_at"),
                ("collection_runs", "started_at"),
                ("listing_snapshots", "observed_at"),
                ("listings", "last_in_search_at"),
            ):
                session.execute(text(f"UPDATE {table} SET {column} = datetime({column}, '-{days} days')"))

    return shift
