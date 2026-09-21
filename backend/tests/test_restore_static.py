"""Restoring enrichment from an export: the round trip must put back exactly
what ``export_static`` wrote, onto a database whose internal ids are different."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.restore_static as restore
from app.api.matches import get_match
from app.db import Base
from app.ingest.uefa import _write_depth
from app.models import (
    Booking,
    Competition,
    Goal,
    Match,
    MatchPlayerRating,
    MatchTeamStat,
    Substitution,
    Team,
)
from app.providers.uefa import UEFA_ID_OFFSET, build_depth, team_pid

FIXTURES = Path(__file__).parent / "fixtures" / "uefa"
COMO, LEIPZIG = 79946, 2603790
MATCH_PID = UEFA_ID_OFFSET + 2049570


def _new_db(pad_teams: int = 0):
    """An empty database with Como, Leipzig and their (unenriched) match.
    ``pad_teams`` shifts the auto-increment ids, so the two databases disagree
    about what "team 3" is — as a rebuilt database really would."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with factory() as db:
        for i in range(pad_teams):
            db.add(Team(provider_id=9000 + i, name=f"Filler {i}"))
        comp = Competition(provider_id=2001, code="CL", name="UEFA Champions League", type="CUP")
        como = Team(provider_id=450, name="Como 1907", short_name="Como", tla="COM")
        leipzig = Team(provider_id=451, name="RB Leipzig", short_name="Leipzig", tla="RBL")
        db.add_all([comp, como, leipzig])
        db.flush()
        db.add(Match(
            provider_id=MATCH_PID, competition_id=comp.id, season="2026",
            utc_date=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30),
            status="FINISHED", home_team_id=como.id, away_team_id=leipzig.id,
            home_score=4, away_score=1,
        ))
        db.commit()
    return factory, engine


def _enriched_export():
    """What export_static would have written for a fully enriched match."""
    factory, engine = _new_db()
    depth = build_depth(
        json.loads((FIXTURES / "lineups.json").read_text(encoding="utf-8")),
        json.loads((FIXTURES / "events.json").read_text(encoding="utf-8")),
    )
    with factory() as db:
        match = db.scalar(select(Match))
        tmap = {team_pid(COMO): match.home_team_id, team_pid(LEIPZIG): match.away_team_id}
        _write_depth(db, match, depth, tmap)
        # two more sources, as a Premier League match would have
        db.add(MatchTeamStat(
            match_id=match.id, team_id=match.home_team_id, source="football-data.co.uk",
            shots=20, xg=1.9,
        ))
        db.add(MatchPlayerRating(
            match_id=match.id, team_id=match.away_team_id, source="fpl",
            player_name="Some Player", bps=31, bonus=2,
        ))
        db.commit()
        doc = get_match(match.id, db=db).model_dump(mode="json")
    engine.dispose()
    return doc


@pytest.fixture(scope="module")
def doc():
    return _enriched_export()


def _counts(db):
    return [
        db.scalar(select(func.count()).select_from(t))
        for t in (Goal, Booking, Substitution, MatchTeamStat, MatchPlayerRating)
    ]


def test_round_trip_restores_everything_onto_different_ids(doc):
    factory, engine = _new_db(pad_teams=5)
    with factory() as db:
        added = restore.restore_match(db, doc)
        db.commit()

        assert dict(added) == {
            "goals": 5, "bookings": 5, "substitutions": 10, "team stats": 3, "players": 46,
        }
        match = db.scalar(select(Match))
        assert _counts(db) == [5, 5, 10, 3, 46]

        # stored against *this* database's team ids, not the export's
        assert doc["home_team"]["id"] != match.home_team_id
        goal = db.scalars(select(Goal).where(Goal.minute == 38)).one()
        assert goal.team_id == match.home_team_id
        assert (goal.scorer_name, goal.assist_name) == ("Tasos Douvikas", "Martin Baturina")
        by_source = {(s.source, s.team_id): s for s in db.scalars(select(MatchTeamStat))}
        assert by_source[("football-data.co.uk", match.home_team_id)].xg == 1.9
        assert by_source[("uefa", match.away_team_id)].corners == 5
        fpl = db.scalars(select(MatchPlayerRating).where(MatchPlayerRating.source == "fpl")).one()
        assert (fpl.team_id, fpl.bps, fpl.bonus) == (match.away_team_id, 31, 2)

        # the enrichers are told these sources are done for this match
        assert match.uefa_synced_at and match.fdcouk_synced_at and match.fpl_synced_at
        assert match.depth_synced_at is None  # api-football contributed nothing
    engine.dispose()


def test_restore_is_idempotent(doc):
    factory, engine = _new_db()
    with factory() as db:
        restore.restore_match(db, doc)
        db.commit()
        assert not restore.restore_match(db, doc)  # nothing left to add
        db.commit()
        assert _counts(db) == [5, 5, 10, 3, 46]
    engine.dispose()


def test_restore_never_overwrites_what_the_database_already_has(doc):
    factory, engine = _new_db()
    with factory() as db:
        match = db.scalar(select(Match))
        db.add(Goal(match_id=match.id, minute=1, scorer_name="Fresher Data"))
        db.add(MatchTeamStat(
            match_id=match.id, team_id=match.home_team_id, source="uefa", shots=99,
        ))
        db.commit()

        added = restore.restore_match(db, doc)
        db.commit()

        assert "goals" not in added  # the match already had goals: left alone
        assert db.scalars(select(Goal.scorer_name)).all() == ["Fresher Data"]
        assert db.scalar(
            select(MatchTeamStat.shots).where(
                MatchTeamStat.source == "uefa", MatchTeamStat.team_id == match.home_team_id
            )
        ) == 99
        assert added["team stats"] == 2  # the other uefa row + the fdcouk one
    engine.dispose()


def test_a_match_the_database_does_not_know_is_skipped(doc):
    factory, engine = _new_db()
    with factory() as db:
        assert restore.restore_match(db, {**doc, "provider_id": 12345}) == {"match not in db": 1}
        other_side = {**doc, "home_team": {**doc["home_team"], "provider_id": 777}}
        assert restore.restore_match(db, other_side) == {"team mismatch": 1}
        assert _counts(db) == [0, 0, 0, 0, 0]
    engine.dispose()


def test_run_reads_the_export_folder(doc, tmp_path, monkeypatch):
    matches = tmp_path / "matches"
    matches.mkdir()
    (matches / "1.json").write_text(json.dumps(doc), encoding="utf-8")
    (matches / "window.json").write_text("[]", encoding="utf-8")  # not a match
    (matches / "2.json").write_text("{not json", encoding="utf-8")

    factory, engine = _new_db()
    monkeypatch.setattr(restore, "SessionLocal", factory)
    total = restore.run(tmp_path)

    assert (total["files"], total["errors"]) == (1, 1)
    assert total["goals"] == 5
    with factory() as db:
        assert _counts(db) == [5, 5, 10, 3, 46]
    engine.dispose()
