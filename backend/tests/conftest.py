from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# Configure the app for tests BEFORE anything imports app.config.
_db_fd, _db_path = tempfile.mkstemp(suffix=".db", prefix="chairscore_test_")
os.close(_db_fd)
os.environ.update(
    DATABASE_URL=f"sqlite:///{_db_path}",
    ENABLE_SCHEDULER="false",
    SYNC_ON_STARTUP="false",
    RUN_MIGRATIONS_ON_STARTUP="false",
    FOOTBALL_DATA_API_TOKEN="",
    CORS_ORIGINS="http://testserver",
)

from fastapi.testclient import TestClient  # noqa: E402

from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.migrations import run_migrations  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    run_migrations()  # build the test DB from the migration chain
    yield
    engine.dispose()  # release the SQLite file handle before unlink (Windows)
    try:
        Path(_db_path).unlink(missing_ok=True)
    except PermissionError:
        pass


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
