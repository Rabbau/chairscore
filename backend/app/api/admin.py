from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query

from app.config import settings
from app.ingest.depth import enrich_depth_matches
from app.ingest.football_data_co_uk import enrich_fdcouk_matches
from app.ingest.fpl import enrich_fpl_matches
from app.ingest.sync import (
    run_full_sync,
    sync_recent_matches,
    sync_reference_data,
    sync_standings_and_scorers,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])

_JOBS = {
    "full": run_full_sync,
    "matches": sync_recent_matches,
    "standings": sync_standings_and_scorers,
    "reference": sync_reference_data,
    "depth": enrich_depth_matches,
    "fpl": enrich_fpl_matches,
    "fdcouk": enrich_fdcouk_matches,
}


@router.post("/sync")
def trigger_sync(
    background: BackgroundTasks,
    mode: str = Query("full", pattern="^(full|matches|standings|reference|depth|fpl|fdcouk)$"),
    x_admin_token: str = Header(default=""),
):
    if not settings.admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(401, "bad or missing X-Admin-Token")
    background.add_task(_JOBS[mode])
    return {"status": "scheduled", "mode": mode}
