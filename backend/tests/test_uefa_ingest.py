"""UEFA ingest on an in-memory database: recognising clubs the leagues already
created, idempotent upserts, and writing the lineups + event feed."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.ingest import uefa as ingest
from app.ingest.sync import upsert_match
from app.models import (
    Booking,
    Competition,
    CompetitionTeam,
    Goal,
    Match,
    MatchPlayerRating,
    MatchTeamStat,
    Substitution,
    Team,
    TeamExternalRef,
)
from app.providers.base import NTeam
from app.providers.uefa import UEFA_ID_OFFSET, build_depth, map_match

FIXTURES = Path(__file__).parent / "fixtures" / "uefa"
COMO, LEIPZIG = 79946, 2603790


def _fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def mem():
    """A throwaway database the ingest code can be pointed at."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with factory() as db:
        db.add(Competition(
            provider_id=2001, code="CL", name="UEFA Champions League", type="CUP",
            current_season="2026",
        ))
        db.commit()
    yield factory
    engine.dispose()


def _league_team(db, pid, name, short, tla):
    team = Team(provider_id=pid, name=name, short_name=short, tla=tla)
    db.add(team)
    db.flush()
    return team


def _uefa_team(uefa_id, name, short, tla, aliases, country):
    return NTeam(
        provider_id=UEFA_ID_OFFSET + uefa_id, name=name, short_name=short, tla=tla,
        area_name=country, aliases=aliases,
    )


# --------------------------------------------------------------------------- #
# matching clubs
# --------------------------------------------------------------------------- #
def test_matcher_links_known_clubs_and_creates_the_rest(mem):
    with mem() as db:
        psg = _league_team(db, 57, "Paris Saint-Germain FC", "PSG", "PSG")
        paris_fc = _league_team(db, 58, "Paris FC", "Paris FC", "PFC")
        inter = _league_team(db, 59, "FC Internazionale Milano", "Inter", "INT")
        db.commit()

        matcher = ingest.TeamMatcher()
        # UEFA lists PSG as plain "Paris" — the same spelling as Paris FC; the
        # three-letter code is what tells them apart.
        paris = _uefa_team(52747, "Paris Saint-Germain", "Paris", "PSG",
                           ["Paris Saint-Germain", "Paris"], "France")
        assert matcher(db, paris).id == psg.id != paris_fc.id
        milan_inter = _uefa_team(50138, "FC Internazionale Milano", "Inter", "INT",
                                 ["FC Internazionale Milano", "Inter"], "Italy")
        assert matcher(db, milan_inter).id == inter.id

        # a club with no league team becomes its own row, under UEFA's id
        sporting = _uefa_team(50149, "Sporting Clube de Portugal", "Sporting CP", "SCP",
                              ["Sporting Clube de Portugal", "Sporting CP"], "Portugal")
        created = matcher(db, sporting)
        assert created.provider_id == UEFA_ID_OFFSET + 50149
        assert matcher.created == ["Sporting Clube de Portugal"]

        # asking again — with this matcher or a fresh one — finds the same rows
        assert matcher(db, paris).id == psg.id
        assert ingest.TeamMatcher()(db, sporting).id == created.id
        refs = db.scalars(select(TeamExternalRef).where(TeamExternalRef.provider == "uefa")).all()
        assert sorted(r.external_id for r in refs) == [50138, 50149, 52747]


def test_matcher_will_not_guess_between_equally_good_candidates(mem):
    with mem() as db:
        _league_team(db, 71, "Real Union", "Real Union", "RUN")
        _league_team(db, 72, "Real Union Club", "Real Union Club", "RUC")
        db.commit()
        team = ingest.TeamMatcher()(
            db, _uefa_team(900, "Real Union", "Real Union", "XXX", ["Real Union"], "Spain")
        )
        assert team.provider_id == UEFA_ID_OFFSET + 900  # standalone rather than a coin-flip


def test_matcher_never_reuses_a_league_team_for_a_second_uefa_club(mem):
    with mem() as db:
        arsenal = _league_team(db, 11, "Arsenal FC", "Arsenal", "ARS")
        db.commit()
        matcher = ingest.TeamMatcher()
        def arsenal_from_uefa(uefa_id):
            return _uefa_team(uefa_id, "Arsenal FC", "Arsenal", "ARS", ["Arsenal FC"], "England")

        first = matcher(db, arsenal_from_uefa(1))
        second = matcher(db, arsenal_from_uefa(2))
        assert first.id == arsenal.id
        assert second.id != arsenal.id  # unique (team, provider) — the second one stands alone


# --------------------------------------------------------------------------- #
# breadth
# --------------------------------------------------------------------------- #
def test_upsert_is_idempotent_and_shares_teams_with_the_league(mem):
    raw = next(m for m in _fixture("matches.json") if m["id"] == "2049570")
    with mem() as db:
        como = _league_team(db, 450, "Como 1907", "Como", "COM")
        db.commit()
        matcher = ingest.TeamMatcher()

        first = upsert_match(db, map_match(raw, "CL"), matcher)
        db.commit()
        again = upsert_match(db, map_match(raw, "CL"), matcher)
        db.commit()

        assert first.id == again.id
        assert db.scalar(select(func.count(Match.id))) == 1
        assert first.home_team_id == como.id  # the league's Como, not a second one
        assert db.scalar(select(func.count(Team.id))) == 2  # Como + RB Leipzig
        assert (first.home_score, first.away_score, first.home_score_ht) == (4, 1, 2)
        assert first.provider_id == UEFA_ID_OFFSET + 2049570


def test_sync_links_teams_and_sets_the_current_matchday(mem):
    raw = _fixture("matches.json")
    matches = [map_match(m, "CL") for m in raw if m["id"] in ("2049570", "2049577")]

    class FakeProvider:
        def get_matches(self, code, season=None, date_from=None, date_to=None):
            return matches

    with mem() as db:
        ingest.sync_uefa_matches(db, FakeProvider(), ingest.TeamMatcher(), "CL", season="2026")

        assert db.scalar(select(func.count(Match.id))) == 2
        assert db.scalar(select(func.count(CompetitionTeam.id))) == 4  # two clubs per match
        # Como-Leipzig (matchday 1) is finished; the other one is still to come
        assert db.scalar(select(Competition.current_matchday).where(Competition.code == "CL")) == 1


# --------------------------------------------------------------------------- #
# depth
# --------------------------------------------------------------------------- #
class FakeUefa:
    codes = ["CL"]

    def __init__(self, depth):
        self.depth = depth
        self.calls = []

    def get_match_depth(self, provider_id, home_id=None, away_id=None):
        self.calls.append((provider_id, home_id, away_id))
        return self.depth

    def close(self):
        pass


def _seed_finished_match(db):
    comp = db.scalar(select(Competition).where(Competition.code == "CL"))
    como = _league_team(db, 450, "Como 1907", "Como", "COM")
    leipzig = _league_team(db, 451, "RB Leipzig", "Leipzig", "RBL")
    db.add_all([
        TeamExternalRef(team_id=como.id, provider="uefa", external_id=COMO),
        TeamExternalRef(team_id=leipzig.id, provider="uefa", external_id=LEIPZIG),
    ])
    match = Match(
        provider_id=UEFA_ID_OFFSET + 2049570, competition_id=comp.id, season="2026",
        utc_date=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1),
        status="FINISHED", home_team_id=como.id, away_team_id=leipzig.id,
        home_score=4, away_score=1,
    )
    db.add(match)
    db.commit()
    return match, como, leipzig


def _patch(monkeypatch, mem, fake):
    monkeypatch.setattr(ingest, "SessionLocal", mem)
    monkeypatch.setattr(ingest, "get_uefa_provider", lambda: fake)


def _counts(db):
    return [
        db.scalar(select(func.count()).select_from(t))
        for t in (Goal, Booking, Substitution, MatchTeamStat, MatchPlayerRating)
    ]


def test_enrich_writes_the_feed_and_replaces_rather_than_appends(mem, monkeypatch):
    depth = build_depth(_fixture("lineups.json"), _fixture("events.json"))
    fake = FakeUefa(depth)
    with mem() as db:
        match, como, leipzig = _seed_finished_match(db)
        match_id = match.id
    _patch(monkeypatch, mem, fake)

    assert ingest.enrich_uefa_matches() == 1
    assert fake.calls == [(UEFA_ID_OFFSET + 2049570, str(COMO), str(LEIPZIG))]

    with mem() as db:
        match = db.get(Match, match_id)
        assert match.uefa_synced_at is not None
        assert _counts(db) == [5, 5, 10, 2, 45]

        goal = db.scalars(select(Goal).where(Goal.minute == 38)).one()
        assert (goal.scorer_name, goal.assist_name, goal.home_score, goal.away_score) == (
            "Tasos Douvikas", "Martin Baturina", 2, 0,
        )
        assert goal.team_id == match.home_team_id  # mapped back onto *our* team ids
        stats = {s.team_id: s for s in db.scalars(select(MatchTeamStat))}
        assert stats[match.home_team_id].source == "uefa"
        home, away = stats[match.home_team_id], stats[match.away_team_id]
        assert (home.shots_on_target, away.corners) == (6, 5)
        match.uefa_synced_at = None  # force a re-run
        db.commit()

    assert ingest.enrich_uefa_matches() == 1
    with mem() as db:
        assert _counts(db) == [5, 5, 10, 2, 45]  # replaced, not doubled


def test_enrich_leaves_an_unfinished_feed_for_the_next_run(mem, monkeypatch):
    opening_minutes = _fixture("events.json")[-20:]  # the feed is newest-first: no full time here
    depth = build_depth(_fixture("lineups.json"), opening_minutes)
    assert not depth.complete
    with mem() as db:
        match, *_ = _seed_finished_match(db)
        match_id = match.id
    _patch(monkeypatch, mem, FakeUefa(depth))

    assert ingest.enrich_uefa_matches() == 0
    with mem() as db:
        assert db.get(Match, match_id).uefa_synced_at is None
        assert _counts(db) == [0, 0, 0, 0, 0]


def test_enrich_skips_a_match_whose_team_has_no_uefa_id(mem, monkeypatch):
    depth = build_depth(_fixture("lineups.json"), _fixture("events.json"))
    with mem() as db:
        match, como, _ = _seed_finished_match(db)
        db.query(TeamExternalRef).filter_by(team_id=como.id).delete()
        db.commit()
    fake = FakeUefa(depth)
    _patch(monkeypatch, mem, fake)

    assert ingest.enrich_uefa_matches() == 0
    assert fake.calls == []
