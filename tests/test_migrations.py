from alembic import command
from sqlalchemy import create_engine, text

from helpers import alembic_config


def test_migrations_apply_match_the_models_and_roll_back(tmp_path, monkeypatch):
    path = tmp_path / "migrations.db"
    monkeypatch.setattr("ria_stats.db.DB_PATH", path)
    config = alembic_config()

    command.upgrade(config, "head")
    command.check(config)  # raises when the models and the migrations have drifted apart
    command.downgrade(config, "base")

    with create_engine(f"sqlite:///{path}").connect() as connection:
        left = connection.execute(text("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")).scalars().all()
    assert left == ["alembic_version"]
