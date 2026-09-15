import { useSyncExternalStore } from 'react'

export interface FavTeam {
  id: number
  name: string
  crest_url: string | null
}
export interface FavCompetition {
  code: string
  name: string
  emblem_url: string | null
}
interface Favourites {
  teams: FavTeam[]
  competitions: FavCompetition[]
}

const KEY = 'chairscore.favourites'
const EMPTY: Favourites = { teams: [], competitions: [] }

const listeners = new Set<() => void>()
let cache: Favourites = read()

function read(): Favourites {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return EMPTY
    const parsed = JSON.parse(raw)
    return {
      teams: Array.isArray(parsed.teams) ? parsed.teams : [],
      competitions: Array.isArray(parsed.competitions) ? parsed.competitions : [],
    }
  } catch {
    return EMPTY
  }
}

function write(next: Favourites) {
  cache = next
  try {
    localStorage.setItem(KEY, JSON.stringify(next))
  } catch {
    /* private mode / quota — keep the in-memory copy */
  }
  listeners.forEach((l) => l())
}

if (typeof window !== 'undefined') {
  window.addEventListener('storage', (e) => {
    if (e.key === KEY) {
      cache = read()
      listeners.forEach((l) => l())
    }
  })
}

export function toggleFavTeam(team: FavTeam) {
  const has = cache.teams.some((t) => t.id === team.id)
  write({
    ...cache,
    teams: has ? cache.teams.filter((t) => t.id !== team.id) : [...cache.teams, team],
  })
}

export function toggleFavCompetition(comp: FavCompetition) {
  const has = cache.competitions.some((c) => c.code === comp.code)
  write({
    ...cache,
    competitions: has
      ? cache.competitions.filter((c) => c.code !== comp.code)
      : [...cache.competitions, comp],
  })
}

export function useFavourites(): Favourites {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l)
      return () => listeners.delete(l)
    },
    () => cache,
    () => EMPTY,
  )
}
