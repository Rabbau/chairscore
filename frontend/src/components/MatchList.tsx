import { Link } from 'react-router-dom'

import type { Match } from '../api/types'
import { Crest } from './Crest'
import { MatchRow } from './MatchRow'

/** Groups a flat match list into one card per competition. */
export function GroupedMatches({ matches }: { matches: Match[] }) {
  const groups = new Map<string, { competition: Match['competition']; matches: Match[] }>()
  for (const m of matches) {
    const g = groups.get(m.competition.code)
    if (g) g.matches.push(m)
    else groups.set(m.competition.code, { competition: m.competition, matches: [m] })
  }

  return (
    <>
      {[...groups.values()].map(({ competition, matches }) => (
        <div className="card" key={competition.code}>
          <Link to={`/competitions/${competition.code}`} className="card__head">
            <Crest src={competition.emblem_url} alt={competition.name} />
            {competition.name}
            {competition.area_name && <span className="chip">{competition.area_name}</span>}
          </Link>
          <div>
            {matches.map((m) => (
              <MatchRow key={m.id} match={m} />
            ))}
          </div>
        </div>
      ))}
    </>
  )
}

export function MatchListCard({ title, matches }: { title: string; matches: Match[] }) {
  return (
    <div className="card">
      <div className="card__head">{title}</div>
      <div>
        {matches.map((m) => (
          <MatchRow key={m.id} match={m} />
        ))}
      </div>
    </div>
  )
}
