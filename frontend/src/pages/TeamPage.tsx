import { useParams } from 'react-router-dom'

import { useTeam } from '../api/client'
import { Crest } from '../components/Crest'
import { FavStar } from '../components/FavStar'
import { MatchListCard } from '../components/MatchList'
import { ErrorState, Loading } from '../components/States'

export function TeamPage() {
  const { id = '' } = useParams()
  const { data: team, isLoading, error } = useTeam(id)

  if (isLoading) return <Loading />
  if (error) return <ErrorState error={error} />
  if (!team) return null

  return (
    <>
      <div className="page-title">
        <Crest src={team.crest_url} alt={team.name} size="xl" />
        <div style={{ flex: 1 }}>
          <h1>{team.name}</h1>
          <span className="faint" style={{ fontSize: 12 }}>
            {[team.venue, team.founded && `founded ${team.founded}`, team.coach_name]
              .filter(Boolean)
              .join(' · ')}
          </span>
        </div>
        <FavStar team={{ id: team.id, name: team.name, crest_url: team.crest_url }} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 16 }}>
        {team.upcoming_matches.length > 0 && (
          <MatchListCard title="Upcoming" matches={team.upcoming_matches} />
        )}
        {team.recent_matches.length > 0 && (
          <MatchListCard title="Recent results" matches={team.recent_matches} />
        )}

        <div className="card" style={{ overflowX: 'auto' }}>
          <div className="card__head">Squad ({team.squad.length})</div>
          {team.squad.length === 0 ? (
            <div className="state faint" style={{ fontSize: 13 }}>
              No squad data — run a reference sync on the backend.
            </div>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th className="num">#</th>
                  <th style={{ textAlign: 'left' }}>Name</th>
                  <th style={{ textAlign: 'left' }}>Position</th>
                  <th style={{ textAlign: 'left' }}>Nationality</th>
                </tr>
              </thead>
              <tbody>
                {team.squad.map((p) => (
                  <tr key={p.id}>
                    <td className="num">{p.shirt_number ?? ''}</td>
                    <td style={{ textAlign: 'left' }}>{p.name}</td>
                    <td style={{ textAlign: 'left' }} className="muted">
                      {p.position ?? '—'}
                    </td>
                    <td style={{ textAlign: 'left' }} className="muted">
                      {p.nationality ?? '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </>
  )
}
