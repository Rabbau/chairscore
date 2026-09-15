import { useQuery } from '@tanstack/react-query'

import { liveApi } from './liveClient'
import { staticApi } from './staticClient'

// GitHub Pages build (npm run build:static) sets VITE_STATIC=true and reads
// the JSON snapshot instead of hitting a live backend. Same shape either way
// — see liveClient.ts / staticClient.ts — so nothing below this line cares.
export const api = import.meta.env.VITE_STATIC === 'true' ? staticApi : liveApi
export const isStatic = import.meta.env.VITE_STATIC === 'true'

// ---- hooks ---------------------------------------------------------------
const MIN = 60_000
// A static snapshot never changes underneath the page, so cache it for good.
const staleTime = (liveMs: number) => (isStatic ? Infinity : liveMs)

export const useCompetitions = () =>
  useQuery({ queryKey: ['competitions'], queryFn: api.competitions, staleTime: staleTime(30 * MIN) })

export const useCompetition = (code: string) =>
  useQuery({
    queryKey: ['competition', code],
    queryFn: () => api.competition(code),
    staleTime: staleTime(30 * MIN),
  })

export const useStandings = (code: string, season?: string) =>
  useQuery({
    queryKey: ['standings', code, season ?? 'latest'],
    queryFn: () => api.standings(code, season),
    staleTime: staleTime(10 * MIN),
  })

export const useCompetitionMatches = (
  code: string,
  params?: { matchday?: number; status?: string; season?: string },
) =>
  useQuery({
    queryKey: ['competition-matches', code, params],
    queryFn: () => api.competitionMatches(code, params),
    staleTime: staleTime(2 * MIN),
  })

export const useSeasons = (code: string) =>
  useQuery({ queryKey: ['seasons', code], queryFn: () => api.seasons(code), staleTime: staleTime(60 * MIN) })

export const useScorers = (code: string, season?: string, limit = 20) =>
  useQuery({
    queryKey: ['scorers', code, season ?? 'latest', limit],
    queryFn: () => api.scorers(code, season, limit),
    staleTime: staleTime(15 * MIN),
  })

export const useSearch = (q: string) =>
  useQuery({
    queryKey: ['search', q],
    queryFn: () => api.search(q),
    enabled: q.trim().length >= 2,
    staleTime: staleTime(5 * MIN),
    placeholderData: (prev) => prev,
  })

export const useMatchesOn = (date?: string) =>
  useQuery({
    queryKey: ['matches', date ?? 'today'],
    queryFn: () => api.matchesOn(date),
    staleTime: staleTime(MIN),
    refetchInterval: isStatic ? false : 60_000,
  })

export const useMatch = (id: number | string) =>
  useQuery({ queryKey: ['match', id], queryFn: () => api.match(id), staleTime: staleTime(MIN) })

export const useTeam = (id: number | string) =>
  useQuery({ queryKey: ['team', id], queryFn: () => api.team(id), staleTime: staleTime(15 * MIN) })
