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

export function StandingsTable({ rows, showForm = true }: { rows: StandingRow[]; showForm?: boolean }) {
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
          {rows.map((r) => (
            <tr key={r.team.id}>
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
    </div>
  )
}
