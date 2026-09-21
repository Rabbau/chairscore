"""Enrichers fill every hole in the current season (not just recent matches), and
the coverage report shows what is still missing."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.ingest import football_data_co_uk as fdcouk_ingest
from app.models import Competition, Match, MatchTeamStat, Team
from app.providers.base import NTeamMatchStats
from app.report import coverage, render


@pytest.fixture
def mem():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with factory() as db:
        comp = Competition(
            provider_id=2021, code="PL", name="Premier League", type="LEAGUE",
            current_season="2026",
        )
        home = Team(provider_id=1, name="Home FC")
        away = Team(provider_id=2, name="Away FC")
        db.add_all([comp, home, away])
        db.flush()

        def match(pid, days_ago, season):
            db.add(Match(
                provider_id=pid, competition_id=comp.id, season=season,
                utc_date=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days_ago),
                status="FINISHED", home_team_id=home.id, away_team_id=away.id,
                home_score=1, away_score=0,
            ))

        match(101, days_ago=2, season="2026")  # just played
        match(102, days_ago=60, season="2026")  # older than any 14-day window, same season
        match(103, days_ago=200, season="2025")  # last season: not this run's business
        db.commit()
    yield factory
    engine.dispose()


class FakeCsv:
    """Stands in for the football-data.co.uk provider: every match is in the CSV."""

    closed = False

    def find_row(self, code, season, day, home, away):
        return {"row": True}

    @staticmethod
    def team_stats(row):
        return (
            NTeamMatchStats(shots=10, shots_on_target=4, corners=5, fouls=9),
            NTeamMatchStats(shots=6, shots_on_target=2, corners=1, fouls=12),
        )

    def close(self):
        self.closed = True


def test_fdcouk_fills_old_matches_of_the_current_season_only(mem, monkeypatch):
    monkeypatch.setattr(fdcouk_ingest, "SessionLocal", mem)
    monkeypatch.setattr(fdcouk_ingest, "get_fdcouk_provider", FakeCsv)

    assert fdcouk_ingest.enrich_fdcouk_matches() == 2

    with mem() as db:
        done = {
            m.provider_id: m.fdcouk_synced_at is not None for m in db.scalars(select(Match))
        }
        assert done == {101: True, 102: True, 103: False}
        assert len(db.scalars(select(MatchTeamStat)).all()) == 4  # two teams x two matches


def test_a_second_run_finds_nothing_left_to_fill(mem, monkeypatch):
    monkeypatch.setattr(fdcouk_ingest, "SessionLocal", mem)
    monkeypatch.setattr(fdcouk_ingest, "get_fdcouk_provider", FakeCsv)
    fdcouk_ingest.enrich_fdcouk_matches()
    assert fdcouk_ingest.enrich_fdcouk_matches() == 0


def test_the_per_run_budget_takes_the_newest_matches_first(mem, monkeypatch):
    monkeypatch.setattr(fdcouk_ingest, "SessionLocal", mem)
    monkeypatch.setattr(fdcouk_ingest, "get_fdcouk_provider", FakeCsv)
    monkeypatch.setattr(
        fdcouk_ingest, "settings",
        SimpleNamespace(
            tracked_competition_codes=["PL"], fdcouk_max_matches_per_run=1,
        ),
    )
    assert fdcouk_ingest.enrich_fdcouk_matches() == 1
    with mem() as db:
        synced = [m.provider_id for m in db.scalars(select(Match)) if m.fdcouk_synced_at]
        assert synced == [101]  # yesterday's game before the older one


def test_coverage_report_lists_the_holes(mem, monkeypatch):
    monkeypatch.setattr(fdcouk_ingest, "SessionLocal", mem)
    monkeypatch.setattr(fdcouk_ingest, "get_fdcouk_provider", FakeCsv)
    monkeypatch.setattr(
        fdcouk_ingest, "settings",
        SimpleNamespace(tracked_competition_codes=["PL"], fdcouk_max_matches_per_run=1),
    )
    fdcouk_ingest.enrich_fdcouk_matches()  # only the newest match gets its stats

    with mem() as db:
        report = coverage(db, "PL")
        assert (report["season"], report["finished"], report["with_stats"]) == ("2026", 2, 1)
        assert report["sources"] == {"football-data.co.uk": 1}
        assert report["fields"]["shots"] == 1 and report["fields"]["possession"] == 0
        assert [m.provider_id for m in report["bare"]] == [102]

        text = render(report, missing=5)
        assert "PL 2026: 2 finished matches" in text
        assert "team stats" in text and "no stats:" in text

        assert coverage(db, "NOPE") is None
