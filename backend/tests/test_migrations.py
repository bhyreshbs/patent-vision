from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.core.database import Base

BACKEND = Path(__file__).resolve().parents[1]


def _config(db_url: str) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_migration_matches_models_and_downgrades(tmp_path):
    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    command.upgrade(_config(url), "head")

    insp = inspect(create_engine(url))
    tables = set(insp.get_table_names()) - {"alembic_version"}
    assert tables == set(Base.metadata.tables)
    for name, table in Base.metadata.tables.items():
        assert {c["name"] for c in insp.get_columns(name)} == {c.name for c in table.columns}, name
        fk_targets = {fk["referred_table"] for fk in insp.get_foreign_keys(name)}
        assert fk_targets == {fk.column.table.name for c in table.columns for fk in c.foreign_keys}, name

    command.downgrade(_config(url), "base")
    assert set(inspect(create_engine(url)).get_table_names()) - {"alembic_version"} == set()
