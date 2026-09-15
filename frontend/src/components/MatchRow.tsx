import { Link } from 'react-router-dom'

import type { Match } from '../api/types'
import { isFinished, isLive, kickoffTime } from '../lib/format'
import { Crest } from './Crest'

export function MatchRow({ match }: { match: Match }) {
  const live = isLive(match.status)
  const done = isFinished(match.status)
  const hasScore = match.home_score != null && match.away_score != null
  const homeWon = match.winner === 'HOME_TEAM'
  const awayWon = match.winner === 'AWAY_TEAM'

  let timeNode: React.ReactNode
  if (live) timeNode = <span className="live">LIVE</span>
  else if (done) timeNode = <span className="faint">FT</span>
  else if (match.status === 'POSTPONED') timeNode = <span className="faint">PP</span>
  else timeNode = kickoffTime(match.utc_date)

  return (
    <Link to={`/matches/${match.id}`} className="match-row">
      <div className="match-row__time">{timeNode}</div>

      <div className="match-row__teams">
        <div className={`match-row__team${homeWon ? ' match-row__team--won' : ''}`}>
          <Crest src={match.home_team.crest_url} alt={match.home_team.name} />
          <span>{match.home_team.short_name || match.home_team.name}</span>
        </div>
        <div className={`match-row__team${awayWon ? ' match-row__team--won' : ''}`}>
          <Crest src={match.away_team.crest_url} alt={match.away_team.name} />
          <span>{match.away_team.short_name || match.away_team.name}</span>
        </div>
      </div>

      <div className="match-row__score">
        {hasScore ? (
          <>
            <span className={awayWon ? 'dim' : ''}>{match.home_score}</span>
            <span className={homeWon ? 'dim' : ''}>{match.away_score}</span>
          </>
        ) : (
          <span className="faint">–</span>
        )}
      </div>
    </Link>
  )
}
