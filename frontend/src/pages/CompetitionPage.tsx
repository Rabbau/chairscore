import { useState } from 'react'
import { useParams } from 'react-router-dom'

import type { Match } from '../api/types'

import {
  useCompetition,
  useCompetitionMatches,
  useScorers,
  useSeasons,
  useStandings,
} from '../api/client'
import { Crest } from '../components/Crest'
import { FavStar } from '../components/FavStar'
import { GroupedMatches } from '../components/MatchList'
import { MatchRow } from '../components/MatchRow'
import { StandingsTable } from '../components/StandingsTable'
import { EmptyState, ErrorState, Loading } from '../components/States'
import { roundLabel } from '../lib/format'

type Tab = 'standings' | 'matches' | 'scorers'

function seasonLabel(s: string): string {
  const y = Number(s)
  return Number.isFinite(y) ? `${y}/${String((y + 1) % 100).padStart(2, '0')}` : s
}

export function CompetitionPage() {
  const { code = '' } = useParams()
  const [tab, setTab] = useState<Tab>('standings')
  // remember the picked season together with the competition it belongs to,
  // so switching competitions naturally falls back to that one's latest season
  const [picked, setPicked] = useState<{ code: string; season: string } | null>(null)
  const { data: competition } = useCompetition(code)
  const { data: seasons } = useSeasons(code)

  const activeSeason = (picked?.code === code ? picked.season : undefined) ?? seasons?.[0]

  return (
    <>
      <div className="page-title">
        <Crest src={competition?.emblem_url} alt={competition?.name ?? code} size="lg" />
        <div style={{ flex: 1 }}>
          <h1>{competition?.name ?? code}</h1>
          <span className="faint" style={{ fontSize: 12 }}>
            {competition?.area_name}
            {competition?.current_matchday ? ` · Matchday ${competition.current_matchday}` : ''}
          </span>
        </div>
        {competition && (
          <FavStar
            competition={{
              code: competition.code,
              name: competition.name,
              emblem_url: competition.emblem_url,
            }}
          />
        )}
        {seasons && seasons.length > 1 && (
          <select
            className="season-select"
            value={activeSeason ?? ''}
            onChange={(e) => setPicked({ code, season: e.target.value })}
          >
            {seasons.map((s) => (
              <option key={s} value={s}>
                {seasonLabel(s)}
              </option>
            ))}
          </select>
        )}
      </div>

      <div className="tabs">
        {(['standings', 'matches', 'scorers'] as Tab[]).map((t) => (
          <button
            key={t}
            className={`tab${tab === t ? ' tab--active' : ''}`}
            onClick={() => setTab(t)}
          >
            {t === 'scorers' ? 'Top scorers' : t[0].toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      <div style={{ marginTop: 16 }}>
        {tab === 'standings' && <StandingsTab code={code} season={activeSeason} />}
        {tab === 'matches' && <MatchesTab code={code} season={activeSeason} />}
        {tab === 'scorers' && <ScorersTab code={code} season={activeSeason} />}
      </div>
    </>
  )
}

function StandingsTab({ code, season }: { code: string; season?: string }) {
  const { data, isLoading, error } = useStandings(code, season)
  if (isLoading) return <Loading />
  if (error) return <ErrorState error={error} />
  const groups = data?.groups ?? []
  if (groups.length === 0)
    return (
      <EmptyState>
        <p>No standings for this season.</p>
      </EmptyState>
    )

  const realGroup = (name: string | null) => name && name.toUpperCase() !== 'MATCHDAY'

  return (
    <>
      {groups.map((g, i) => (
        <div className="card" key={i}>
          {realGroup(g.group_name) && <div className="card__head">{g.group_name}</div>}
          <StandingsTable
            rows={g.rows}
            zones={g.stage === 'LEAGUE_STAGE' && g.rows.length === 36}
          />
        </div>
      ))}
    </>
  )
}

function MatchesTab({ code, season }: { code: string; season?: string }) {
  const { data, isLoading, error } = useCompetitionMatches(code, { season })
  if (isLoading) return <Loading />
  if (error) return <ErrorState error={error} />
  if (!data || data.length === 0)
    return (
      <EmptyState>
        <p>No matches for this season.</p>
      </EmptyState>
    )

  const upcoming = data.filter((m) => !['FINISHED', 'AWARDED'].includes(m.status))
  const finished = data.filter((m) => ['FINISHED', 'AWARDED'].includes(m.status)).reverse()

  // Cups have rounds — section the fixture lists by them. Leagues keep the
  // single per-competition card.
  if (!data.some((m) => roundLabel(m)))
    return <GroupedMatches matches={[...upcoming, ...finished]} />
  return (
    <>
      {upcoming.length > 0 && <RoundCard title="Upcoming" matches={upcoming} />}
      {finished.length > 0 && <RoundCard title="Results" matches={finished} />}
    </>
  )
}

function RoundCard({ title, matches }: { title: string; matches: Match[] }) {
  const rows: React.ReactNode[] = []
  let last: string | null = null
  for (const m of matches) {
    const label = roundLabel(m)
    if (label && label !== last) {
      rows.push(
        <div className="sub-head" key={`round-${m.id}`}>
          {label}
        </div>,
      )
      last = label
    }
    rows.push(<MatchRow key={m.id} match={m} />)
  }
  return (
    <div className="card">
      <div className="card__head">{title}</div>
      <div>{rows}</div>
    </div>
  )
}

function ScorersTab({ code, season }: { code: string; season?: string }) {
  const { data, isLoading, error } = useScorers(code, season)
  if (isLoading) return <Loading />
  if (error) return <ErrorState error={error} />
  const scorers = data?.scorers ?? []
  if (scorers.length === 0)
    return (
      <EmptyState>
        <p>No scorer data for this season.</p>
      </EmptyState>
    )

  return (
    <div className="card" style={{ overflowX: 'auto' }}>
      <table className="table">
        <thead>
          <tr>
            <th className="num">#</th>
            <th style={{ textAlign: 'left' }}>Player</th>
            <th style={{ textAlign: 'left' }}>Team</th>
            <th>MP</th>
            <th>Goals</th>
            <th>Assists</th>
          </tr>
        </thead>
        <tbody>
          {scorers.map((s) => (
            <tr key={s.rank}>
              <td className="num">{s.rank}</td>
              <td style={{ textAlign: 'left' }}>{s.player_name}</td>
              <td style={{ textAlign: 'left' }} className="muted">
                {s.team?.short_name || s.team?.name || '—'}
              </td>
              <td>{s.played_matches ?? '—'}</td>
              <td className="pts">{s.goals}</td>
              <td>{s.assists ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
