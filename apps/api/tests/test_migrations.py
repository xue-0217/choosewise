from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from app.db import Base


def test_initial_migration_matches_models_and_can_reverse(tmp_path, monkeypatch):
    url = f'sqlite:///{tmp_path / "migration.db"}'
    monkeypatch.setenv('DATABASE_URL', url)
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    command.upgrade(config, 'head')
    engine = create_engine(url)
    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
    assert 'recommendation_snapshots' in inspect(engine).get_table_names()
    engine.dispose()
    command.downgrade(config, 'base')
    engine = create_engine(url)
    assert set(inspect(engine).get_table_names()) == {'alembic_version'}
    engine.dispose()
