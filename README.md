# [Chairscore](https://rabbau.github.io/chairscore/)

Football stats site (SofaScore-style) — league tables, fixtures, results, match details, top scorers.

- **Backend:** Python 3.12 · FastAPI · SQLAlchemy · APScheduler
- **Frontend:** React + TypeScript (Vite) · React Router · TanStack Query
- **Data sources:** [football-data.org](https://www.football-data.org/) v4 (free) +
  [Fantasy Premier League](https://fantasy.premierleague.com/api/) (free, current PL season) +
  [Football-Data.co.uk](https://football-data.co.uk) (free CSV, match stats for all 5 leagues) +
  [UEFA](https://www.uefa.com)'s own key-less API (Champions League + Europa League, incl.
  lineups and events)
- **DB:** SQLite in dev, PostgreSQL in production
- **Also ships as a static site** — `docs/`, no backend needed, see
  [Static export & GitHub Pages](#static-export--github-pages)

## Layout

```
backend/     FastAPI app, data ingestion, scheduler, static JSON export
frontend/    React SPA — live (backend API) and static (docs/) builds share
             every component; only the data-fetching layer differs
docs/        built static site — served as-is by GitHub Pages
.github/     optional scheduled Action that keeps docs/ current
```

## Quick start

### Backend

```bash
cd backend
py -3.12 -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
cp .env.example .env          # then paste your football-data.org token into .env
.venv/Scripts/python -m uvicorn app.main:app --reload
```

API runs at http://localhost:8000 — docs at http://localhost:8000/docs

Populate the database from the API:

```bash
.venv/Scripts/python -m app.ingest --full
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

App runs at http://localhost:5173

## Get a data token

Register (free, email only) at https://www.football-data.org/client/register and put the
token in `backend/.env` as `FOOTBALL_DATA_API_TOKEN`. Free tier: 10 requests/minute,
~13 competitions (Premier League, La Liga, Bundesliga, Serie A, Ligue 1, and more).
The **Champions League and Europa League don't need it** — they come from UEFA's own
key-less API (below), which also has the Europa League that football-data.org's free
tier lacks.

## Data sources

**Breadth — [football-data.org](https://www.football-data.org/) (free):** standings,
fixtures, results (FT + HT), top scorers, squads, referees — across all tracked
competitions. No event timeline, xG, or player ratings on the free tier.

**Depth, current PL season — [Fantasy Premier League](https://fantasy.premierleague.com/api/) (free, official, on by default):**
per-player goals / assists / cards / saves / bonus / BPS and per-player xG / xA
for finished Premier League matches. No key, no meaningful rate limit. One
`/fixtures` call covers a gameweek; xG / xA cost one `/element-summary` call per
player (`FPL_FETCH_PLAYER_XG`). PL only. Toggle with `FPL_ENABLED`.

**Depth, every tracked league — [Football-Data.co.uk](https://football-data.co.uk) (free CSV, no key, on by default):**
shots, shots on target, corners, fouls, cards and (2026-27 files onward) team
xG, for **all 5 tracked leagues**, not just one. One CSV per competition-season
covers every match in it — cheap enough that a whole run is a handful of
requests, not one per match. Team names differ from football-data.org's
("Man City" vs "Manchester City FC") — matched by accent-insensitive token
overlap plus a small alias table for the genuine abbreviations (`app/providers/football_data_co_uk.py`).
Toggle with `FDCOUK_ENABLED`.

**Breadth + depth, Champions League & Europa League — [UEFA](https://www.uefa.com) (free, no key, on by default):**
the backends uefa.com itself calls (`match.` / `standings.` / `compstats.uefa.com`,
each publishes an OpenAPI spec at `/v3/api-docs`): fixtures and results (incl.
extra time and penalty shoot-outs), the league-phase table, top scorers, **lineups**
and the full **event feed** — goals with assists and running score, cards,
substitutions. There is no per-match team-stats endpoint, so shots, shots on
target, corners, fouls, offsides, cards and saves are *counted from the event
feed* (checked against UEFA's own aggregates: on-target shots, corners, fouls and
yellows matched exactly); possession and passes aren't available per match.
UEFA's clubs are matched onto the league teams football-data.org already created
(name + UEFA's three-letter code, recorded in `team_external_refs`), so Arsenal is
one team, with one head-to-head history, in the league and in Europe. Toggle with
`UEFA_ENABLED`; which competitions with `UEFA_COMPETITIONS` (`CL,EL`). Unofficial:
fine for a personal project, but it can change or block without notice.

**Depth, any tracked league — [API-Football](https://dashboard.api-football.com/) (optional, off by default):**
goal / card / substitution timeline, per-team statistics (possession, shots,
xG …) and 0–10 player ratings. Provider + pipeline are built and tested, but the
**free plan only serves seasons 2022–2024** (100 req/day), so `DEPTH_ENABLED=false`.
A paid key unlocks the current season. See
[Data-source alternatives](#data-source-alternatives) for other options.

The provider layer (`backend/app/providers/`) normalizes every source behind the
same dataclasses; the DB and API code never see a raw provider response. Each
depth source resolves a football-data match to its own fixture id by team name +
date, caches it in `match_external_refs`, and writes `match_team_stats` /
`match_player_ratings` rows tagged with its `source`. When several sources cover
one match (a Premier League game has Football-Data.co.uk *and* FPL), the API folds
them into one row per team (`app/merge.py`, `merged_team_stats`): each stat comes
from the most trusted source that has it, and the UI says which.

**Coverage today** (`python -m app.report` prints this for your own database):

| | results & table | team stats | events | lineups | player stats |
|-|-|-|-|-|-|
| Premier League | ✅ | shots, SOT, corners, fouls, cards, xG | – | – | ✅ FPL: BPS, xG/xA |
| La Liga · Bundesliga · Serie A · Ligue 1 | ✅ | shots, SOT, corners, fouls, cards, xG | – | – | – |
| Champions League · Europa League | ✅ | shots, SOT, corners, fouls, offsides, cards, saves | ✅ | ✅ | minutes, goals, assists, cards |

Still no free source for possession / passes anywhere, or for events and lineups
in the four leagues besides the Premier League.

## Data-source alternatives

If a paid API-Football plan isn't on the table, options for match depth (events,
xG, lineups, ratings) — a new provider drops into `app/providers/` behind the
existing normalized dataclasses:

| source | cost | gives | covers | notes |
|--------|------|-------|--------|-------|
| **API-Football free, 2022–24** | free | events, team stats, **ratings** | those 3 seasons, all tracked leagues | already integrated — set `DEPTH_ENABLED=true` and enrich historical matchdays; current season stays bare |
| **[FPL API](https://fantasy.premierleague.com/api/bootstrap-static/)** | free, official | goals, assists, xG, xA, BPS, bonus | **Premier League only**, current season | ✅ **integrated** (`app/providers/fpl.py`); `--fpl`. BPS ≈ a per-player rating |
| **[Understat](https://understat.com)** | free | **xG** per shot, player xG/xA | EPL, La Liga, Bundesliga, Serie A, Ligue 1, RPL | ⚠️ now behind Cloudflare — plain HTTP clients (httpx, `soccerdata`) get a challenge page; needs a headless browser |
| **[FBref](https://fbref.com)** (StatsBomb) | free | full player + team match stats, xG, **lineups**, formations | dozens of comps, current season | `soccerdata.FBref`; 1 req / 3 s, ToS discourages scraping/redistribution — fine for personal use |
| **[StatsBomb Open Data](https://github.com/statsbomb/open-data)** | free, CC BY-NC-SA | full **event-level** data, xG, freeze frames | World Cups, Euro 2024, Bundesliga 23-24, WSL, Messi-era Barça… | legally clean; great for a showcase, not for current top-5 leagues |
| **[Football-Data.co.uk](https://www.football-data.co.uk)** | free CSV | shots, SOT, corners, fouls, cards, **team xG** (2026-27+) | ~22 leagues, decades + current | ✅ **integrated** (`app/providers/football_data_co_uk.py`); `--fdcouk`. No lineups/events/player stats |
| **[UEFA](https://www.uefa.com)** (`match.uefa.com` …) | free, no key | fixtures, lineups, event feed, tables, scorers | **Champions League, Europa League** (+ Conference) | ✅ **integrated** (`app/providers/uefa.py`); `--uefa`. Unofficial but first-party; possession/passes not per match |
| **[Premier League](https://www.premierleague.com) official API** (`footballapi.pulselive.com`) | free, no key (sends the site's `Origin` header) | 150+ team stats per match **incl. possession + passes**, events, lineups | Premier League only | 🔎 verified reachable (2026-09), **not integrated** — the natural next gap-filler for PL |
| **[TheSportsDB](https://www.thesportsdb.com)** | free key is truncated to 5 rows per response; ~$3–9/mo Patreon for real data | lineups, event timeline, stats | popular leagues, current season | real API + key; cheaper but less consistent than API-Football |

**Where this leaves us:** FPL covers current-season PL per-player depth,
Football-Data.co.uk covers team-level match stats (+ xG) for **all 5** leagues,
and UEFA covers the Champions and Europa League end to end — all free, all done.
What's still missing for the other 4 leagues: lineups, an event timeline, and
possession / passes. FBref via `soccerdata` is the realistic free option there
(mind the ToS); otherwise API-Football Pro is the clean paid upgrade — the
pipeline already supports it, and its free tier can enrich 2022–24 today.

Probed from a home connection in 2026-09 and **not usable**: ESPN's site API
(Akamai "Access Denied"), FBref (Cloudflare challenge), Sofascore and Understat
(blocked). openfootball has fresh fixtures for eight leagues but only scores —
no goals or stats.

Scraping Sofascore / FlashScore / WhoScored internal endpoints would give
everything including ratings, but violates their ToS, breaks without notice, and
gets IPs blocked — not viable for a public site.

## Ingestion

```bash
.venv/Scripts/python -m app.ingest --full        # everything, tracked competitions
.venv/Scripts/python -m app.ingest --matches     # recent-window matches only
.venv/Scripts/python -m app.ingest --standings   # standings + scorers
.venv/Scripts/python -m app.ingest --reference   # competitions + teams + squads
.venv/Scripts/python -m app.ingest --depth       # API-Football events/stats/ratings
.venv/Scripts/python -m app.ingest --fpl         # FPL per-player data (current PL season)
.venv/Scripts/python -m app.ingest --fdcouk      # Football-Data.co.uk match stats (all leagues)
.venv/Scripts/python -m app.ingest --uefa        # Champions/Europa League: fixtures, then lineups + events
.venv/Scripts/python -m app.ingest --seasons 2023,2024,2025   # backfill past results
```

`--seasons` pulls past-season match results (one request per competition per
season). They power head-to-head on the match page and the season switcher.
`--full` also pulls the Champions / Europa League season from UEFA (after the
leagues, so UEFA's clubs can be matched onto their league teams).

The enrichers (`--fpl`, `--fdcouk`, `--uefa`) are **gap-fillers**: each run takes
the finished matches of the *current season* that still lack that source's data,
newest first, up to a per-run budget (`FPL_MAX_MATCHES_PER_RUN`,
`FDCOUK_MAX_MATCHES_PER_RUN`, `UEFA_MAX_MATCHES_PER_RUN`) — so a backlog fills in
over a few runs instead of being skipped once it is older than a couple of weeks.
`python -m app.report` shows what is still missing.

With a token set, the backend self-syncs on a schedule (one pass ~15s after
start, then matches every 15 min, standings every 6 h, reference data daily,
FPL + Football-Data.co.uk every 6 h, UEFA every 30 min, and — when
`API_FOOTBALL_KEY` is set — depth every 12 h). Trigger over HTTP:
`POST /api/admin/sync?mode=full` (or `matches` / `standings` / `reference` /
`depth` / `fpl` / `fdcouk` / `uefa`) with header
`X-Admin-Token: <ADMIN_TOKEN>`.

**Running with `ENABLE_SCHEDULER=false`** (handy while iterating locally so
you're not hitting three APIs on every reload): nothing syncs automatically,
so scores/statuses go stale the moment a fixture kicks off. `--matches` won't
necessarily catch you up — it only looks back `match_window_past_days` (3, by
default). `--full` has no date bound and re-pulls each competition's whole
fixture list, so it's the right one-shot catch-up after any longer gap.

## Database migrations

Schema is managed with Alembic. The app runs `alembic upgrade head` on startup
(`RUN_MIGRATIONS_ON_STARTUP`, on by default); a `create_all()` database from an
earlier version is auto-stamped at head on first run, no data loss.

```bash
cd backend
.venv/Scripts/alembic upgrade head                       # apply migrations
.venv/Scripts/alembic revision --autogenerate -m "..."   # after changing models
.venv/Scripts/alembic downgrade -1                        # roll back one
.venv/Scripts/alembic current                             # where am I
```

`tests/test_migrations.py` fails if the models and the migration chain disagree.

## Deployment

### Docker Compose (Postgres + API + static frontend)

```bash
cp backend/.env.example backend/.env     # fill in FOOTBALL_DATA_API_TOKEN, change ADMIN_TOKEN
docker compose up --build                # → http://localhost:8080
```

Three services (`docker-compose.yml`):

| service   | image / build     | role                                                        |
|-----------|-------------------|------------------------------------------------------------|
| `db`      | `postgres:16`     | data, on the `pgdata` named volume                          |
| `backend` | `backend/Dockerfile` | FastAPI + scheduler; runs `alembic upgrade head` on start |
| `web`     | `frontend/Dockerfile` | nginx serving the built SPA, proxying `/api` → `backend` |

`backend` reads `backend/.env` for the API tokens; compose overrides `DATABASE_URL`
to point at the `db` service. The SPA is same-origin behind nginx, so CORS isn't
involved. First boot: the scheduler runs a full sync ~15 s after start; or trigger
it now with `curl -XPOST -H "X-Admin-Token: <token>" localhost:8080/api/admin/sync`.

Just Postgres for local dev (`uvicorn --reload` on the host):

```bash
docker compose up db
# backend/.env: DATABASE_URL=postgresql+psycopg://chairscore:chairscore@localhost:5432/chairscore
```

### Production config

| var | notes |
|-----|-------|
| `DATABASE_URL` | `postgresql+psycopg://user:pass@host:5432/chairscore` — needs the `.[postgres]` extra (baked into the image) |
| `ADMIN_TOKEN` | **change from `changeme`** — guards `POST /api/admin/sync` |
| `FOOTBALL_DATA_API_TOKEN` | required for any data |
| `CORS_ORIGINS` | only if the SPA is served from a different origin than the API |
| `ENABLE_SCHEDULER` | see caveat below |
| `RUN_MIGRATIONS_ON_STARTUP` | `true` (default) applies migrations on boot; set `false` to run `alembic upgrade head` as a separate deploy step |

**Scaling caveat:** the APScheduler jobs run in-process, so exactly one backend
process may have `ENABLE_SCHEDULER=true`. Don't run `uvicorn --workers N` with the
scheduler on; for more web capacity, add replicas with `ENABLE_SCHEDULER=false`.

### Without Docker

Build the SPA (`cd frontend && npm run build`) and serve `dist/` from any static
host or nginx, proxying `/api` to the API. Run the API with
`uvicorn app.main:app` (or `gunicorn -k uvicorn.workers.UvicornWorker app.main:app`,
single worker) behind a reverse proxy.

## Static export & GitHub Pages

A second way to ship this, with **no backend running at all**: export the
database to a tree of JSON files and serve a static build of the SPA that
reads those files instead of calling `/api/*`. `docs/` is that build — commit
it and GitHub Pages serves it directly.

```bash
cd backend
.venv/Scripts/python -m app.export_static --out ../docs/data   # DB -> JSON

cd ../frontend
npm run build:static                                            # -> ../docs
```

Then: **Settings → Pages → Source: Deploy from a branch → branch `main` (or
whichever you push), folder `/docs`.**

Sanity-check the build before pushing — serve `docs/` exactly as GitHub Pages
would, no dev server involved:

```bash
cd docs
python -m http.server 8080
```

Open http://localhost:8080/#/ — this is the actual production artifact (same
static files, same relative paths), so if it looks right here it'll look right
on Pages. Confirms the three things that actually break on Pages: hash routing
on a hard refresh of a deep link, relative asset/data paths, and that
`docs/data` has the JSON the build expects.

How it holds together:

- **One frontend, two data layers.** `frontend/src/api/liveClient.ts` calls
  the REST API; `staticClient.ts` fetches the same shapes from `docs/data/*.json`
  and resolves things the API would (latest season, search) on the client.
  `api/client.ts` picks one by `VITE_STATIC` — every page, component and hook
  is unaware which. `npm run build:static` sets `VITE_STATIC=true`, builds
  with a relative base (`./`, works from any subpath with zero per-repo
  config) into `../docs`, and switches the router to `HashRouter` — GitHub
  Pages has no server-side rewrite for deep links, so routes live at
  `#/competitions/PL` instead of `/competitions/PL`. `emptyOutDir: false` so
  rebuilding the app never wipes `docs/data`.
- **One export, the API's own code.** `backend/app/export_static.py` calls
  the *exact* endpoint functions `app/api/*.py` use (`db=` passed directly
  instead of resolved via `Depends`) and dumps their Pydantic responses to
  files — competitions, every season's standings/fixtures/scorers, every
  team, and match detail (head-to-head, form, events, player stats) for each
  tracked competition's **current** season (older seasons keep their table
  and results list — `--all-seasons` lifts this, slower). ~1750 files, ~28 MB
  for 5 competitions × 4 seasons.
- **Keeping it current.** `.github/workflows/refresh-data.yml` — a daily
  scheduled Action that syncs (incrementally, via a rolling cache of the sync
  DB) and re-exports `docs/data`, then commits it. Needs a
  `FOOTBALL_DATA_API_TOKEN` repository secret (the job fails loudly without
  it, rather than committing an empty snapshot). Skip it entirely and just
  re-run the two commands above by hand whenever you want a fresher snapshot.
- **The committed JSON is the data store.** Every match's detail file keeps
  what the enrichment providers collected (events, stats, lineups — each
  tagged with its source), so `docs/data` doubles as a durable copy of it all.
  `python -m app.restore_static --from ../docs/data` puts back whatever a
  database is missing — the workflow runs it after the breadth sync — so a
  wiped Actions cache (or a fresh clone) doesn't make the next export drop the
  stats of matches older than the providers' look-back. It only adds what is
  missing, keyed on provider ids, and never overwrites fresher data.

## Roadmap

1. ✅ Scaffold, ingestion, home / competition / match / team pages
2. ✅ Alembic migrations
3. ⏸ Second data provider (API-Football) for match events, statistics, player
   ratings — provider, enrichment pipeline and schema are done and tested, but
   the **free plan only exposes seasons 2022–2024**, so it's disabled
   (`DEPTH_ENABLED=false`). Set a paid key + `DEPTH_ENABLED=true` to light it up.
4. ✅ Head-to-head record + recent form on the match page (needs past seasons
   backfilled — see `--seasons`)
5. ✅ Global search (`/api/search`), a season switcher on the competition page
   (`/api/competitions/{code}/seasons`), and client-side favourites (localStorage,
   shown in the sidebar)
6. ✅ Containerised deploy — `docker compose up` brings up Postgres + API +
   nginx-served SPA; see [Deployment](#deployment)
7. ✅ FPL depth provider — per-player goals / assists / bonus / BPS / xG / xA on
   current-season Premier League match pages (`app/providers/fpl.py`, `--fpl`,
   the "Player stats" card). Free, official, no key.
8. ✅ Static JSON export + GitHub Pages build (`docs/`), dark/monospace/lime
   restyle, starball favicon — see
   [Static export & GitHub Pages](#static-export--github-pages)
9. ✅ Football-Data.co.uk depth provider — shots / shots on target / corners /
   fouls / cards / team xG on **all 5** tracked leagues' match pages (not just
   PL), the "Match stats" card. Free CSV, no key.
10. ✅ UEFA provider for the **Champions League and Europa League** (fixtures,
    league-phase table, scorers, lineups, events, and team stats counted from
    the event feed — `app/providers/uefa.py`, `--uefa`), clubs matched onto their
    league teams; server-side merge of multiple sources' team stats with
    provenance (`app/merge.py`); gap-driven enrichers; restore-from-snapshot
    (`app/restore_static.py`) and a coverage report (`app/report.py`).
