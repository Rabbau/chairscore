import type { FormResult } from '../lib/format'

/** Row of small W/D/L squares, oldest → newest (pass results already in that order). */
export function FormBadges({ results, max = 5 }: { results: FormResult[]; max?: number }) {
  const items = results.slice(-max)
  if (items.length === 0) return <span className="faint">—</span>
  return (
    <span className="form-badges">
      {items.map((r, i) => (
        <span key={i} className={`form-badge form-badge--${r}`} title={r}>
          {r}
        </span>
      ))}
    </span>
  )
}
