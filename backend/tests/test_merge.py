"""Folding several sources' team stats into one row per team."""

from types import SimpleNamespace

from app.merge import STAT_FIELDS, merge_team_stats


def row(team_id, source, **stats):
    fields = {**dict.fromkeys(STAT_FIELDS), "team_id": team_id, "source": source, **stats}
    return SimpleNamespace(**fields)


def test_a_single_source_passes_through():
    (m,) = merge_team_stats([row(1, "uefa", shots=12, corners=3)])
    assert (m["team_id"], m["shots"], m["corners"], m["possession"]) == (1, 12, 3, None)
    assert m["sources"] == ["uefa"]
    assert m["field_sources"] == {"shots": "uefa", "corners": "uefa"}


def test_holes_are_filled_from_other_sources():
    # Premier League: Football-Data.co.uk has shots + xG, FPL has saves + its own xG
    rows = [
        row(1, "fpl", xg=2.07, saves=4),
        row(1, "football-data.co.uk", shots=15, corners=5, xg=1.91),
    ]
    (m,) = merge_team_stats(rows)
    assert (m["shots"], m["corners"], m["saves"]) == (15, 5, 4)  # one from each
    assert m["xg"] == 1.91  # the more trusted source wins the overlap
    assert m["field_sources"]["saves"] == "fpl"
    assert m["field_sources"]["xg"] == "football-data.co.uk"
    assert m["sources"] == ["football-data.co.uk", "fpl"]  # most trusted first


def test_input_order_does_not_matter():
    a = row(1, "football-data.co.uk", shots=10, xg=1.0)
    b = row(1, "fpl", shots=99, xg=9.0, saves=2)
    assert merge_team_stats([a, b]) == merge_team_stats([b, a])


def test_teams_are_kept_apart():
    merged = merge_team_stats([row(1, "uefa", shots=5), row(2, "uefa", shots=8)])
    assert {m["team_id"]: m["shots"] for m in merged} == {1: 5, 2: 8}


def test_zero_is_a_value_not_a_hole():
    (m,) = merge_team_stats([
        row(1, "football-data.co.uk", red_cards=0),
        row(1, "fpl", red_cards=1),
    ])
    assert m["red_cards"] == 0  # a real "no red cards" isn't overridden by a later source


def test_unknown_sources_rank_last_and_rows_without_a_team_are_dropped():
    merged = merge_team_stats([
        row(1, "some-new-source", shots=1, corners=7),
        row(1, "uefa", shots=2),
        row(None, "uefa", shots=50),
    ])
    assert len(merged) == 1
    assert (merged[0]["shots"], merged[0]["corners"]) == (2, 7)
    assert merged[0]["sources"] == ["uefa", "some-new-source"]


def test_match_detail_endpoint_carries_the_merged_rows(db, client):
    from datetime import datetime

    from app.models import Competition, Match, MatchTeamStat, Team

    comp = db.query(Competition).filter_by(code="PL").one()
    home = Team(provider_id=910001, name="Merge Town FC")
    away = Team(provider_id=910002, name="Merge City FC")
    db.add_all([home, away])
    db.flush()
    match = Match(
        provider_id=910001, competition_id=comp.id, season="2026",
        utc_date=datetime(2026, 1, 2, 15, 0), status="FINISHED",
        home_team_id=home.id, away_team_id=away.id, home_score=2, away_score=0,
    )
    db.add(match)
    db.flush()
    db.add_all([
        MatchTeamStat(match_id=match.id, team_id=home.id, source="fpl", xg=1.5, saves=3),
        MatchTeamStat(
            match_id=match.id, team_id=home.id, source="football-data.co.uk", shots=14, xg=1.2
        ),
    ])
    db.commit()

    body = client.get(f"/api/matches/{match.id}").json()
    assert len(body["team_stats"]) == 2  # the raw rows stay available
    (merged,) = body["merged_team_stats"]
    assert (merged["team_id"], merged["shots"], merged["saves"], merged["xg"]) == (
        home.id, 14, 3, 1.2,
    )
    assert merged["sources"] == ["football-data.co.uk", "fpl"]
