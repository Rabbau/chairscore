"""football-data.org v4 provider.

Docs: https://docs.football-data.org/general/v4/index.html
Free tier: 10 requests/minute, ~13 competitions, no per-match xG / lineups.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, date, datetime

import httpx

from app.providers.base import (
    BaseProvider,
    NBooking,
    NCompetition,
    NGoal,
    NMatch,
    NPlayer,
    NScorer,
    NStandingRow,
    NStandings,
    NSubstitution,
    NTeam,
    ProviderError,
)

log = logging.getLogger("chairscore.provider.football_data")


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


class FootballDataProvider(BaseProvider):
    name = "football-data.org"

    def __init__(
        self,
        token: str,
        base_url: str = "https://api.football-data.org/v4",
        min_request_interval: float = 6.1,
        timeout: float = 30.0,
    ) -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.min_request_interval = min_request_interval
        self._last_request_ts = 0.0
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers={"X-Auth-Token": token} if token else {},
        )

    # -- HTTP ---------------------------------------------------------------
    def _throttle(self) -> None:
        wait = self.min_request_interval - (time.monotonic() - self._last_request_ts)
        if wait > 0:
            time.sleep(wait)

    def _get(self, path: str, params: dict | None = None, _retries: int = 3) -> dict:
        if not self.token:
            raise ProviderError(
                "FOOTBALL_DATA_API_TOKEN is not set — get one at "
                "https://www.football-data.org/client/register"
            )
        self._throttle()
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        try:
            resp = self._client.get(path, params=clean)
        except httpx.HTTPError as exc:  # transient network / TLS blip
            if _retries > 0:
                back = 2 ** (3 - _retries)
                log.warning("network error on %s (%s), retrying in %ss", path, exc, back)
                time.sleep(back)
                self._last_request_ts = time.monotonic()
                return self._get(path, params, _retries - 1)
            raise ProviderError(f"request to {path} failed: {exc}") from exc
        finally:
            self._last_request_ts = time.monotonic()

        if resp.status_code == 429 and _retries > 0:
            retry_after = int(resp.headers.get("Retry-After", "10")) + 1
            log.warning("rate limited on %s, sleeping %ss", path, retry_after)
            time.sleep(retry_after)
            return self._get(path, params, _retries - 1)
        if resp.status_code in (500, 502, 503, 504) and _retries > 0:
            log.warning("%s on %s, retrying", resp.status_code, path)
            time.sleep(3)
            return self._get(path, params, _retries - 1)
        if resp.status_code == 403:
            raise ProviderError(
                f"{path}: 403 — token invalid or competition/resource not on your plan"
            )
        if resp.status_code >= 400:
            raise ProviderError(f"{path}: {resp.status_code} {resp.text[:200]}")
        return resp.json()

    def close(self) -> None:
        self._client.close()

    # -- mappers ----------------------------------------------------------------
    @staticmethod
    def _team(raw: dict) -> NTeam:
        return NTeam(
            provider_id=raw["id"],
            name=raw.get("name") or raw.get("shortName") or f"Team {raw['id']}",
            short_name=raw.get("shortName"),
            tla=raw.get("tla"),
            crest_url=raw.get("crest"),
            founded=raw.get("founded"),
            club_colors=raw.get("clubColors"),
            venue=raw.get("venue"),
            website=raw.get("website"),
            coach_name=(raw.get("coach") or {}).get("name"),
            area_name=(raw.get("area") or {}).get("name"),
            squad=[
                NPlayer(
                    name=p["name"],
                    provider_id=p.get("id"),
                    position=p.get("position"),
                    date_of_birth=_parse_date(p.get("dateOfBirth")),
                    nationality=p.get("nationality"),
                    shirt_number=p.get("shirtNumber"),
                )
                for p in (raw.get("squad") or [])
            ],
        )

    @staticmethod
    def _competition(raw: dict) -> NCompetition:
        season = raw.get("currentSeason") or {}
        start = _parse_date(season.get("startDate"))
        return NCompetition(
            provider_id=raw["id"],
            code=raw["code"],
            name=raw["name"],
            type=raw.get("type"),
            emblem_url=raw.get("emblem"),
            area_name=(raw.get("area") or {}).get("name"),
            area_code=(raw.get("area") or {}).get("code"),
            area_flag=(raw.get("area") or {}).get("flag"),
            current_season=str(start.year) if start else None,
            current_season_start=start,
            current_season_end=_parse_date(season.get("endDate")),
            current_matchday=season.get("currentMatchday"),
        )

    @classmethod
    def _match(cls, raw: dict, competition_code: str, competition_pid: int | None) -> NMatch:
        score = raw.get("score") or {}
        full = score.get("fullTime") or {}
        half = score.get("halfTime") or {}
        season_raw = raw.get("season") or {}
        season = str(_parse_date(season_raw.get("startDate")).year) if season_raw.get(
            "startDate"
        ) else str(_parse_dt(raw["utcDate"]).year)

        m = NMatch(
            provider_id=raw["id"],
            competition_code=competition_code,
            competition_provider_id=competition_pid,
            season=season,
            utc_date=_parse_dt(raw["utcDate"]),
            status=raw.get("status", "SCHEDULED"),
            home_team=cls._team(raw["homeTeam"]),
            away_team=cls._team(raw["awayTeam"]),
            matchday=raw.get("matchday"),
            stage=raw.get("stage"),
            group=raw.get("group"),
            home_score=full.get("home"),
            away_score=full.get("away"),
            home_score_ht=half.get("home"),
            away_score_ht=half.get("away"),
            winner=score.get("winner"),
            duration=score.get("duration"),
            venue=raw.get("venue"),
            provider_updated_at=_parse_dt(raw.get("lastUpdated")),
            referees=[
                {"name": r.get("name"), "type": r.get("type"), "nationality": r.get("nationality")}
                for r in (raw.get("referees") or [])
                if r.get("name")
            ],
        )
        for g in raw.get("goals") or []:
            m.goals.append(
                NGoal(
                    minute=g.get("minute"),
                    injury_time=g.get("injuryTime"),
                    type=g.get("type"),
                    team_provider_id=(g.get("team") or {}).get("id"),
                    scorer_name=(g.get("scorer") or {}).get("name"),
                    scorer_provider_id=(g.get("scorer") or {}).get("id"),
                    assist_name=(g.get("assist") or {}).get("name"),
                    home_score=(g.get("score") or {}).get("home"),
                    away_score=(g.get("score") or {}).get("away"),
                )
            )
        for b in raw.get("bookings") or []:
            m.bookings.append(
                NBooking(
                    minute=b.get("minute"),
                    team_provider_id=(b.get("team") or {}).get("id"),
                    player_name=(b.get("player") or {}).get("name"),
                    card=b.get("card"),
                )
            )
        for s in raw.get("substitutions") or []:
            m.substitutions.append(
                NSubstitution(
                    minute=s.get("minute"),
                    team_provider_id=(s.get("team") or {}).get("id"),
                    player_in_name=(s.get("playerIn") or {}).get("name"),
                    player_out_name=(s.get("playerOut") or {}).get("name"),
                )
            )
        return m

    # -- BaseProvider ---------------------------------------------------------
    def list_competitions(self) -> list[NCompetition]:
        data = self._get("/competitions")
        return [self._competition(c) for c in data.get("competitions", [])]

    def get_teams(self, code: str, season: str | None = None) -> tuple[NCompetition, list[NTeam]]:
        data = self._get(f"/competitions/{code}/teams", {"season": season})
        comp = self._competition(data["competition"])
        return comp, [self._team(t) for t in data.get("teams", [])]

    def get_standings(self, code: str, season: str | None = None) -> NStandings:
        data = self._get(f"/competitions/{code}/standings", {"season": season})
        comp = self._competition(data["competition"])
        season_str = str((data.get("filters") or {}).get("season") or comp.current_season or "")
        rows: list[NStandingRow] = []
        for block in data.get("standings", []):
            # league tables come back with group == "Matchday" (noise); real
            # group names look like "GROUP_A".
            group = block.get("group")
            if group and group.upper() in ("MATCHDAY", "REGULAR_SEASON"):
                group = None
            for r in block.get("table", []):
                rows.append(
                    NStandingRow(
                        team=self._team(r["team"]),
                        position=r["position"],
                        played=r.get("playedGames", 0),
                        won=r.get("won", 0),
                        draw=r.get("draw", 0),
                        lost=r.get("lost", 0),
                        points=r.get("points", 0),
                        goals_for=r.get("goalsFor", 0),
                        goals_against=r.get("goalsAgainst", 0),
                        goal_difference=r.get("goalDifference", 0),
                        form=r.get("form"),
                        stage=block.get("stage", "REGULAR_SEASON"),
                        type=block.get("type", "TOTAL"),
                        group=group,
                    )
                )
        return NStandings(competition=comp, season=season_str, rows=rows)

    def get_matches(
        self,
        code: str,
        *,
        season: str | None = None,
        matchday: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[NMatch]:
        params = {
            "season": season,
            "matchday": matchday,
            "dateFrom": date_from.isoformat() if date_from else None,
            "dateTo": date_to.isoformat() if date_to else None,
        }
        data = self._get(f"/competitions/{code}/matches", params)
        comp_raw = data.get("competition") or {}
        pid = comp_raw.get("id")
        return [self._match(m, code, pid) for m in data.get("matches", [])]

    def get_match(self, provider_id: int) -> NMatch:
        data = self._get(f"/matches/{provider_id}")
        raw = data.get("match") or data
        comp_raw = raw.get("competition") or {}
        return self._match(raw, comp_raw.get("code", ""), comp_raw.get("id"))

    def get_scorers(
        self, code: str, season: str | None = None, limit: int = 20
    ) -> tuple[NCompetition, list[NScorer]]:
        data = self._get(f"/competitions/{code}/scorers", {"season": season, "limit": limit})
        comp = self._competition(data["competition"])
        scorers: list[NScorer] = []
        for s in data.get("scorers", []):
            player = s.get("player") or {}
            scorers.append(
                NScorer(
                    player_name=player.get("name", "Unknown"),
                    player_provider_id=player.get("id"),
                    position=player.get("position"),
                    nationality=player.get("nationality"),
                    date_of_birth=_parse_date(player.get("dateOfBirth")),
                    team=self._team(s["team"]) if s.get("team") else None,
                    played_matches=s.get("playedMatches"),
                    goals=s.get("goals") or 0,
                    assists=s.get("assists"),
                    penalties=s.get("penalties"),
                )
            )
        return comp, scorers
