"""Alembic environment — wired to app settings and models."""

from __future__ import annotations

import logging
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app import models  # noqa: F401  (import registers every mapper)
from app.config import settings
from app.db import Base

config = context.config
# A caller (app.migrations, tests) may set the URL explicitly; only fall back to
# app settings when it hasn't.
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", settings.database_url)

# Only let Alembic reconfigure logging when it owns the process (the `alembic`
# CLI). Embedded — app.migrations on startup, the ingest CLI, tests — the app has
# already set up logging, and fileConfig() would silence the app's own loggers.
if config.config_file_name is not None and not logging.getLogger().handlers:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_db_url = config.get_main_option("sqlalchemy.url") or ""
# SQLite can't ALTER most columns — Alembic emits copy-and-move "batch" ops instead.
_render_as_batch = _db_url.startswith("sqlite")


def run_migrations_offline() -> None:
    context.configure(
        url=_db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=_render_as_batch,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=_render_as_batch,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
