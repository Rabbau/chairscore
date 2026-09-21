import { Link, useParams } from 'react-router-dom'

import type { Match, MatchDetail, MergedTeamStat, PlayerRating, TeamStat } from '../api/types'
import { useMatch } from '../api/client'
import { Crest } from '../components/Crest'
import { FormBadges } from '../components/FormBadges'
import { MatchRow } from '../components/MatchRow'
import { ErrorState, Loading } from '../components/States'
import {
  isLive,
  kickoffTime,
  parseUtc,
  resultFor,
  stageLabel,
  type FormResult,
} from '../lib/format'

/** Recent finished matches for a team, oldest → newest, as W/D/L. */
function formOf(matches: Match[], teamId: number): FormResult[] {
  return matches
    .map((m) => resultFor(m, teamId))
    .filter((r): r is FormResult => r != null)
    .reverse()
}

/** When more than one depth source covers a match, use whichever row for
 * this team actually has more fields filled in (e.g. football-data.co.uk's
 * shots/corners/cards beats FPL's xG-only row for the same PL match). */
function richestStat(stats: TeamStat[], teamId: number): TeamStat | undefined {
  const filled = (s: TeamStat) =>
    [
      s.xg,
      s.possession,
      s.shots,
      s.shots_on_target,
      s.corners,
      s.fouls,
      s.offsides,
      s.yellow_cards,
      s.red_cards,
      s.saves,
    ]
      .filter((v) => v != null).length
  return stats
    .filter((s) => s.team_id === teamId)
    .reduce<TeamStat | undefined>((best, s) => (!best || filled(s) > filled(best) ? s : best), undefined)
}

export function MatchPage() {
  const { id = '' } = useParams()
  const { data: match, isLoading, error } = useMatch(id)

  if (isLoading) return <Loading />
  if (error) return <ErrorState error={error} />
  if (!match) return null

  const done = match.status === 'FINISHED' || match.status === 'AWARDED'
  const fullTime =
    match.duration === 'PENALTY_SHOOTOUT'
      ? 'After penalties'
      : match.duration === 'EXTRA_TIME'
        ? 'After extra time'
        : 'Full time'
  const stage = stageLabel(match.stage)
  const hasShootout = match.home_score_pen != null && match.away_score_pen != null
  const statusText = isLive(match.status)
    ? 'LIVE'
    : done
      ? fullTime
      : `${parseUtc(match.utc_date).toLocaleDateString([], {
          weekday: 'long',
          day: 'numeric',
          month: 'long',
        })} · ${kickoffTime(match.utc_date)}`

  return (
    <>
      <div className="page-title">
        <Link to={`/competitions/${match.competition.code}`} className="muted">
          ‹ {match.competition.name}
        </Link>
        {stage && <span className="faint"> · {stage}</span>}
      </div>

      <div className="card">
        <div className="scoreline">
          <Link to={`/teams/${match.home_team.id}`} className="scoreline__team">
            <Crest src={match.home_team.crest_url} alt={match.home_team.name} size="xl" />
            <span>{match.home_team.name}</span>
            <FormBadges results={formOf(match.home_form, match.home_team.id)} />
          </Link>

          <div style={{ textAlign: 'center' }}>
            <div className="scoreline__score">
              {match.home_score ?? '–'}
              <span className="faint"> : </span>
              {match.away_score ?? '–'}
            </div>
            <div className={`chip${isLive(match.status) ? ' chip--live' : ''}`} style={{ marginTop: 8 }}>
              {statusText}
            </div>
            {hasShootout && (
              <div className="faint" style={{ fontSize: 12, marginTop: 6 }}>
                Penalties {match.home_score_pen}–{match.away_score_pen}
              </div>
            )}
            {match.home_score_ht != null && (
              <div className="faint" style={{ fontSize: 12, marginTop: hasShootout ? 2 : 6 }}>
                HT {match.home_score_ht}–{match.away_score_ht}
              </div>
            )}
          </div>

          <Link to={`/teams/${match.away_team.id}`} className="scoreline__team">
            <Crest src={match.away_team.crest_url} alt={match.away_team.name} size="xl" />
            <span>{match.away_team.name}</span>
            <FormBadges results={formOf(match.away_form, match.away_team.id)} />
          </Link>
        </div>
      </div>

      <EventsCard match={match} />
      <MatchStatsCard match={match} />
      <LineupsCard match={match} />
      <PlayerStatsCard match={match} />
      <HeadToHeadCard match={match} />
      <MatchInfoCard match={match} />
    </>
  )
}

const SOURCE_NAME: Record<string, string> = {
  fpl: 'Fantasy Premier League',
  'api-football': 'API-Football',
  'football-data.co.uk': 'Football-Data.co.uk',
  uefa: 'UEFA',
}

/** "via UEFA" / "via Football-Data.co.uk + Fantasy Premier League" */
function viaLabel(sources: string[]): string | null {
  const names = [...new Set(sources)].map((s) => SOURCE_NAME[s]).filter(Boolean)
  return names.length ? `via ${names.join(' + ')}` : null
}

interface StatRowDef {
  label: string
  home: number | null
  away: number | null
  decimals?: number
  /** where the value came from, when it was merged from several sources */
  source?: string
}

/** Prefer the server-side merge; fall back to picking a row for snapshots that predate it. */
function statsFor(match: MatchDetail, teamId: number): MergedTeamStat | undefined {
  const merged = match.merged_team_stats?.find((s) => s.team_id === teamId)
  if (merged) return merged
  const row = richestStat(match.team_stats ?? [], teamId)
  return row && { ...row, sources: [row.source], field_sources: {} }
}

function MatchStatsCard({ match }: { match: MatchDetail }) {
  const home = statsFor(match, match.home_team.id)
  const away = statsFor(match, match.away_team.id)
  if (!home && !away) return null

  const stat = (
    label: string,
    key: keyof MergedTeamStat & keyof TeamStat,
    decimals?: number,
  ): StatRowDef => ({
    label,
    home: (home?.[key] as number | null | undefined) ?? null,
    away: (away?.[key] as number | null | undefined) ?? null,
    decimals,
    source: home?.field_sources[key] ?? away?.field_sources[key],
  })

  const rows: StatRowDef[] = [
    stat('xG', 'xg', 2),
    stat('Possession', 'possession'),
    stat('Shots', 'shots'),
    stat('Shots on target', 'shots_on_target'),
    stat('Corners', 'corners'),
    stat('Fouls', 'fouls'),
    stat('Offsides', 'offsides'),
    stat('Saves', 'saves'),
    stat('Yellow cards', 'yellow_cards'),
    stat('Red cards', 'red_cards'),
  ].filter((r) => r.home != null || r.away != null)
  if (rows.length === 0) return null

  const via = viaLabel([...(home?.sources ?? []), ...(away?.sources ?? [])])

  return (
    <div className="card">
      <div className="card__head">
        Match stats
        {via && <span className="faint"> · {via}</span>}
      </div>
      <div className="stat-rows">
        {rows.map((r) => (
          <StatRow key={r.label} {...r} />
        ))}
      </div>
    </div>
  )
}

function StatRow({ label, home, away, decimals, source }: StatRowDef) {
  const h = home ?? 0
  const a = away ?? 0
  const total = h + a || 1
  const fmt = (v: number | null) => (v == null ? '–' : decimals ? v.toFixed(decimals) : String(v))
  return (
    <div className="stat-row">
      <span className="stat-row__val">{fmt(home)}</span>
      <div className="stat-row__mid">
        <span
          className="stat-row__label"
          title={source && SOURCE_NAME[source] ? `from ${SOURCE_NAME[source]}` : undefined}
        >
          {label}
        </span>
        <div className="h2h-bar">
          <span className="h2h-bar__w" style={{ width: `${(h / total) * 100}%` }} />
          <span className="h2h-bar__l" style={{ width: `${(a / total) * 100}%` }} />
        </div>
      </div>
      <span className="stat-row__val">{fmt(away)}</span>
    </div>
  )
}

function PlayerStatsCard({ match }: { match: MatchDetail }) {
  // Lineup-only sources (UEFA) have no BPS / rating to rank by — LineupsCard shows those.
  const ratings = (match.player_ratings ?? []).filter((r) => r.rating != null || r.bps != null)
  if (ratings.length === 0) return null

  const source = ratings[0]?.source ?? ''

  const forTeam = (teamId: number) =>
    ratings
      .filter((r) => r.team_id === teamId)
      .sort((a, b) => (b.bps ?? b.rating ?? 0) - (a.bps ?? a.rating ?? 0))

  return (
    <div className="card">
      <div className="card__head">
        Player stats
        {viaLabel([source]) && <span className="faint"> · {viaLabel([source])}</span>}
      </div>

      <div className="ratings">
        <div className="ratings__col">
          {forTeam(match.home_team.id).map((r) => (
            <RatingRow key={r.player_name} r={r} />
          ))}
        </div>
        <div className="ratings__col">
          {forTeam(match.away_team.id).map((r) => (
            <RatingRow key={r.player_name} r={r} align="right" />
          ))}
        </div>
      </div>
    </div>
  )
}

const POSITION_ORDER: Record<string, number> = { GKP: 0, DEF: 1, MID: 2, FWD: 3 }

function LineupsCard({ match }: { match: MatchDetail }) {
  // Lineup-only sources (UEFA) know shirt numbers but have nothing to rank
  // players by; sources with a BPS / rating are PlayerStatsCard's.
  const lineup = (match.player_ratings ?? []).filter(
    (r) => r.rating == null && r.bps == null && r.number != null,
  )
  if (lineup.length === 0) return null
  const source = lineup[0]?.source ?? ''

  const byPosition = (a: PlayerRating, b: PlayerRating) =>
    (POSITION_ORDER[a.position ?? ''] ?? 9) - (POSITION_ORDER[b.position ?? ''] ?? 9) ||
    (a.number ?? 0) - (b.number ?? 0)
  const playedFirst = (a: PlayerRating, b: PlayerRating) =>
    Number((b.minutes ?? 0) > 0) - Number((a.minutes ?? 0) > 0) || (a.number ?? 0) - (b.number ?? 0)

  const column = (teamId: number, align?: 'right') => {
    const players = lineup.filter((r) => r.team_id === teamId)
    const starters = players.filter((r) => r.is_starter).sort(byPosition)
    const bench = players.filter((r) => !r.is_starter).sort(playedFirst)
    return (
      <div className="ratings__col">
        <div className="sub-head">Starting XI</div>
        {starters.map((r) => (
          <LineupRow key={r.player_name} r={r} match={match} align={align} />
        ))}
        {bench.length > 0 && <div className="sub-head">Substitutes</div>}
        {bench.map((r) => (
          <LineupRow key={r.player_name} r={r} match={match} align={align} />
        ))}
      </div>
    )
  }

  return (
    <div className="card">
      <div className="card__head">
        Lineups
        {viaLabel([source]) && <span className="faint"> · {viaLabel([source])}</span>}
      </div>
      <div className="ratings">
        {column(match.home_team.id)}
        {column(match.away_team.id, 'right')}
      </div>
    </div>
  )
}

function LineupRow({
  r,
  match,
  align,
}: {
  r: PlayerRating
  match: MatchDetail
  align?: 'right'
}) {
  const marks = [
    '⚽'.repeat(r.goals ?? 0),
    '🅰'.repeat(r.assists ?? 0),
    (r.red ?? 0) > 0 ? '🟥' : (r.yellow ?? 0) > 0 ? '🟨' : '',
  ].join('')
  const swap = (side: 'in' | 'out') =>
    match.substitutions.find(
      (s) =>
        s.team_id === r.team_id &&
        (side === 'in' ? s.player_in_name : s.player_out_name) === r.player_name,
    )
  const on = swap('in')
  const off = swap('out')
  const meta = [
    r.position,
    on && `⬆ ${on.minute}'`,
    off && `⬇ ${off.minute}'`,
    (r.saves ?? 0) > 0 && `${r.saves} saves`,
  ]
    .filter(Boolean)
    .join(' · ')
  const unused = !r.is_starter && (r.minutes ?? 0) === 0

  return (
    <div
      className={`rating-row${align === 'right' ? ' rating-row--right' : ''}${
        unused ? ' rating-row--dim' : ''
      }`}
    >
      <span className="rating-row__score" title="shirt number">
        {r.number}
      </span>
      <span className="rating-row__name">
        {r.player_name}
        {marks && <span className="rating-row__marks"> {marks}</span>}
      </span>
      <span className="rating-row__meta faint">{meta}</span>
    </div>
  )
}

function RatingRow({ r, align }: { r: PlayerRating; align?: 'right' }) {
  const marks = [
    '⚽'.repeat(r.goals ?? 0),
    '🅰'.repeat(r.assists ?? 0),
    (r.red ?? 0) > 0 ? '🟥' : (r.yellow ?? 0) > 0 ? '🟨' : '',
  ].join('')
  const score = r.rating ?? r.bps
  return (
    <div className={`rating-row${align === 'right' ? ' rating-row--right' : ''}`}>
      <span className="rating-row__score" title={r.rating != null ? 'rating' : 'BPS'}>
        {score ?? '–'}
      </span>
      <span className="rating-row__name">
        {r.player_name}
        {marks && <span className="rating-row__marks"> {marks}</span>}
      </span>
      <span className="rating-row__meta faint">
        {r.minutes != null ? `${r.minutes}'` : ''}
        {r.xg != null && ` · xG ${r.xg.toFixed(2)}`}
        {(r.bonus ?? 0) > 0 && ` · +${r.bonus}`}
      </span>
    </div>
  )
}

function HeadToHeadCard({ match }: { match: MatchDetail }) {
  const h2h = match.head_to_head
  if (!h2h || h2h.matches.length === 0) return null

  const total = h2h.home_wins + h2h.draws + h2h.away_wins || 1
  const pct = (n: number) => `${(n / total) * 100}%`
  const homeName = match.home_team.short_name || match.home_team.name
  const awayName = match.away_team.short_name || match.away_team.name

  return (
    <div className="card">
      <div className="card__head">Head to head</div>

      <div className="h2h-summary">
        <div className="h2h-summary__row">
          <span className="h2h-summary__side">{homeName}</span>
          <span className="h2h-summary__nums">
            <b>{h2h.home_wins}</b> <span className="faint">·</span> {h2h.draws}{' '}
            <span className="faint">·</span> <b>{h2h.away_wins}</b>
          </span>
          <span className="h2h-summary__side" style={{ textAlign: 'right' }}>
            {awayName}
          </span>
        </div>
        <div className="h2h-bar">
          <span className="h2h-bar__w" style={{ width: pct(h2h.home_wins) }} />
          <span className="h2h-bar__d" style={{ width: pct(h2h.draws) }} />
          <span className="h2h-bar__l" style={{ width: pct(h2h.away_wins) }} />
        </div>
      </div>

      <div>
        {h2h.matches.map((m) => (
          <MatchRow key={m.id} match={m} />
        ))}
      </div>
    </div>
  )
}

function MatchInfoCard({ match }: { match: MatchDetail }) {
  const refs = match.referees.filter((r) => r.name)
  if (!match.venue && !match.matchday && refs.length === 0) return null
  return (
    <div className="card">
      <div className="card__head">Match info</div>
      <ul className="info-list">
        {match.venue && (
          <li>
            <span className="faint">Venue</span>
            <span>{match.venue}</span>
          </li>
        )}
        {match.matchday && (
          <li>
            <span className="faint">Matchday</span>
            <span>{match.matchday}</span>
          </li>
        )}
        {refs.length > 0 && (
          <li>
            <span className="faint">Referee{refs.length > 1 ? 's' : ''}</span>
            <span>
              {refs
                .map((r) => `${r.name}${r.type && r.type !== 'REFEREE' ? ` (${r.type.toLowerCase()})` : ''}`)
                .join(', ')}
            </span>
          </li>
        )}
      </ul>
    </div>
  )
}

function EventsCard({ match }: { match: MatchDetail }) {
  type Ev = {
    minute: number | null
    injury?: number | null
    side: 'home' | 'away' | null
    icon: string
    text: string
  }
  const side = (teamId: number | null): 'home' | 'away' | null =>
    teamId === match.home_team.id ? 'home' : teamId === match.away_team.id ? 'away' : null

  const events = ([
    ...match.goals.map((g) => ({
      minute: g.minute,
      injury: g.injury_time,
      side: side(g.team_id),
      icon: g.type === 'PENALTY' ? '⚽(P)' : g.type === 'OWN' ? '⚽(OG)' : '⚽',
      text: [g.scorer_name, g.assist_name && `(assist: ${g.assist_name})`].filter(Boolean).join(' '),
    })),
    ...match.bookings.map((b) => ({
      minute: b.minute,
      side: side(b.team_id),
      icon: b.card === 'RED' ? '🟥' : b.card === 'YELLOW_RED' ? '🟨🟥' : '🟨',
      text: b.player_name ?? '',
    })),
    ...match.substitutions.map((s) => ({
      minute: s.minute,
      side: side(s.team_id),
      icon: '🔁',
      text: `${s.player_in_name ?? '?'} ⬆ / ${s.player_out_name ?? '?'} ⬇`,
    })),
  ] as Ev[]).sort(
    (a, b) => (a.minute ?? 999) - (b.minute ?? 999) || (a.injury ?? 0) - (b.injury ?? 0),
  )

  // Free football-data.org tier has no event timeline — just skip the card.
  if (events.length === 0) return null

  return (
    <div className="card">
      <div className="card__head">Match events</div>
      <ul className="timeline">
        {events.map((e, i) => (
          <li key={i}>
            <span className="min">
              {e.minute != null ? `${e.minute}${e.injury ? `+${e.injury}` : ''}'` : ''}
            </span>
            <span>{e.icon}</span>
            <span style={{ textAlign: e.side === 'away' ? 'right' : 'left' }}>{e.text}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
