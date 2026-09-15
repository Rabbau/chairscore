from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import routers
from app.config import settings
from app.migrations import run_migrations
from app.seed import seed_competitions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("chairscore")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.run_migrations_on_startup:
        run_migrations()
    seed_competitions()

    if settings.sync_on_startup and settings.football_data_api_token:
        from app.ingest.sync import run_full_sync

        try:
            run_full_sync()
        except Exception:  # noqa: BLE001
            log.exception("startup sync failed")

    scheduler = None
    if settings.enable_scheduler and settings.football_data_api_token:
        from app.ingest.scheduler import shutdown_scheduler, start_scheduler

        scheduler = start_scheduler()
    elif settings.enable_scheduler:
        log.warning("scheduler disabled: FOOTBALL_DATA_API_TOKEN is not set")

    yield

    if scheduler is not None:
        from app.ingest.scheduler import shutdown_scheduler

        shutdown_scheduler()


app = FastAPI(title="Chairscore API", version=__version__, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in routers:
    app.include_router(router)


@app.get("/api/health", tags=["meta"])
def health():
    return {
        "status": "ok",
        "version": __version__,
        "provider_token_configured": bool(settings.football_data_api_token),
        "tracked_competitions": settings.tracked_competition_codes,
    }


@app.get("/", include_in_schema=False)
def root():
    return {"name": "Chairscore API", "docs": "/docs", "health": "/api/health"}
