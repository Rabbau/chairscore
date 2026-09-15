"""Fantasy Premier League provider — a free, official, key-less depth source
for the **current Premier League season only**.

`https://fantasy.premierleague.com/api/`
* ``/bootstrap-static/``      — players, teams, gameweeks (cache once per run)
* ``/fixtures/?event=N``      — a gameweek's fixtures + per-player stat lines
* ``/element-summary/{id}/``  — a player's per-fixture history (xG / xA)

Per finished fixture it yields per-player goals / assists / cards / saves /
bonus / BPS from one ``/fixtures`` call; xG / xA need one ``/element-summary``
call per player, gated by ``fpl_fetch_player_xg``.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime

import httpx

from app.providers.api_football import _name_overlap
from app.providers.base import NPlayerRating, NTeamMatchStats, ProviderError

log = logging.getLogger("chairscore.provider.fpl")

_POS = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}

# fixture["stats"] identifier -> NPlayerRating attribute
_STAT_ATTR = {
    "goals_scored": "goals",
    "assists": "assists",
    "yellow_cards": "yellow",
    "red_cards": "red",
    "saves": "saves",
    "bonus": "bonus",
    "bps": "bps",
}


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt


class FplProvider:
    name = "fpl"

    def __init__(
        self,
        base_url: str = "https://fantasy.premierleague.com/api",
        min_request_interval: float = 1.2,
        timeout: float = 20.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.min_request_interval = min_request_interval
        self._last_ts = 0.0
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (Chairscore)"},
            follow_redirects=True,
        )
        self._bootstrap: dict | None = None
        self._teams: dict[int, dict] = {}
        self._players: dict[int, dict] = {}
        self._es_cache: dict[int, list[dict]] = {}

    # -- HTTP -------------------------------------------------------------------
    def _throttle(self) -> None:
        wait = self.min_request_interval - (time.monotonic() - self._last_ts)
        if wait > 0:
            time.sleep(wait)

    def _get(self, path: str, params: dict | None = None, _retries: int = 2):
        self._throttle()
        try:
            resp = self._client.get(path, params=params or None)
        except httpx.HTTPError as exc:
            if _retries > 0:
                time.sleep(2)
                return self._get(path, params, _retries - 1)
            raise ProviderError(f"FPL request {path} failed: {exc}") from exc
        finally:
            self._last_ts = time.monotonic()
        if resp.status_code == 429 and _retries > 0:
            time.sleep(int(resp.headers.get("Retry-After", "5")) + 1)
            return self._get(path, params, _retries - 1)
        if resp.status_code >= 400:
            raise ProviderError(f"FPL {path}: {resp.status_code} {resp.text[:160]}")
        return resp.json()

    def close(self) -> None:
        self._client.close()

    # -- bootstrap -----------------------------------------------------------
    def _load_bootstrap(self) -> None:
        if self._bootstrap is not None:
            return
        data = self._get("/bootstrap-static/")
        self._bootstrap = data
        self._teams = {t["id"]: t for t in data["teams"]}
        self._players = {
            p["id"]: {
                "name": p["web_name"],
                "full_name": f"{p['first_name']} {p['second_name']}".strip(),
                "team": p["team"],
                "position": _POS.get(p["element_type"]),
            }
            for p in data["elements"]
        }

    def team_name(self, fpl_team_id: int) -> str:
        self._load_bootstrap()
        t = self._teams.get(fpl_team_id, {})
        return t.get("name", f"team {fpl_team_id}")

    def team_short(self, fpl_team_id: int) -> str | None:
        self._load_bootstrap()
        return (self._teams.get(fpl_team_id) or {}).get("short_name")

    def events(self) -> list[dict]:
        self._load_bootstrap()
        return self._bootstrap["events"]  # type: ignore[index]

    def current_event(self) -> int:
        evs = self.events()
        for e in evs:
            if e.get("is_current"):
                return e["id"]
        finished = [e["id"] for e in evs if e.get("finished")]
        return (max(finished) + 1) if finished else 1

    # -- fixtures ----------------------------------------------------------
    def fixtures(self, event: int) -> list[dict]:
        return self._get("/fixtures/", {"event": event})

    def find_fixture(
        self,
        on: date,
        home_name: str,
        away_name: str,
        *,
        event_hint: int | None = None,
        home_tla: str | None = None,
        away_tla: str | None = None,
    ) -> dict | None:
        """Locate the FPL fixture for a match known from football-data, by
        team-name overlap + kickoff date (±1 day). FPL gameweek numbering can
        drift from football-data matchday, so a few events around the hint are
        scanned."""
        self._load_bootstrap()
        hint = event_hint or self.current_event()
        candidates = [hint, hint - 1, hint + 1, hint - 2, hint + 2]
        seen: set[int] = set()

        best: tuple[float, dict] | None = None
        for ev in candidates:
            if ev < 1 or ev > 38 or ev in seen:
                continue
            seen.add(ev)
            for fx in self.fixtures(ev):
                ko = _parse_dt(fx.get("kickoff_time"))
                if ko and abs((ko.date() - on).days) > 1:
                    continue
                h, a = self.team_name(fx["team_h"]), self.team_name(fx["team_a"])
                score = _name_overlap(home_name, h) + _name_overlap(away_name, a)
                if home_tla and self.team_short(fx["team_h"]) == home_tla:
                    score += 0.5
                if away_tla and self.team_short(fx["team_a"]) == away_tla:
                    score += 0.5
                if score >= 1.0 and (best is None or score > best[0]):
                    best = (score, fx)
            if best and best[0] >= 2.5:
                break
        return best[1] if best else None

    # -- depth bundle ----------------------------------------------------------
    def _element_history(self, element_id: int) -> list[dict]:
        if element_id not in self._es_cache:
            data = self._get(f"/element-summary/{element_id}/")
            self._es_cache[element_id] = data.get("history", [])
        return self._es_cache[element_id]

    def match_depth(
        self, fixture: dict, *, want_player_xg: bool = True
    ) -> tuple[list[NTeamMatchStats], list[NPlayerRating]]:
        self._load_bootstrap()
        fid = fixture["id"]
        # element_id -> {attr: value}, plus which side it played for
        lines: dict[int, dict] = {}
        side_of: dict[int, str] = {}

        for stat in fixture.get("stats", []):
            attr = _STAT_ATTR.get(stat["identifier"])
            if attr is None:
                continue
            for side in ("h", "a"):
                for entry in stat.get(side, []):
                    eid = entry["element"]
                    lines.setdefault(eid, {})[attr] = entry["value"]
                    side_of[eid] = side

        team_h, team_a = fixture["team_h"], fixture["team_a"]
        ratings: list[NPlayerRating] = []
        for eid, vals in lines.items():
            meta = self._players.get(eid, {})
            side = side_of[eid]
            r = NPlayerRating(
                player_name=meta.get("name") or f"#{eid}",
                team_provider_id=team_h if side == "h" else team_a,
                player_provider_id=eid,
                position=meta.get("position"),
                goals=vals.get("goals"),
                assists=vals.get("assists"),
                yellow=vals.get("yellow"),
                red=vals.get("red"),
                saves=vals.get("saves"),
                bonus=vals.get("bonus"),
                bps=vals.get("bps"),
            )
            if want_player_xg:
                for h in self._element_history(eid):
                    if h.get("fixture") == fid:
                        r.xg = float(h["expected_goals"]) if h.get("expected_goals") else None
                        r.xa = float(h["expected_assists"]) if h.get("expected_assists") else None
                        r.minutes = h.get("minutes")
                        r.is_starter = bool(h.get("starts"))
                        break
            ratings.append(r)

        # team rollups
        stats: list[NTeamMatchStats] = []
        for fpl_id in (team_h, team_a):
            side_players = [r for r in ratings if r.team_provider_id == fpl_id]
            xgs = [r.xg for r in side_players if r.xg is not None]
            stats.append(
                NTeamMatchStats(
                    team_provider_id=fpl_id,
                    xg=round(sum(xgs), 2) if xgs else None,
                    saves=_sum(side_players, "saves"),
                    yellow_cards=_sum(side_players, "yellow"),
                    red_cards=_sum(side_players, "red"),
                )
            )
        return stats, ratings


def _sum(players: list[NPlayerRating], attr: str) -> int | None:
    vals = [getattr(p, attr) for p in players if getattr(p, attr)]
    return sum(vals) if vals else None
