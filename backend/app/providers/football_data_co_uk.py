"""Football-Data.co.uk provider — free CSV match statistics (shots, corners,
cards and, since the 2026-27 files, team xG) for many European leagues. No
key, no auth, no rate limit worth worrying about.

One CSV per competition per season:
``https://football-data.co.uk/mmz4281/{yy}{yy}/{code}.csv`` — e.g. season
"2025" (our start-year convention) -> "2526", code "E0" for the Premier
League. The column *set* varies by season (xG columns are new) so rows are
always read by name (``csv.DictReader``), never by position.

No player-level data here — team totals only, which is exactly what
``MatchTeamStat`` already models; nothing writes to ``MatchPlayerRating``.
"""

from __future__ import annotations

import csv
import io
import logging
import time
from datetime import date, datetime

import httpx

from app.providers.api_football import _name_overlap
from app.providers.base import NTeamMatchStats, ProviderError

log = logging.getLogger("chairscore.provider.football_data_co_uk")

# our football-data.org code -> football-data.co.uk code
CODE_TO_FDCOUK: dict[str, str] = {
    "PL": "E0",
    "PD": "SP1",
    "BL1": "D1",
    "SA": "I1",
    "FL1": "F1",
    "ELC": "E1",
    "DED": "N1",
    "PPL": "P1",
}

# football-data.co.uk uses short/local club names that don't token-match our
# (football-data.org) full names — e.g. "Man City" vs "Manchester City FC".
# Verified empirically against every club in the 5 tracked leagues' current
# season (see chairscore-project memory); add entries here as new mismatches
# turn up rather than guessing ahead of time.
_ALIASES: dict[str, str] = {
    "man city": "manchester city",
    "man united": "manchester united",
    "nott'm forest": "nottingham forest",
    "ath madrid": "atletico madrid",
    "ath bilbao": "athletic club",
    "espanol": "espanyol",
    "bayern munich": "bayern munchen",
    "ein frankfurt": "eintracht frankfurt",
    "hamburg": "hamburger",
    "m'gladbach": "monchengladbach",
    "inter": "internazionale",
    "brest": "brestois",
    "lyon": "lyonnais",
    "rennes": "rennais",
}


def _alias(name: str) -> str:
    return _ALIASES.get(name.strip().lower(), name)


def _fdcouk_season(season: str) -> str:
    """Our "2025" (start year) -> their "2526"."""
    start = int(season)
    return f"{start % 100:02d}{(start + 1) % 100:02d}"


def _parse_date(value: str) -> date | None:
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _int(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _float(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


class FootballDataCoUkProvider:
    name = "football-data.co.uk"

    def __init__(
        self,
        base_url: str = "https://football-data.co.uk/mmz4281",
        min_request_interval: float = 1.0,
        timeout: float = 20.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.min_request_interval = min_request_interval
        self._last_ts = 0.0
        self._client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (Chairscore)"},
            follow_redirects=True,
        )
        # one CSV covers a whole league-season -> cache it, not per-match.
        self._cache: dict[tuple[str, str], list[dict]] = {}

    def close(self) -> None:
        self._client.close()

    def _throttle(self) -> None:
        wait = self.min_request_interval - (time.monotonic() - self._last_ts)
        if wait > 0:
            time.sleep(wait)

    def rows(self, code: str, season: str) -> list[dict]:
        """All CSV rows for one of our competition codes + season. Cached —
        cheap to call repeatedly."""
        fdcouk_code = CODE_TO_FDCOUK.get(code.upper())
        if fdcouk_code is None:
            return []
        key = (fdcouk_code, season)
        if key in self._cache:
            return self._cache[key]

        self._throttle()
        url = f"{self.base_url}/{_fdcouk_season(season)}/{fdcouk_code}.csv"
        try:
            resp = self._client.get(url)
        except httpx.HTTPError as exc:
            raise ProviderError(f"football-data.co.uk request {url} failed: {exc}") from exc
        finally:
            self._last_ts = time.monotonic()
        if resp.status_code == 404:
            self._cache[key] = []
            return []
        if resp.status_code >= 400:
            raise ProviderError(f"football-data.co.uk {url}: {resp.status_code}")

        text = resp.content.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        parsed = [r for r in reader if r.get("HomeTeam") and r.get("AwayTeam")]
        self._cache[key] = parsed
        log.info("[%s] %s: %d rows", fdcouk_code, _fdcouk_season(season), len(parsed))
        return parsed

    def find_row(
        self, code: str, season: str, on: date, home_name: str, away_name: str
    ) -> dict | None:
        """Locate the CSV row for a match known from football-data.org, by
        date (±1 day) + fuzzy team-name overlap."""
        best: tuple[float, dict] | None = None
        for row in self.rows(code, season):
            row_date = _parse_date(row.get("Date", ""))
            if row_date is None or abs((row_date - on).days) > 1:
                continue
            score = _name_overlap(
                _alias(home_name), _alias(row.get("HomeTeam", ""))
            ) + _name_overlap(_alias(away_name), _alias(row.get("AwayTeam", "")))
            if score >= 1.2 and (best is None or score > best[0]):
                best = (score, row)
        return best[1] if best else None

    @staticmethod
    def team_stats(row: dict) -> tuple[NTeamMatchStats, NTeamMatchStats]:
        """(home, away) — ``team_provider_id`` is left unset; the caller
        already knows which side is which from the row it resolved."""
        home = NTeamMatchStats(
            shots=_int(row.get("HS")),
            shots_on_target=_int(row.get("HST")),
            corners=_int(row.get("HC")),
            fouls=_int(row.get("HF")),
            yellow_cards=_int(row.get("HY")),
            red_cards=_int(row.get("HR")),
            xg=_float(row.get("HxG")),
        )
        away = NTeamMatchStats(
            shots=_int(row.get("AS")),
            shots_on_target=_int(row.get("AST")),
            corners=_int(row.get("AC")),
            fouls=_int(row.get("AF")),
            yellow_cards=_int(row.get("AY")),
            red_cards=_int(row.get("AR")),
            xg=_float(row.get("AxG")),
        )
        return home, away
