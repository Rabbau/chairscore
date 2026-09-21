"""UEFA provider — the data behind uefa.com for the Champions League and Europa League.

Three key-less JSON services the site itself calls (each publishes its OpenAPI
spec at ``/v3/api-docs``):

* ``match.uefa.com``      fixtures / results, lineups, the per-match event feed
* ``standings.uefa.com``  league-phase / group tables
* ``compstats.uefa.com``  season aggregates — used here only for top scorers

There is no per-match team-statistics endpoint. Shots, corners, fouls, offsides
and cards are counted from the event feed instead — checked against UEFA's own
aggregates for teams playing their first match of a season, where on-target
shots, corners, fouls and yellows all matched exactly. Possession and passes are
simply not available per match.

Undocumented as a product: fine for a personal project, but it can change or
start blocking without notice, so requests are throttled and the heavy payloads
(lineups + events, ~4 calls per match) are fetched once per finished match.

IDs: UEFA ids are offset by ``UEFA_ID_OFFSET`` so they can share the
``provider_id`` columns with football-data.org's without colliding.
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from dataclasses import dataclass, field
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

log = logging.getLogger("chairscore.provider.uefa")

UEFA_ID_OFFSET = 1_000_000_000
USER_AGENT = "Chairscore/0.1 (+https://github.com/Rabbau/chairscore)"


@dataclass(frozen=True, slots=True)
class _CompetitionInfo:
    uefa_id: int
    name: str
    # CL keeps football-data.org's id: that competition row is seeded on first
    # run, and this is what lets UEFA update it rather than add a second "CL".
    provider_id: int


COMPETITIONS: dict[str, _CompetitionInfo] = {
    "CL": _CompetitionInfo(1, "UEFA Champions League", 2001),
    "EL": _CompetitionInfo(14, "UEFA Europa League", UEFA_ID_OFFSET + 14),
}

_EMBLEM = "https://crests.football-data.org/{code}.png"

_STATUS = {
    "FINISHED": "FINISHED",
    "UPCOMING": "TIMED",
    "LIVE": "IN_PLAY",
    "SUSPENDED": "SUSPENDED",
    "POSTPONED": "POSTPONED",
    "CANCELED": "CANCELLED",
    "ABANDONED": "CANCELLED",
    "UNKNOWN": "SCHEDULED",
}

# UEFA round type -> football-data.org-style stage names, which is what the UI
# and the rest of the schema already speak.
_STAGE = {
    "FINAL_TOURNAMENT_PLAY_OFF": "PLAYOFFS",
    "ROUND_OF_16": "LAST_16",
    "QUARTER_FINALS": "QUARTER_FINALS",
    "SEMIFINAL": "SEMI_FINALS",
    "FINAL": "FINAL",
    "FIRST_QUALIFYING": "QUALIFYING_ROUND_1",
    "SECOND_QUALIFYING": "QUALIFYING_ROUND_2",
    "THIRD_QUALIFYING": "QUALIFYING_ROUND_3",
    "PLAY_OFF": "QUALIFYING_PLAYOFF",
}
# The single-table "league phase" started with the 2024-25 season (seasonYear 2025).
_FIRST_LEAGUE_PHASE_YEAR = 2025

_POSITION = {"GOALKEEPER": "GKP", "DEFENDER": "DEF", "MIDFIELDER": "MID", "FORWARD": "FWD"}
_PHASE_ORDER = {
    "FIRST_HALF": 0,
    "SECOND_HALF": 1,
    "EXTRA_TIME_FIRST_HALF": 2,
    "EXTRA_TIME_SECOND_HALF": 3,
    "PENALTY": 4,
}
_SHOOTOUT = "PENALTY"
_REFEREE_ROLES = {"REFEREE": "REFEREE", "VIDEO_ASSISTANT_REFEREE": "VAR"}


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def uefa_season_year(season: str) -> str:
    """Our start-year season ("2026" = 2026-27) -> UEFA's end-year ("2027")."""
    return str(int(season) + 1)


def season_from_uefa_year(season_year: str | int) -> str:
    return str(int(season_year) - 1)


def current_season(today: date | None = None) -> str:
    """UEFA seasons roll over on 1 July."""
    today = today or datetime.now(UTC).date()
    return str(today.year if today.month >= 7 else today.year - 1)


def _en(translations: object) -> str | None:
    """Pick the English string out of UEFA's ``{"EN": ..., "FR": ...}`` maps."""
    if isinstance(translations, dict):
        value = translations.get("EN")
        return value if isinstance(value, str) and value else None
    return None


def _int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def team_pid(uefa_team_id: object) -> int:
    return UEFA_ID_OFFSET + int(uefa_team_id)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# mappers: raw UEFA JSON -> normalized dataclasses
# --------------------------------------------------------------------------- #
def map_team(raw: dict) -> NTeam:
    tr = raw.get("translations") or {}
    international = raw.get("internationalName")
    display = _en(tr.get("displayName"))
    official = _en(tr.get("displayOfficialName"))
    names = [n for n in (official, display, international) if n]
    return NTeam(
        provider_id=team_pid(raw["id"]),
        name=official or international or display or f"Team {raw['id']}",
        short_name=display or international,
        tla=raw.get("teamCode"),
        crest_url=raw.get("mediumLogoUrl") or raw.get("logoUrl") or raw.get("bigLogoUrl"),
        area_name=_en(tr.get("countryName")),
        aliases=list(dict.fromkeys(names)),
    )


def _person_name(person: dict) -> str | None:
    tr = person.get("translations") or {}
    full = " ".join(p for p in (_en(tr.get("firstName")), _en(tr.get("lastName"))) if p)
    return full or person.get("internationalName") or None


def _referees(raw: dict) -> list[dict]:
    out = []
    for r in raw.get("referees") or []:
        kind = _REFEREE_ROLES.get(r.get("role") or "")
        person = r.get("person") or {}
        name = _person_name(person)
        if kind and name:
            out.append({
                "name": name,
                "type": kind,
                "nationality": _en((person.get("translations") or {}).get("countryName")),
            })
    return sorted(out, key=lambda r: r["type"] != "REFEREE")  # the referee first, then VAR


def _stage(raw: dict) -> str | None:
    round_type = ((raw.get("round") or {}).get("metaData") or {}).get("type")
    if round_type == "GROUP_STANDINGS":
        year = _int(raw.get("seasonYear")) or 0
        return "LEAGUE_STAGE" if year >= _FIRST_LEAGUE_PHASE_YEAR else "GROUP_STAGE"
    return _STAGE.get(round_type or "")


def _credited_team(scorer: dict, home_id: str, away_id: str) -> str | None:
    """Which side a listed goal counts for — an own goal counts for the other one."""
    team = str(scorer.get("teamId") or "")
    if scorer.get("goalType") == "OWN":
        return away_id if team == home_id else home_id if team == away_id else None
    return team or None


def map_match(raw: dict, code: str) -> NMatch:
    score = raw.get("score") or {}
    total = score.get("total") or {}
    regular = score.get("regular") or {}
    penalty = score.get("penalty") or {}
    status = _STATUS.get(raw.get("status") or "", "SCHEDULED")
    finished = status == "FINISHED"

    home, away = raw["homeTeam"], raw["awayTeam"]
    home_id, away_id = str(home["id"]), str(away["id"])
    scorers = (raw.get("playerEvents") or {}).get("scorers") or []

    # Half-time isn't a field of its own; count the first-half goals instead.
    ht_home = ht_away = None
    if finished:
        ht_home = ht_away = 0
        for s in scorers:
            if s.get("phase") != "FIRST_HALF":
                continue
            side = _credited_team(s, home_id, away_id)
            ht_home += side == home_id
            ht_away += side == away_id

    winner = None
    reason = ""
    if finished:
        won = ((raw.get("winner") or {}).get("match") or {})
        reason = won.get("reason") or ""
        winner_id = str((won.get("team") or {}).get("id") or "")
        winner = (
            "HOME_TEAM" if winner_id == home_id
            else "AWAY_TEAM" if winner_id == away_id
            else "DRAW"
        )

    duration = None
    if finished:
        if penalty or "PENALT" in reason:
            duration = "PENALTY_SHOOTOUT"
        elif "EXTRA" in reason or (total and regular and total != regular):
            duration = "EXTRA_TIME"
        else:
            duration = "REGULAR"

    stage = _stage(raw)
    matchday = (
        _int((raw.get("matchday") or {}).get("sequenceNumber"))
        if raw.get("type") == "GROUP_STAGE" else None
    )
    stadium = (raw.get("stadium") or {}).get("translations") or {}

    return NMatch(
        provider_id=UEFA_ID_OFFSET + int(raw["id"]),
        competition_code=code,
        competition_provider_id=None,
        season=season_from_uefa_year(raw["seasonYear"]),
        utc_date=_parse_dt((raw.get("kickOffTime") or {}).get("dateTime")) or datetime.now(UTC),
        status=status,
        home_team=map_team(home),
        away_team=map_team(away),
        matchday=matchday,
        stage=stage,
        home_score=total.get("home") if finished or status == "IN_PLAY" else None,
        away_score=total.get("away") if finished or status == "IN_PLAY" else None,
        home_score_ht=ht_home,
        away_score_ht=ht_away,
        home_score_pen=penalty.get("home"),
        away_score_pen=penalty.get("away"),
        winner=winner,
        duration=duration,
        venue=_en(stadium.get("name")) or _en(stadium.get("mediaName")),
        referees=_referees(raw),
    )


def map_standings(comp: NCompetition, season: str, blocks: list[dict]) -> NStandings:
    rows: list[NStandingRow] = []
    for block in blocks:
        group_name = ((block.get("group") or {}).get("metaData") or {}).get("groupName")
        league = group_name in (None, "League")
        for item in block.get("items") or []:
            if not item.get("team"):
                continue
            rows.append(NStandingRow(
                team=map_team(item["team"]),
                position=item["rank"],
                played=item.get("played", 0),
                won=item.get("won", 0),
                draw=item.get("drawn", 0),
                lost=item.get("lost", 0),
                points=item.get("points", 0),
                goals_for=item.get("goalsFor", 0),
                goals_against=item.get("goalsAgainst", 0),
                goal_difference=item.get("goalDifference", 0),
                stage="LEAGUE_STAGE" if league else "GROUP_STAGE",
                type="TOTAL",
                group=None if league else group_name,
            ))
    return NStandings(competition=comp, season=season, rows=rows)


def map_scorers(entries: list[dict]) -> list[NScorer]:
    out = []
    for e in entries:
        player = e.get("player") or {}
        stats = {s.get("name"): _int(s.get("value")) for s in e.get("statistics") or []}
        team = map_team(e["team"]) if e.get("team") else None
        out.append(NScorer(
            player_name=player.get("internationalName") or "Unknown",
            player_provider_id=_int(player.get("id")),
            team=team,
            position=_POSITION.get(player.get("fieldPosition") or ""),
            nationality=_en((player.get("translations") or {}).get("countryName")),
            played_matches=stats.get("matches_appearance"),
            goals=stats.get("goals") or 0,
            assists=stats.get("assists"),
        ))
    return out


# --------------------------------------------------------------------------- #
# depth: lineups + event feed -> events, team stats, player lines
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class UefaDepth:
    goals: list[NGoal] = field(default_factory=list)
    bookings: list[NBooking] = field(default_factory=list)
    substitutions: list[NSubstitution] = field(default_factory=list)
    team_stats: list[NTeamMatchStats] = field(default_factory=list)
    player_ratings: list[NPlayerRating] = field(default_factory=list)
    complete: bool = False  # the feed reached full time


def _actor(event: dict, which: str) -> tuple[str | None, dict]:
    """(team id, person) for an event's primary/secondary actor. Coaches and
    other staff come back with the person nested one level deeper and no
    ``id`` — those aren't players, so they yield an empty person."""
    actor = event.get(which) or {}
    team = str((actor.get("team") or {}).get("id") or "") or None
    person = actor.get("person") or {}
    if actor.get("type") not in (None, "PLAYER") or "id" not in person:
        person = {}
    return team, person


def _order_key(event: dict) -> tuple:
    t = event.get("time") or {}

    def num(key: str, default: int) -> int:
        value = t.get(key)
        return default if value is None else value

    return (
        _PHASE_ORDER.get(event.get("phase") or "", 9),
        num("minute", 999),
        num("injuryMinute", 0),
        num("second", 0),
        event.get("timestamp") or "",
    )


def _seconds(event: dict) -> float | None:
    dt = _parse_dt(event.get("timestamp"))
    return dt.timestamp() if dt else None


def _minute(event: dict) -> tuple[int | None, int | None]:
    """(minute, stoppage minutes) — 90 + 2 arrives as minute 90, injuryMinute 2."""
    t = event.get("time") or {}
    return t.get("minute"), t.get("injuryMinute")


def build_depth(
    lineups: dict | None,
    events: list[dict],
    home_id: str | None = None,
    away_id: str | None = None,
) -> UefaDepth:
    """Turn one match's lineups + event feed into our normalized depth objects.

    ``home_id`` / ``away_id`` (UEFA team ids) fix which side is which when the
    lineups are missing; with lineups the order they list is used.
    """
    lineups = lineups or {}
    sides = [lineups.get("homeTeam") or {}, lineups.get("awayTeam") or {}]
    team_ids = [str((s.get("team") or {}).get("id") or "") for s in sides]
    if not all(team_ids):
        team_ids = [str(home_id or ""), str(away_id or "")]
    home_id, away_id = team_ids
    known = {t for t in team_ids if t}

    def other(team: str | None) -> str | None:
        return away_id if team == home_id else home_id if team == away_id else None

    evs = sorted(events, key=_order_key)
    extra_time = any((e.get("phase") or "").startswith("EXTRA_TIME") for e in evs)
    full_time = 120 if extra_time else 90

    # -- player index from the lineups ------------------------------------
    players: dict[tuple[str, str], dict] = {}
    for side, team in zip(sides, team_ids, strict=True):
        for group, starter in (("field", True), ("bench", False)):
            for entry in side.get(group) or []:
                person = entry.get("player") or {}
                if not person.get("id"):
                    continue
                players[(team, str(person["id"]))] = {
                    "name": person.get("internationalName") or "Unknown",
                    "number": entry.get("jerseyNumber"),
                    "position": _POSITION.get(person.get("fieldPosition") or ""),
                    "starter": starter,
                    "on": 0 if starter else None,
                    "off": None,
                    "goals": 0, "assists": 0, "yellow": 0, "red": 0, "saves": 0,
                }

    def player(team: str | None, person: dict) -> dict | None:
        return players.get((team or "", str(person.get("id")))) if person else None

    stats = {t: Counter() for t in known}
    out = UefaDepth()
    goal_events: list[tuple[NGoal, str | None, float | None]] = []
    assists: list[tuple[str | None, str, float | None, dict]] = []

    for e in evs:
        kind, phase = e.get("type"), e.get("phase")
        if kind == "FULL_TIME":
            out.complete = True
        if phase == _SHOOTOUT:
            continue  # shoot-out kicks aren't part of the match stats or timeline
        team, person = _actor(e, "primaryActor")
        rival = other(team)
        name = person.get("internationalName")
        minute, injury = _minute(e)
        row = player(team, person)

        if kind == "GOAL":
            own = e.get("subType") == "OWN"
            credited = rival if own else team
            if not own and team in stats:
                stats[team]["shots"] += 1
                stats[team]["on_target"] += 1
            if row and not own:
                row["goals"] += 1
            goal = NGoal(
                minute=minute, injury_time=injury,
                type="OWN" if own else "PENALTY" if e.get("subType") == "PENALTY" else "REGULAR",
                team_provider_id=team_pid(credited) if credited else None,
                scorer_name=name,
                scorer_provider_id=_int(person.get("id")),
            )
            goal_events.append((goal, credited, _seconds(e)))
            out.goals.append(goal)
        elif kind == "ASSIST":
            if row:
                row["assists"] += 1
            assists.append((team, name or "", _seconds(e), e))
        elif kind == "SHOT_ON_GOAL":
            if team in stats:
                stats[team]["shots"] += 1
                stats[team]["on_target"] += 1
            if rival in stats:
                stats[rival]["saves"] += 1
            keeper_team, keeper = _actor(e, "secondaryActor")
            if krow := player(keeper_team, keeper):
                krow["saves"] += 1
        elif kind in ("SHOT_WIDE", "SHOT_BLOCKED"):
            if team in stats:
                stats[team]["shots"] += 1
        elif kind == "PENALTY":  # an in-play penalty that wasn't scored
            if team in stats:
                stats[team]["shots"] += 1
                if e.get("subType") == "SAVED":
                    stats[team]["on_target"] += 1
        elif kind == "CORNER" and team in stats:
            stats[team]["corners"] += 1
        elif kind == "FOUL" and team in stats:
            stats[team]["fouls"] += 1
        elif kind == "OFFSIDE" and team in stats:
            stats[team]["offsides"] += 1
        elif kind in ("YELLOW_CARD", "YELLOW_CARD_SECOND", "RED_CARD", "RED_YELLOW_CARD"):
            if not person:
                continue  # a card for a coach / official
            yellow = kind in ("YELLOW_CARD", "YELLOW_CARD_SECOND")
            if team in stats:
                stats[team]["yellow" if yellow else "red"] += 1
            if row:
                row["yellow" if yellow else "red"] += 1
                if not yellow:
                    row["off"] = min(minute or full_time, full_time)
            # The second yellow arrives as two events; show it once, as the dismissal.
            if kind != "YELLOW_CARD_SECOND":
                out.bookings.append(NBooking(
                    minute=minute, team_provider_id=team_pid(team) if team else None,
                    player_name=name,
                    card={"YELLOW_CARD": "YELLOW", "RED_CARD": "RED"}.get(kind, "YELLOW_RED"),
                ))
        elif kind == "SUBSTITUTION":
            _, incoming = _actor(e, "secondaryActor")
            at = min(minute or 0, full_time)
            if row:
                row["off"] = at
            if irow := player(team, incoming):
                irow["on"] = at
            out.substitutions.append(NSubstitution(
                minute=minute, team_provider_id=team_pid(team) if team else None,
                player_in_name=incoming.get("internationalName"), player_out_name=name,
            ))

    # -- running score + assists on the goal list --------------------------
    scored = {home_id: 0, away_id: 0}
    for goal, credited, _ in goal_events:
        if credited in scored:
            scored[credited] += 1
        goal.home_score, goal.away_score = scored[home_id], scored[away_id]
    for team, name, when, _event in assists:
        best: tuple[float, NGoal] | None = None
        for goal, credited, gwhen in goal_events:
            if credited != team or goal.type == "OWN" or goal.assist_name:
                continue
            gap = abs(when - gwhen) if when is not None and gwhen is not None else 1e9
            if gap <= 30 and (best is None or gap < best[0]):
                best = (gap, goal)
        if best:
            best[1].assist_name = name or None

    # -- team stats ---------------------------------------------------------
    for team in team_ids:
        if not team:
            continue
        c = stats[team]
        out.team_stats.append(NTeamMatchStats(
            team_provider_id=team_pid(team),
            shots=c["shots"], shots_on_target=c["on_target"], corners=c["corners"],
            fouls=c["fouls"], offsides=c["offsides"], yellow_cards=c["yellow"],
            red_cards=c["red"], saves=c["saves"],
        ))

    # -- player lines -------------------------------------------------------
    for (team, _pid), p in players.items():
        played = p["on"] is not None
        minutes = 0
        if played:
            end = p["off"] if p["off"] is not None else full_time
            minutes = max(end - p["on"], 0)
        out.player_ratings.append(NPlayerRating(
            player_name=p["name"], team_provider_id=team_pid(team),
            player_provider_id=int(_pid), minutes=minutes, position=p["position"],
            number=p["number"], is_starter=p["starter"],
            goals=p["goals"] or None, assists=p["assists"] or None,
            yellow=p["yellow"] or None, red=p["red"] or None, saves=p["saves"] or None,
        ))
    return out


# --------------------------------------------------------------------------- #
# the provider
# --------------------------------------------------------------------------- #
class UefaProvider(BaseProvider):
    name = "uefa"
    supports_depth = True

    def __init__(
        self,
        competitions: list[str],
        matches_url: str = "https://match.uefa.com/v5",
        standings_url: str = "https://standings.uefa.com/v1",
        stats_url: str = "https://compstats.uefa.com/v1",
        min_request_interval: float = 0.4,
        include_qualifying: bool = False,
        timeout: float = 45.0,
    ) -> None:
        self.codes = [c for c in competitions if c in COMPETITIONS]
        self.matches_url = matches_url.rstrip("/")
        self.standings_url = standings_url.rstrip("/")
        self.stats_url = stats_url.rstrip("/")
        self.min_request_interval = min_request_interval
        self.include_qualifying = include_qualifying
        self._last_request_ts = 0.0
        self._client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )

    # -- HTTP ---------------------------------------------------------------
    def _throttle(self) -> None:
        wait = self.min_request_interval - (time.monotonic() - self._last_request_ts)
        if wait > 0:
            time.sleep(wait)

    def _get(self, url: str, params: dict | None = None, _retries: int = 3):
        self._throttle()
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        try:
            resp = self._client.get(url, params=clean)
        except httpx.HTTPError as exc:
            if _retries > 0:
                time.sleep(2 ** (3 - _retries))
                return self._get(url, params, _retries - 1)
            raise ProviderError(f"request to {url} failed: {exc}") from exc
        finally:
            self._last_request_ts = time.monotonic()

        if resp.status_code == 429 and _retries > 0:
            time.sleep(int(resp.headers.get("Retry-After", "10")) + 1)
            return self._get(url, params, _retries - 1)
        if resp.status_code in (500, 502, 503, 504) and _retries > 0:
            time.sleep(3)
            return self._get(url, params, _retries - 1)
        if resp.status_code >= 400:
            raise ProviderError(f"{url}: {resp.status_code} {resp.text[:200]}")
        return resp.json()

    def _paged(self, url: str, params: dict, page: int = 200) -> list:
        rows: list = []
        offset = 0
        while True:
            chunk = self._get(url, {**params, "limit": page, "offset": offset})
            rows += chunk
            if len(chunk) < page:
                return rows
            offset += page

    def close(self) -> None:
        self._client.close()

    # -- helpers ------------------------------------------------------------
    def _info(self, code: str) -> _CompetitionInfo:
        if code not in COMPETITIONS:
            raise ProviderError(f"UEFA provider has no competition '{code}'")
        return COMPETITIONS[code]

    def _competition(self, code: str, season: str | None = None) -> NCompetition:
        info = self._info(code)
        return NCompetition(
            provider_id=info.provider_id,
            code=code,
            name=info.name,
            type="CUP",
            emblem_url=_EMBLEM.format(code=code),
            area_name="Europe",
            area_code="EUR",
            current_season=season or current_season(),
        )

    def _phase(self) -> str:
        return "ALL" if self.include_qualifying else "TOURNAMENT"

    # -- BaseProvider -------------------------------------------------------
    def list_competitions(self) -> list[NCompetition]:
        return [self._competition(code) for code in self.codes]

    def get_matches(
        self,
        code: str,
        *,
        season: str | None = None,
        matchday: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[NMatch]:
        season = season or current_season()
        raw = self._paged(
            f"{self.matches_url}/matches",
            {
                "competitionId": self._info(code).uefa_id,
                "seasonYear": uefa_season_year(season),
                "phase": self._phase(),
                "fromDate": date_from.isoformat() if date_from else None,
                "toDate": date_to.isoformat() if date_to else None,
                "order": "ASC",
            },
        )
        matches = [map_match(m, code) for m in raw]
        if matchday is not None:
            matches = [m for m in matches if m.matchday == matchday]
        return matches

    def get_match(self, provider_id: int) -> NMatch:
        raw = self._get(f"{self.matches_url}/matches/{provider_id - UEFA_ID_OFFSET}")
        info = next(
            (c for c, i in COMPETITIONS.items() if str(i.uefa_id) == str(raw["competition"]["id"])),
            "",
        )
        return map_match(raw, info)

    def get_standings(self, code: str, season: str | None = None) -> NStandings:
        season = season or current_season()
        blocks = self._get(
            f"{self.standings_url}/standings",
            {
                "competitionId": self._info(code).uefa_id,
                "seasonYear": uefa_season_year(season),
                "phase": "TOURNAMENT",
            },
        )
        return map_standings(self._competition(code, season), season, blocks)

    def get_teams(self, code: str, season: str | None = None) -> tuple[NCompetition, list[NTeam]]:
        standings = self.get_standings(code, season)
        seen: dict[int, NTeam] = {}
        for row in standings.rows:
            seen.setdefault(row.team.provider_id, row.team)
        return standings.competition, list(seen.values())

    def get_scorers(
        self, code: str, season: str | None = None, limit: int = 20
    ) -> tuple[NCompetition, list[NScorer]]:
        season = season or current_season()
        entries = self._get(
            f"{self.stats_url}/player-ranking",
            {
                "competitionId": self._info(code).uefa_id,
                "seasonYear": uefa_season_year(season),
                "phase": "TOURNAMENT",
                "stats": "goals,assists,matches_appearance",
                "limit": limit,
                "offset": 0,
                "order": "DESC",
                "optionalFields": "PLAYER,TEAM",
            },
        )
        return self._competition(code, season), map_scorers(entries)

    # -- depth ---------------------------------------------------------------
    def get_match_depth(
        self, provider_id: int, home_id: str | None = None, away_id: str | None = None
    ) -> UefaDepth:
        """Lineups + the full event feed for one finished match."""
        match_id = provider_id - UEFA_ID_OFFSET
        try:
            lineups = self._get(f"{self.matches_url}/matches/{match_id}/lineups")
        except ProviderError as exc:
            log.info("no lineups for UEFA match %s (%s)", match_id, exc)
            lineups = None
        events = self._paged(
            f"{self.matches_url}/matches/{match_id}/events",
            {"filter": "ALL", "order": "ASC"},
            page=100,
        )
        return build_depth(lineups, events, home_id, away_id)
