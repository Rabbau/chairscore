import { useMemo, useState } from 'react'

import { useMatchesOn } from '../api/client'
import { GroupedMatches } from '../components/MatchList'
import { EmptyState, ErrorState, Loading } from '../components/States'
import { dayLabel, toISODate } from '../lib/format'

export function HomePage() {
  const [offset, setOffset] = useState(0)

  const date = useMemo(() => {
    const d = new Date()
    d.setDate(d.getDate() + offset)
    return d
  }, [offset])

  const { data: matches, isLoading, error, isFetching } = useMatchesOn(toISODate(date))

  return (
    <>
      <div className="date-nav">
        <button onClick={() => setOffset((o) => o - 1)} aria-label="Previous day">
          ‹
        </button>
        <span className="date-nav__label">{dayLabel(date)}</span>
        <button onClick={() => setOffset((o) => o + 1)} aria-label="Next day">
          ›
        </button>
        {offset !== 0 && (
          <button onClick={() => setOffset(0)} style={{ marginLeft: 4 }}>
            Today
          </button>
        )}
        {isFetching && <span className="spinner" style={{ width: 14, height: 14, margin: 0 }} />}
      </div>

      {isLoading ? (
        <Loading label="Loading matches…" />
      ) : error ? (
        <ErrorState error={error} />
      ) : !matches || matches.length === 0 ? (
        <EmptyState>
          <p>No matches for {dayLabel(date).toLowerCase()}.</p>
          <p className="faint" style={{ fontSize: 12 }}>
            Data is pulled from tracked competitions. Run a sync on the backend to populate it.
          </p>
        </EmptyState>
      ) : (
        <GroupedMatches matches={matches} />
      )}
    </>
  )
}
