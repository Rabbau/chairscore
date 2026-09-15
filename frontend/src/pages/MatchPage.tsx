import { Link, useParams } from 'react-router-dom'

import type { Match, MatchDetail, PlayerRating, TeamStat } from '../api/types'
import { useMatch } from '../api/client'
import { Crest } from '../components/Crest'
import { FormBadges } from '../components/FormBadges'
import { MatchRow } from '../components/MatchRow'
import { ErrorState, Loading } from '../components/States'
import { isLive, kickoffTime, parseUtc, resultFor, type FormResult } from '../lib/format'

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
    [s.xg, s.possession, s.shots, s.shots_on_target, s.corners, s.fouls, s.yellow_cards, s.red_cards, s.saves]
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
  const statusText = isLive(match.status)
    ? 'LIVE'
    : done
      ? 'Full time'
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
            {match.home_score_ht != null && (
              <div className="faint" style={{ fontSize: 12, marginTop: 6 }}>
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
      <PlayerStatsCard match={match} />
      <HeadToHeadCard match={match} />
      <MatchInfoCard match={match} />
    </>
  )
}

const SOURCE_LABEL: Record<string, string> = {
  fpl: 'via Fantasy Premier League',
  'api-football': 'via API-Football',
  'football-data.co.uk': 'via Football-Data.co.uk',
}

interface StatRowDef {
  label: string
  home: number | null
  away: number | null
  decimals?: number
}

function MatchStatsCard({ match }: { match: MatchDetail }) {
  const stats = match.team_stats ?? []
  const home = richestStat(stats, match.home_team.id)
  const away = richestStat(stats, match.away_team.id)
  if (!home && !away) return null

  const rows: StatRowDef[] = [
    { label: 'xG', home: home?.xg ?? null, away: away?.xg ?? null, decimals: 2 },
    { label: 'Possession', home: home?.possession ?? null, away: away?.possession ?? null },
    { label: 'Shots', home: home?.shots ?? null, away: away?.shots ?? null },
    {
      label: 'Shots on target',
      home: home?.shots_on_target ?? null,
      away: away?.shots_on_target ?? null,
    },
    { label: 'Corners', home: home?.corners ?? null, away: away?.corners ?? null },
    { label: 'Fouls', home: home?.fouls ?? null, away: away?.fouls ?? null },
    { label: 'Yellow cards', home: home?.yellow_cards ?? null, away: away?.yellow_cards ?? null },
    { label: 'Red cards', home: home?.red_cards ?? null, away: away?.red_cards ?? null },
  ].filter((r) => r.home != null || r.away != null)
  if (rows.length === 0) return null

  const source = home?.source ?? away?.source ?? ''

  return (
    <div className="card">
      <div className="card__head">
        Match stats
        {SOURCE_LABEL[source] && <span className="faint"> · {SOURCE_LABEL[source]}</span>}
      </div>
      <div className="stat-rows">
        {rows.map((r) => (
          <StatRow key={r.label} {...r} />
        ))}
      </div>
    </div>
  )
}

function StatRow({ label, home, away, decimals }: StatRowDef) {
  const h = home ?? 0
  const a = away ?? 0
  const total = h + a || 1
  const fmt = (v: number | null) => (v == null ? '–' : decimals ? v.toFixed(decimals) : String(v))
  return (
    <div className="stat-row">
      <span className="stat-row__val">{fmt(home)}</span>
      <div className="stat-row__mid">
        <span className="stat-row__label">{label}</span>
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
  const ratings = match.player_ratings ?? []
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
        {SOURCE_LABEL[source] && <span className="faint"> · {SOURCE_LABEL[source]}</span>}
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
  type Ev = { minute: number | null; side: 'home' | 'away' | null; icon: string; text: string }
  const side = (teamId: number | null): 'home' | 'away' | null =>
    teamId === match.home_team.id ? 'home' : teamId === match.away_team.id ? 'away' : null

  const events: Ev[] = [
    ...match.goals.map((g) => ({
      minute: g.minute,
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
  ].sort((a, b) => (a.minute ?? 999) - (b.minute ?? 999))

  // Free football-data.org tier has no event timeline — just skip the card.
  if (events.length === 0) return null

  return (
    <div className="card">
      <div className="card__head">Match events</div>
      <ul className="timeline">
        {events.map((e, i) => (
          <li key={i}>
            <span className="min">{e.minute != null ? `${e.minute}'` : ''}</span>
            <span>{e.icon}</span>
            <span style={{ textAlign: e.side === 'away' ? 'right' : 'left' }}>{e.text}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
