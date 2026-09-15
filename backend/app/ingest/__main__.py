"""CLI entry point:  python -m app.ingest [--full|--matches|--standings|--reference|--depth]

Examples
--------
    python -m app.ingest --full                 # everything, tracked competitions
    python -m app.ingest --full --code PL,PD     # everything, just these
    python -m app.ingest --matches              # recent-window matches only
    python -m app.ingest --standings            # standings + scorers only
    python -m app.ingest --depth                # API-Football events/stats/ratings
    python -m app.ingest --fpl                  # FPL per-player data (current PL season)
    python -m app.ingest --fdcouk               # Football-Data.co.uk match stats (all leagues)
    python -m app.ingest --seasons 2023,2024    # backfill past-season results
"""

from __future__ import annotations

import argparse
import logging

from app.config import settings
from app.ingest.depth import enrich_depth_matches
from app.ingest.football_data_co_uk import enrich_fdcouk_matches
from app.ingest.fpl import enrich_fpl_matches
from app.ingest.sync import (
    run_full_sync,
    sync_history,
    sync_recent_matches,
    sync_reference_data,
    sync_standings_and_scorers,
)
from app.migrations import run_migrations
from app.seed import seed_competitions


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.ingest", description="Chairscore data ingestion")
    parser.add_argument("--full", action="store_true", help="full sync (default if no flag)")
    parser.add_argument("--matches", action="store_true", help="recent-window matches only")
    parser.add_argument("--standings", action="store_true", help="standings + scorers only")
    parser.add_argument("--reference", action="store_true", help="competitions + teams only")
    parser.add_argument(
        "--depth", action="store_true",
        help="enrich recent matches with API-Football events / stats / ratings",
    )
    parser.add_argument(
        "--fpl", action="store_true",
        help="enrich recent PL matches with FPL per-player data",
    )
    parser.add_argument(
        "--fdcouk", action="store_true",
        help="enrich recent matches with Football-Data.co.uk team stats (all tracked leagues)",
    )
    parser.add_argument(
        "--seasons", help="comma-separated past seasons to backfill, e.g. 2023,2024",
    )
    parser.add_argument("--code", help="comma-separated competition codes (overrides .env)")
    parser.add_argument("-q", "--quiet", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    run_migrations()
    seed_competitions()

    codes = [c.strip().upper() for c in args.code.split(",")] if args.code else None

    if args.seasons:
        sync_history([s.strip() for s in args.seasons.split(",") if s.strip()], codes)
    elif args.matches:
        sync_recent_matches()
    elif args.standings:
        sync_standings_and_scorers()
    elif args.reference:
        sync_reference_data()
    elif args.depth:
        enrich_depth_matches()
    elif args.fpl:
        enrich_fpl_matches()
    elif args.fdcouk:
        enrich_fdcouk_matches()
    else:
        run_full_sync(codes)

    print("done. tracked competitions:", ", ".join(codes or settings.tracked_competition_codes))


if __name__ == "__main__":
    main()
