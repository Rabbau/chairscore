import type { Match } from '../api/types'

/** Backend sends naive-UTC ISO strings; make sure JS parses them as UTC. */
export function parseUtc(iso: string): Date {
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`)
}

export function kickoffTime(iso: string): string {
  return parseUtc(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export function dayLabel(d: Date): string {
  const today = new Date()
  const t0 = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  const d0 = new Date(d.getFullYear(), d.getMonth(), d.getDate())
  const diff = Math.round((d0.getTime() - t0.getTime()) / 86_400_000)
  if (diff === 0) return 'Today'
  if (diff === -1) return 'Yesterday'
  if (diff === 1) return 'Tomorrow'
  return d.toLocaleDateString([], { weekday: 'short', day: 'numeric', month: 'short' })
}

export function toISODate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(
    d.getDate(),
  ).padStart(2, '0')}`
}

export function isLive(status: string): boolean {
  return status === 'IN_PLAY' || status === 'PAUSED'
}

export function isFinished(status: string): boolean {
  return status === 'FINISHED' || status === 'AWARDED'
}

export function scoreText(m: Pick<Match, 'status' | 'home_score' | 'away_score'>): string | null {
  if (m.home_score == null || m.away_score == null) return null
  return `${m.home_score}–${m.away_score}`
}

export type FormResult = 'W' | 'D' | 'L'

/** W/D/L for `teamId` in a finished match, or null if it can't be determined. */
export function resultFor(m: Match, teamId: number): FormResult | null {
  if (m.home_score == null || m.away_score == null) return null
  const isHome = m.home_team.id === teamId
  const gf = isHome ? m.home_score : m.away_score
  const ga = isHome ? m.away_score : m.home_score
  return gf > ga ? 'W' : gf < ga ? 'L' : 'D'
}

const STAGE_LABELS: Record<string, string> = {
  LEAGUE_STAGE: 'League phase',
  GROUP_STAGE: 'Group stage',
  PLAYOFFS: 'Knockout play-off',
  LAST_16: 'Round of 16',
  QUARTER_FINALS: 'Quarter-finals',
  SEMI_FINALS: 'Semi-finals',
  FINAL: 'Final',
}

/** Human label for a cup stage; null for a plain league season. */
export function stageLabel(stage: string | null | undefined): string | null {
  return stage ? (STAGE_LABELS[stage] ?? null) : null
}

/** "League phase · Matchday 3", "Round of 16" ... — what a fixture list is sectioned by. */
export function roundLabel(m: Pick<Match, 'stage' | 'matchday'>): string | null {
  const stage = stageLabel(m.stage)
  if (!stage) return null
  return (m.stage === 'LEAGUE_STAGE' || m.stage === 'GROUP_STAGE') && m.matchday
    ? `${stage} · Matchday ${m.matchday}`
    : stage
}
