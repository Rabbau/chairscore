import { Link } from 'react-router-dom'

import type { StandingRow } from '../api/types'
import type { FormResult } from '../lib/format'
import { Crest } from './Crest'
import { FormBadges } from './FormBadges'

function parseForm(form: string | null): FormResult[] {
  if (!form) return []
  return form
    .split(',')
    .map((s) => s.trim().toUpperCase())
    .filter((s): s is FormResult => s === 'W' || s === 'D' || s === 'L')
}

/** Top 8 go straight to the round of 16, 9th-24th to the knockout play-offs.
 * Counted by row, not by the printed rank: tied teams share a rank number. */
function zoneOf(place: number): string {
  return place <= 8 ? 'zone-top' : place <= 24 ? 'zone-playoff' : ''
}

export function StandingsTable({
  rows,
  showForm = true,
  zones = false,
}: {
  rows: StandingRow[]
  showForm?: boolean
  /** Colour the league-phase qualification zones (36-team UEFA format). */
  zones?: boolean
}) {
  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="table">
        <thead>
          <tr>
            <th className="num">#</th>
            <th style={{ textAlign: 'left' }}>Team</th>
            <th>P</th>
            <th>W</th>
            <th>D</th>
            <th>L</th>
            <th>GF</th>
            <th>GA</th>
            <th>GD</th>
            <th className="pts">Pts</th>
            {showForm && <th>Form</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.team.id} className={zones ? zoneOf(i + 1) : undefined}>
              <td className="num">{r.position}</td>
              <td>
                <Link to={`/teams/${r.team.id}`} className="team-cell">
                  <Crest src={r.team.crest_url} alt={r.team.name} />
                  <span>{r.team.short_name || r.team.name}</span>
                </Link>
              </td>
              <td>{r.played}</td>
              <td>{r.won}</td>
              <td>{r.draw}</td>
              <td>{r.lost}</td>
              <td>{r.goals_for}</td>
              <td>{r.goals_against}</td>
              <td>{r.goal_difference > 0 ? `+${r.goal_difference}` : r.goal_difference}</td>
              <td className="pts">{r.points}</td>
              {showForm && (
                <td>
                  <FormBadges results={parseForm(r.form)} />
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {zones && (
        <div className="zone-legend faint">
          <span>
            <span className="zone-dot zone-dot--top" />
            Round of 16
          </span>
          <span>
            <span className="zone-dot zone-dot--playoff" />
            Knockout play-off
          </span>
        </div>
      )}
    </div>
  )
}
