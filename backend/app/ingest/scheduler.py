"""APScheduler jobs for periodic data refresh.

The free tier allows ~10 requests/minute, so jobs must not overlap. We run a
single one-shot sequential sync ~15s after boot, then space the recurring
refreshers out on their own intervals (first run == one full interval later,
so nothing stampedes at startup).

Cadence (see .env):
* matches in a date window   - every 15 min
* standings + scorers        - every 6h
* reference data (teams)     - every 24h
* UEFA fixtures + depth      - every 30 min (Champions / Europa League)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.ingest.depth import enrich_depth_matches
from app.ingest.football_data_co_uk import enrich_fdcouk_matches
from app.ingest.fpl import enrich_fpl_matches
from app.ingest.sync import (
    sync_recent_matches,
    sync_reference_data,
    sync_standings_and_scorers,
)
from app.ingest.uefa import run_uefa_sync
from app.providers import (
    get_depth_provider,
    get_fdcouk_provider,
    get_fpl_provider,
    get_uefa_provider,
)

log = logging.getLogger("chairscore.scheduler")

_scheduler: BackgroundScheduler | None = None


def _safe(fn):
    def wrapper():
        try:
            fn()
        except Exception:  # noqa: BLE001 - a failed run must not kill the scheduler
            log.exception("scheduled job %s failed", getattr(fn, "__name__", fn))

    wrapper.__name__ = getattr(fn, "__name__", "job")
    return wrapper


def _initial_sync() -> None:
    """One-shot, sequential — safe on the rate limit."""
    log.info("initial sync starting")
    steps = [sync_reference_data, sync_standings_and_scorers, sync_recent_matches]
    if get_depth_provider() is not None:
        steps.append(enrich_depth_matches)
    if get_fpl_provider() is not None:
        steps.append(enrich_fpl_matches)
    if get_fdcouk_provider() is not None:
        steps.append(enrich_fdcouk_matches)
    if get_uefa_provider() is not None:
        steps.append(run_uefa_sync)
    for step in steps:
        try:
            step()
        except Exception:  # noqa: BLE001
            log.exception("initial sync step %s failed", step.__name__)
    log.info("initial sync done")


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    sched = BackgroundScheduler(timezone="UTC")
    now = datetime.now(UTC)
    m = settings.sync_matches_minutes

    sched.add_job(
        _safe(_initial_sync), "date",
        run_date=now + timedelta(seconds=15), id="initial",
    )
    sched.add_job(
        _safe(sync_recent_matches), "interval",
        minutes=m, id="matches",
        next_run_time=now + timedelta(minutes=m),
        max_instances=1, coalesce=True,
    )
    sched.add_job(
        _safe(sync_standings_and_scorers), "interval",
        hours=settings.sync_standings_hours, id="standings",
        next_run_time=now + timedelta(hours=settings.sync_standings_hours),
        max_instances=1, coalesce=True,
    )
    sched.add_job(
        _safe(sync_reference_data), "interval",
        hours=settings.sync_reference_hours, id="reference",
        next_run_time=now + timedelta(hours=settings.sync_reference_hours),
        max_instances=1, coalesce=True,
    )
    if get_depth_provider() is not None:
        dh = settings.sync_depth_hours
        sched.add_job(
            _safe(enrich_depth_matches), "interval",
            hours=dh, id="depth",
            next_run_time=now + timedelta(hours=dh),
            max_instances=1, coalesce=True,
        )
    if get_fpl_provider() is not None:
        fh = settings.sync_fpl_hours
        sched.add_job(
            _safe(enrich_fpl_matches), "interval",
            hours=fh, id="fpl",
            next_run_time=now + timedelta(hours=fh),
            max_instances=1, coalesce=True,
        )
    if get_fdcouk_provider() is not None:
        ch = settings.sync_fdcouk_hours
        sched.add_job(
            _safe(enrich_fdcouk_matches), "interval",
            hours=ch, id="fdcouk",
            next_run_time=now + timedelta(hours=ch),
            max_instances=1, coalesce=True,
        )
    if get_uefa_provider() is not None:
        um = settings.sync_uefa_minutes
        sched.add_job(
            _safe(run_uefa_sync), "interval",
            minutes=um, id="uefa",
            next_run_time=now + timedelta(minutes=um),
            max_instances=1, coalesce=True,
        )
    sched.start()
    _scheduler = sched
    log.info(
        "scheduler started (initial in 15s; then matches/%dm, standings/%dh, "
        "reference/%dh%s%s%s%s)",
        m, settings.sync_standings_hours, settings.sync_reference_hours,
        f", depth/{settings.sync_depth_hours}h" if get_depth_provider() is not None else "",
        f", fpl/{settings.sync_fpl_hours}h" if get_fpl_provider() is not None else "",
        f", fdcouk/{settings.sync_fdcouk_hours}h" if get_fdcouk_provider() is not None else "",
        f", uefa/{settings.sync_uefa_minutes}m" if get_uefa_provider() is not None else "",
    )
    return sched


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
