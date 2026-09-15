"""Programmatic Alembic access — used on startup and by the ingest CLI."""

from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect

from app.config import settings
from app.db import engine

log = logging.getLogger("chairscore.migrations")


def _backend_root() -> Path:
    """Directory holding alembic.ini + alembic/. Package-relative for an editable
    install; falls back to CWD (the image WORKDIR) for a plain `pip install .`."""
    pkg_root = Path(__file__).resolve().parent.parent
    if (pkg_root / "alembic.ini").exists():
        return pkg_root
    return Path.cwd()


def alembic_config() -> Config:
    root = _backend_root()
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    return cfg


def _head_revision(cfg: Config) -> str | None:
    return ScriptDirectory.from_config(cfg).get_current_head()


def _current_revision() -> str | None:
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def run_migrations() -> None:
    """Bring the database up to head.

    Handles the one-off transition from a `create_all()` database (tables exist,
    no ``alembic_version``) by stamping it at head instead of trying to recreate
    tables.
    """
    cfg = alembic_config()

    with engine.connect() as conn:
        names = set(inspect(conn).get_table_names())
    has_schema = "competitions" in names
    has_version = "alembic_version" in names

    if has_schema and not has_version:
        log.info("existing schema without migration history — stamping at head")
        command.stamp(cfg, "head")
        return

    if _current_revision() == _head_revision(cfg):
        return

    log.info("running database migrations")
    command.upgrade(cfg, "head")
