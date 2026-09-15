// Talks to the live FastAPI backend (see backend/app/api/). Used unless
// VITE_STATIC=true, in which case client.ts wires up staticClient.ts instead.
import type {
  Competition,
  Match,
  MatchDetail,
  ScorersResponse,
  SearchResults,
  Standings,
  TeamDetail,
} from './types'

const BASE = import.meta.env.VITE_API_BASE ?? '/api'

async function get<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(params ?? {})) {
    if (v !== undefined && v !== '') qs.set(k, String(v))
  }
  const query = qs.toString()
  const res = await fetch(`${BASE}${path}${query ? `?${query}` : ''}`)
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(`${res.status} ${res.statusText}${detail ? ` — ${detail}` : ''}`)
  }
  return res.json() as Promise<T>
}

export const liveApi = {
  competitions: () => get<Competition[]>('/competitions'),
  competition: (code: string) => get<Competition>(`/competitions/${code}`),
  standings: (code: string, season?: string) =>
    get<Standings>(`/competitions/${code}/standings`, { season }),
  competitionMatches: (code: string, params?: { matchday?: number; status?: string; season?: string }) =>
    get<Match[]>(`/competitions/${code}/matches`, params),
  seasons: (code: string) => get<string[]>(`/competitions/${code}/seasons`),
  scorers: (code: string, season?: string, limit = 20) =>
    get<ScorersResponse>(`/competitions/${code}/scorers`, { season, limit }),
  matchesOn: (date?: string) => get<Match[]>('/matches', { date }),
  match: (id: number | string) => get<MatchDetail>(`/matches/${id}`),
  team: (id: number | string) => get<TeamDetail>(`/teams/${id}`),
  search: (q: string) => get<SearchResults>('/search', { q }),
}
