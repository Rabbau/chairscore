import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { useSearch } from '../api/client'
import { Crest } from './Crest'

export function SearchBox() {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const [debounced, setDebounced] = useState('')
  const boxRef = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q), 220)
    return () => clearTimeout(t)
  }, [q])

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [])

  const { data, isFetching } = useSearch(debounced)
  const results = data ?? { teams: [], competitions: [] }
  const hasResults = results.teams.length > 0 || results.competitions.length > 0

  function go(to: string) {
    setOpen(false)
    setQ('')
    navigate(to)
  }

  return (
    <div className="search" ref={boxRef}>
      <input
        className="search__input"
        type="search"
        placeholder="Search teams, competitions…"
        value={q}
        onChange={(e) => {
          setQ(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
      />
      {open && debounced.trim().length >= 2 && (
        <div className="search__panel">
          {!hasResults && (
            <div className="search__empty">{isFetching ? 'Searching…' : 'No matches'}</div>
          )}
          {results.competitions.map((c) => (
            <button key={`c${c.code}`} className="search__row" onClick={() => go(`/competitions/${c.code}`)}>
              <Crest src={c.emblem_url} alt={c.name} />
              <span>{c.name}</span>
              <span className="chip">competition</span>
            </button>
          ))}
          {results.teams.map((t) => (
            <button key={`t${t.id}`} className="search__row" onClick={() => go(`/teams/${t.id}`)}>
              <Crest src={t.crest_url} alt={t.name} />
              <span>{t.name}</span>
              {t.tla && <span className="chip">{t.tla}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
