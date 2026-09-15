"""Guard: the migration chain must fully describe the ORM models."""

from __future__ import annotations

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine

from app import models  # noqa: F401  (registers mappers)
from app.db import Base
from app.migrations import alembic_config


def test_no_model_migration_drift(tmp_path):
    url = f"sqlite:///{tmp_path / 'drift.db'}"
    cfg = alembic_config()
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            ctx = MigrationContext.configure(
                conn, opts={"compare_type": True, "render_as_batch": True}
            )
            diffs = compare_metadata(ctx, Base.metadata)
    finally:
        engine.dispose()

    assert not diffs, (
        "Models and migrations disagree — run "
        "`alembic revision --autogenerate` and review:\n" + "\n".join(map(str, diffs))
    )
