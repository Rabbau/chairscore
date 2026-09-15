"""API-Football (api-sports.io) v3 provider — the "depth" source.

Docs: https://www.api-football.com/documentation-v3
Direct plan (dashboard.api-football.com): base ``https://v3.football.api-sports.io``,
auth header ``x-apisports-key``. Free plan: 100 requests/day, 10/minute.

Adds match events, per-team statistics and player ratings on top of the breadth
data from football-data.org. Also implements the full breadth interface so it can
run a competition on its own where the plan allows.
"""

from __future__ import annotations

import logging
import re
import time
import unicodedata
from datetime import UTC, date, datetime

import httpx

from app.providers.base import (
    BaseProvider,
    NBooking,
    NCompetition,
    NGoal,
    NMatch,
    NPlayerRating,
    NScorer,
    NStandingRow,
    NStandings,
    NSubstitution,
    NTeam,
    NTeamMatchStats,
    ProviderError,
)
from app.providers.leagues import to_league_id

log = logging.getLogger("chairscore.provider.api_football")

# API-Football fixture status.short  ->  our status
_STATUS = {
    "TBD": "SCHEDULED", "NS": "SCHEDULED",
    "1H": "IN_PLAY", "2H": "IN_PLAY", "ET": "IN_PLAY", "BT": "IN_PLAY",
    "P": "IN_PLAY", "LIVE": "IN_PLAY", "INT": "IN_PLAY",
    "HT": "PAUSED",
    "FT": "FINISHED", "AET": "FINISHED", "PEN": "FINISHED",
    "SUSP": "SUSPENDED",
    "PST": "POSTPONED",
    "CANC": "CANCELLED", "ABD": "CANCELLED",
    "AWD": "AWARDED", "WO": "AWARDED",
}
_FINISHED = {"FT", "AET", "PEN"}


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _to_int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(str(value).rstrip("%"))
    except ValueError:
        return None


def _to_float(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _matchday_from_round(round_str: str | None) -> int | None:
    if not round_str:
        return None
    m = re.search(r"(\d+)", round_str)
    return int(m.group(1)) if m else None


class ApiFootballProvider(BaseProvider):
    name = "api-football"
    supports_depth = True

    def __init__(
        self,
        key: str,
        base_url: str = "https://v3.football.api-sports.io",
        min_request_interval: float = 6.5,
        timeout: float = 30.0,
        daily_limit: int = 100,
    ) -> None:
        self.key = key
        self.base_url = base_url.rstrip("/")
        self.min_request_interval = min_request_interval
        self.daily_limit = daily_limit
        self._last_request_ts = 0.0
        self._request_count = 0
        self._season_cache: dict[int, str] = {}
        headers = {"x-apisports-key": key} if key else {}
        # RapidAPI-hosted variant needs different headers.
        if "rapidapi" in base_url:
            headers = {"x-rapidapi-key": key, "x-rapidapi-host": httpx.URL(base_url).host}
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout, headers=headers)

    # -- HTTP -----------------------------------------------------------------
    def _throttle(self) -> None:
        wait = self.min_request_interval - (time.monotonic() - self._last_request_ts)
        if wait > 0:
            time.sleep(wait)

    def _get(self, path: str, params: dict | None = None, _retries: int = 3) -> list[dict]:
        if not self.key:
            raise ProviderError(
                "API_FOOTBALL_KEY is not set — get one at https://dashboard.api-football.com/"
            )
        if self._request_count >= self.daily_limit:
            raise ProviderError(
                f"api-football: local daily request budget ({self.daily_limit}) exhausted"
            )
        self._throttle()
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        try:
            resp = self._client.get(f"/{path.lstrip('/')}", params=clean)
        except httpx.HTTPError as exc:
            if _retries > 0:
                back = 2 ** (3 - _retries)
                log.warning("network error on %s (%s), retry in %ss", path, exc, back)
                time.sleep(back)
                self._last_request_ts = time.monotonic()
                return self._get(path, params, _retries - 1)
            raise ProviderError(f"request to {path} failed: {exc}") from exc
        finally:
            self._last_request_ts = time.monotonic()
            self._request_count += 1

        if resp.status_code == 429 and _retries > 0:
            time.sleep(int(resp.headers.get("Retry-After", "10")) + 1)
            return self._get(path, params, _retries - 1)
        if resp.status_code >= 400:
            raise ProviderError(f"{path}: {resp.status_code} {resp.text[:200]}")

        body = resp.json()
        errors = body.get("errors")
        if errors and (isinstance(errors, dict) or isinstance(errors, list)):
            # {} / [] means no error; anything populated is a real error.
            if (isinstance(errors, dict) and errors) or (isinstance(errors, list) and errors):
                raise ProviderError(f"{path}: {errors}")
        return body.get("response", []) or []

    def close(self) -> None:
        self._client.close()

    def _season(self, league_id: int, season: str | None) -> str:
        if season:
            return season
        if league_id in self._season_cache:
            return self._season_cache[league_id]
        rows = self._get("leagues", {"id": league_id, "current": "true"})
        current = None
        for r in rows:
            for s in r.get("seasons", []):
                if s.get("current"):
                    current = str(s["year"])
        current = current or str(datetime.now(UTC).year)
        self._season_cache[league_id] = current
        return current

    # -- mappers ------------------------------------------------------------------
    @staticmethod
    def _team(raw: dict) -> NTeam:
        venue = raw.get("venue")
        return NTeam(
            provider_id=raw["id"],
            name=raw.get("name") or f"Team {raw['id']}",
            short_name=raw.get("name"),
            crest_url=raw.get("logo"),
            founded=raw.get("founded"),
            venue=venue.get("name") if isinstance(venue, dict) else None,
            area_name=raw.get("country"),
        )

    @classmethod
    def _competition(cls, league: dict, country: dict | None = None) -> NCompetition:
        seasons = league.get("seasons") or []
        cur = next((s for s in seasons if s.get("current")), seasons[-1] if seasons else {})
        lg = league.get("league", league)
        country = country or league.get("country") or {}

        def _d(value: str | None) -> date | None:
            dt = _parse_dt(f"{value}T00:00:00") if value else None
            return dt.date() if dt else None

        return NCompetition(
            provider_id=lg["id"],
            code=str(lg["id"]),
            name=lg.get("name", f"League {lg['id']}"),
            type=(lg.get("type") or "").upper() or None,
            emblem_url=lg.get("logo"),
            area_name=country.get("name"),
            area_code=country.get("code"),
            area_flag=country.get("flag"),
            current_season=str(cur["year"]) if cur.get("year") else None,
            current_season_start=_d(cur.get("start")),
            current_season_end=_d(cur.get("end")),
        )

    @classmethod
    def _match(cls, item: dict, competition_code: str) -> NMatch:
        fx, lg, teams = item["fixture"], item["league"], item["teams"]
        score, goals = item.get("score") or {}, item.get("goals") or {}
        ht = score.get("halftime") or {}
        short = (fx.get("status") or {}).get("short", "NS")
        extra_time = (score.get("extratime") or {}).get("home") is not None

        home_win, away_win = teams["home"].get("winner"), teams["away"].get("winner")
        winner = None
        if home_win:
            winner = "HOME_TEAM"
        elif away_win:
            winner = "AWAY_TEAM"
        elif short in _FINISHED:
            winner = "DRAW"

        referee = (fx.get("referee") or "").strip()
        refs = [{"name": referee.split(",")[0].strip(), "type": "REFEREE"}] if referee else []
        return NMatch(
            provider_id=fx["id"],
            competition_code=competition_code,
            competition_provider_id=lg.get("id"),
            season=str(lg.get("season") or ""),
            utc_date=_parse_dt(fx.get("date")),
            status=_STATUS.get(short, "SCHEDULED"),
            home_team=cls._team(teams["home"]),
            away_team=cls._team(teams["away"]),
            matchday=_matchday_from_round(lg.get("round")),
            stage=lg.get("round"),
            home_score=goals.get("home"),
            away_score=goals.get("away"),
            home_score_ht=ht.get("home"),
            away_score_ht=ht.get("away"),
            winner=winner,
            duration="EXTRA_TIME" if extra_time else "REGULAR",
            venue=(fx.get("venue") or {}).get("name"),
            provider_updated_at=_parse_dt(fx.get("date")),
            referees=refs,
        )

    # -- breadth interface -----------------------------------------------------
    def list_competitions(self) -> list[NCompetition]:
        # Only the ones we have a code mapping for, to keep this cheap.
        from app.providers.leagues import API_FOOTBALL_LEAGUE_TO_CODE

        ids = ",".join(str(i) for i in API_FOOTBALL_LEAGUE_TO_CODE)
        rows = self._get("leagues", {"id": ids}) if len(API_FOOTBALL_LEAGUE_TO_CODE) == 1 else []
        if not rows:  # /leagues doesn't take a list; fall back to one call, all leagues
            rows = self._get("leagues", {})
        out = []
        for r in rows:
            lg_id = (r.get("league") or {}).get("id")
            if lg_id in API_FOOTBALL_LEAGUE_TO_CODE:
                comp = self._competition(r)
                comp.code = API_FOOTBALL_LEAGUE_TO_CODE[lg_id]
                out.append(comp)
        return out

    def get_teams(self, code: str, season: str | None = None) -> tuple[NCompetition, list[NTeam]]:
        lg = to_league_id(code)
        season = self._season(lg, season)
        rows = self._get("teams", {"league": lg, "season": season})
        teams = []
        for r in rows:
            t = self._team({**r["team"], "venue": r.get("venue")})
            teams.append(t)
        comp = NCompetition(provider_id=lg, code=code.upper(), name=code.upper(),
                            current_season=season)
        return comp, teams

    def get_standings(self, code: str, season: str | None = None) -> NStandings:
        lg = to_league_id(code)
        season = self._season(lg, season)
        rows = self._get("standings", {"league": lg, "season": season})
        comp = NCompetition(provider_id=lg, code=code.upper(), name=code.upper(),
                            current_season=season)
        result_rows: list[NStandingRow] = []
        for block in rows:
            for group in (block.get("league") or {}).get("standings", []):
                for r in group:
                    alls = r.get("all") or {}
                    g = alls.get("goals") or {}
                    result_rows.append(
                        NStandingRow(
                            team=self._team(r["team"]),
                            position=r.get("rank", 0),
                            played=alls.get("played", 0),
                            won=alls.get("win", 0),
                            draw=alls.get("draw", 0),
                            lost=alls.get("lose", 0),
                            points=r.get("points", 0),
                            goals_for=g.get("for", 0),
                            goals_against=g.get("against", 0),
                            goal_difference=r.get("goalsDiff", 0),
                            form=",".join(list(r.get("form") or "")) or None,
                            group=r.get("group"),
                        )
                    )
        return NStandings(competition=comp, season=season, rows=result_rows)

    def get_matches(
        self,
        code: str,
        *,
        season: str | None = None,
        matchday: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[NMatch]:
        lg = to_league_id(code)
        season = self._season(lg, season)
        params = {
            "league": lg,
            "season": season,
            "round": f"Regular Season - {matchday}" if matchday else None,
            "from": date_from.isoformat() if date_from else None,
            "to": date_to.isoformat() if date_to else None,
        }
        return [self._match(it, code.upper()) for it in self._get("fixtures", params)]

    def get_match(self, provider_id: int) -> NMatch:
        rows = self._get("fixtures", {"id": provider_id})
        if not rows:
            raise ProviderError(f"fixture {provider_id} not found")
        item = rows[0]
        code = ""
        return self._match(item, code)

    def get_scorers(
        self, code: str, season: str | None = None, limit: int = 20
    ) -> tuple[NCompetition, list[NScorer]]:
        lg = to_league_id(code)
        season = self._season(lg, season)
        rows = self._get("players/topscorers", {"league": lg, "season": season})
        comp = NCompetition(provider_id=lg, code=code.upper(), name=code.upper(),
                            current_season=season)
        scorers: list[NScorer] = []
        for r in rows[:limit]:
            p = r.get("player") or {}
            st = (r.get("statistics") or [{}])[0]
            team = st.get("team") or {}
            goals = (st.get("goals") or {})
            games = (st.get("games") or {})
            scorers.append(
                NScorer(
                    player_name=p.get("name", "Unknown"),
                    player_provider_id=p.get("id"),
                    nationality=p.get("nationality"),
                    team=self._team(team) if team else None,
                    played_matches=games.get("appearences"),
                    goals=goals.get("total") or 0,
                    assists=goals.get("assists"),
                    position=games.get("position"),
                )
            )
        return comp, scorers

    # -- depth methods -------------------------------------------------------
    def get_fixture_events(
        self, fixture_id: int
    ) -> tuple[list[NGoal], list[NBooking], list[NSubstitution]]:
        rows = self._get("fixtures/events", {"fixture": fixture_id})
        goals: list[NGoal] = []
        bookings: list[NBooking] = []
        subs: list[NSubstitution] = []
        for e in rows:
            minute = (e.get("time") or {}).get("elapsed")
            extra = (e.get("time") or {}).get("extra")
            team_id = (e.get("team") or {}).get("id")
            player = (e.get("player") or {}).get("name")
            assist = (e.get("assist") or {}).get("name")
            etype = (e.get("type") or "").lower()
            detail = (e.get("detail") or "").lower()
            if etype == "goal":
                if "missed" in detail:
                    continue
                gtype = "REGULAR"
                if "penalty" in detail:
                    gtype = "PENALTY"
                elif "own" in detail:
                    gtype = "OWN"
                goals.append(NGoal(
                    minute=minute, injury_time=extra, type=gtype, team_provider_id=team_id,
                    scorer_name=player, assist_name=assist,
                ))
            elif etype == "card":
                card = "RED" if "red" in detail else "YELLOW"
                bookings.append(NBooking(minute=minute, team_provider_id=team_id,
                                         player_name=player, card=card))
            elif etype == "subst":
                subs.append(NSubstitution(minute=minute, team_provider_id=team_id,
                                          player_in_name=assist, player_out_name=player))
        return goals, bookings, subs

    def get_fixture_statistics(self, fixture_id: int) -> list[NTeamMatchStats]:
        rows = self._get("fixtures/statistics", {"fixture": fixture_id})
        out: list[NTeamMatchStats] = []
        for block in rows:
            stat = {s["type"]: s.get("value") for s in block.get("statistics", [])}
            out.append(
                NTeamMatchStats(
                    team_provider_id=(block.get("team") or {}).get("id"),
                    possession=_to_int(stat.get("Ball Possession")),
                    shots=_to_int(stat.get("Total Shots")),
                    shots_on_target=_to_int(stat.get("Shots on Goal")),
                    corners=_to_int(stat.get("Corner Kicks")),
                    fouls=_to_int(stat.get("Fouls")),
                    offsides=_to_int(stat.get("Offsides")),
                    yellow_cards=_to_int(stat.get("Yellow Cards")),
                    red_cards=_to_int(stat.get("Red Cards")),
                    passes=_to_int(stat.get("Total passes")),
                    passes_accuracy=_to_int(stat.get("Passes %")),
                    saves=_to_int(stat.get("Goalkeeper Saves")),
                    xg=_to_float(stat.get("expected_goals")),
                )
            )
        return out

    def get_fixture_player_ratings(self, fixture_id: int) -> list[NPlayerRating]:
        rows = self._get("fixtures/players", {"fixture": fixture_id})
        out: list[NPlayerRating] = []
        for block in rows:
            team_id = (block.get("team") or {}).get("id")
            for p in block.get("players", []):
                info = p.get("player") or {}
                st = (p.get("statistics") or [{}])[0]
                games = st.get("games") or {}
                goals = st.get("goals") or {}
                cards = st.get("cards") or {}
                out.append(
                    NPlayerRating(
                        player_name=info.get("name", "Unknown"),
                        player_provider_id=info.get("id"),
                        team_provider_id=team_id,
                        rating=_to_float(games.get("rating")),
                        minutes=games.get("minutes"),
                        position=games.get("position"),
                        number=games.get("number"),
                        is_starter=not games.get("substitute", False),
                        captain=bool(games.get("captain")),
                        goals=goals.get("total"),
                        assists=goals.get("assists"),
                        yellow=cards.get("yellow"),
                        red=cards.get("red"),
                    )
                )
        return out

    def get_match_depth(self, fixture_id: int) -> NMatch:
        """Full depth bundle for one fixture: core + events + stats + ratings."""
        match = self.get_match(fixture_id)
        match.goals, match.bookings, match.substitutions = self.get_fixture_events(fixture_id)
        match.team_stats = self.get_fixture_statistics(fixture_id)
        match.player_ratings = self.get_fixture_player_ratings(fixture_id)
        return match

    def find_fixture_id(
        self, code: str, season: str, on: date, home_name: str, away_name: str
    ) -> int | None:
        """Locate the API-Football fixture id for a match known from another provider.

        Matches on league + season + date (±1 day) + fuzzy team-name overlap.
        """
        lg = to_league_id(code)
        best: tuple[float, int] | None = None
        for delta in (0, -1, 1):
            day = date.fromordinal(on.toordinal() + delta)
            rows = self._get("fixtures", {"league": lg, "season": season, "date": day.isoformat()})
            for it in rows:
                teams = it["teams"]
                score = _name_overlap(home_name, teams["home"]["name"]) + _name_overlap(
                    away_name, teams["away"]["name"]
                )
                if score >= 1.0 and (best is None or score > best[0]):
                    best = (score, it["fixture"]["id"])
            if best and best[0] >= 2.0:
                break
        return best[1] if best else None


def _strip_accents(s: str) -> str:
    """'Köln' -> 'Koln', 'Alavés' -> 'Alaves' — data sources mix accented and
    plain-ASCII spellings of the same club name."""
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _name_overlap(a: str, b: str) -> float:
    """Rough token-overlap score in [0, 1] between two team names."""
    stop = {"fc", "cf", "afc", "ac", "sc", "club", "de", "the", "1", "calcio"}
    ta = {w for w in re.findall(r"\w+", _strip_accents(a.lower())) if w not in stop}
    tb = {w for w in re.findall(r"\w+", _strip_accents(b.lower())) if w not in stop}
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))
