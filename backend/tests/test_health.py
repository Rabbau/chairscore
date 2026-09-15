def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["provider_token_configured"] is False


def test_competitions_seeded(client):
    r = client.get("/api/competitions")
    assert r.status_code == 200
    comps = r.json()
    codes = {c["code"] for c in comps}
    assert {"PL", "PD", "BL1", "SA", "FL1"}.issubset(codes)


def test_competition_detail_and_404(client):
    assert client.get("/api/competitions/PL").json()["name"] == "Premier League"
    assert client.get("/api/competitions/NOPE").status_code == 404


def test_empty_standings_ok(client):
    r = client.get("/api/competitions/PL/standings")
    assert r.status_code == 200
    assert r.json()["groups"] == []


def test_matches_feed_empty(client):
    r = client.get("/api/matches")
    assert r.status_code == 200
    assert r.json() == []


def test_seasons_endpoint_empty(client):
    r = client.get("/api/competitions/PL/seasons")
    assert r.status_code == 200
    assert r.json() == []


def test_search(client):
    assert client.get("/api/search", params={"q": "a"}).status_code == 422  # min_length

    r = client.get("/api/search", params={"q": "prem"})
    assert r.status_code == 200
    body = r.json()
    assert body["teams"] == []  # no teams seeded
    assert any(c["code"] == "PL" for c in body["competitions"])  # matches "Premier League"

    assert client.get("/api/search", params={"q": "zzzznope"}).json() == {
        "teams": [],
        "competitions": [],
    }


def test_match_detail_with_null_referees(db, client):
    """Match.referees is a nullable JSON column — None must not 500."""
    from datetime import datetime

    from app.models import Competition, Match, Team

    comp = db.query(Competition).filter_by(code="PL").one()
    home = Team(provider_id=900001, name="Test Town FC")
    away = Team(provider_id=900002, name="Test City FC")
    db.add_all([home, away])
    db.flush()
    match = Match(
        provider_id=900001,
        competition_id=comp.id,
        season="2026",
        utc_date=datetime(2026, 1, 1, 15, 0),
        status="FINISHED",
        home_team_id=home.id,
        away_team_id=away.id,
        home_score=1,
        away_score=0,
        referees=None,
    )
    db.add(match)
    db.commit()

    r = client.get(f"/api/matches/{match.id}")
    assert r.status_code == 200
    assert r.json()["referees"] == []
