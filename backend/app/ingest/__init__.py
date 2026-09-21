"""Data ingestion: pull from a provider, upsert into the DB."""

from app.ingest.depth import enrich_depth_matches
from app.ingest.football_data_co_uk import enrich_fdcouk_matches
from app.ingest.fpl import enrich_fpl_matches
from app.ingest.sync import (
    run_full_sync,
    sync_recent_matches,
    sync_reference_data,
    sync_standings_and_scorers,
)
from app.ingest.uefa import enrich_uefa_matches, run_uefa_sync

__all__ = [
    "run_full_sync",
    "sync_recent_matches",
    "sync_reference_data",
    "sync_standings_and_scorers",
    "enrich_depth_matches",
    "enrich_fpl_matches",
    "enrich_fdcouk_matches",
    "enrich_uefa_matches",
    "run_uefa_sync",
]
