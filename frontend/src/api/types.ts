// Mirrors backend/app/schemas. Keep in sync.

export type MatchStatus =
  | 'SCHEDULED'
  | 'TIMED'
  | 'IN_PLAY'
  | 'PAUSED'
  | 'FINISHED'
  | 'SUSPENDED'
  | 'POSTPONED'
  | 'CANCELLED'
  | 'AWARDED'

export interface Competition {
  id: number
  code: string
  name: string
  emblem_url: string | null
  type?: string | null
  area_name?: string | null
  area_flag?: string | null
  current_season?: string | null
  current_season_start?: string | null
  current_season_end?: string | null
  current_matchday?: number | null
  last_synced_at?: string | null
}

export interface Team {
  id: number
  provider_id: number
  name: string
  short_name: string | null
  tla: string | null
  crest_url: string | null
}

export interface Match {
  id: number
  provider_id: number
  season: string
  matchday: number | null
  stage: string | null
  group: string | null
  utc_date: string
  status: MatchStatus
  home_score: number | null
  away_score: number | null
  home_score_ht: number | null
  away_score_ht: number | null
  /** Penalty shoot-out score (cup ties); the scores above exclude it. */
  home_score_pen?: number | null
  away_score_pen?: number | null
  winner: 'HOME_TEAM' | 'AWAY_TEAM' | 'DRAW' | null
  competition: Competition
  home_team: Team
  away_team: Team
}

export interface Goal {
  minute: number | null
  injury_time: number | null
  type: string | null
  team_id: number | null
  scorer_name: string | null
  assist_name: string | null
  home_score: number | null
  away_score: number | null
}

export interface Booking {
  minute: number | null
  team_id: number | null
  player_name: string | null
  card: 'YELLOW' | 'RED' | 'YELLOW_RED' | null
}

export interface Substitution {
  minute: number | null
  team_id: number | null
  player_in_name: string | null
  player_out_name: string | null
}

export interface Referee {
  name: string | null
  type: string | null
  nationality: string | null
}

export interface HeadToHead {
  home_wins: number
  draws: number
  away_wins: number
  matches: Match[]
}

export interface TeamStat {
  team_id: number | null
  source: string
  possession: number | null
  shots: number | null
  shots_on_target: number | null
  corners: number | null
  fouls: number | null
  offsides: number | null
  yellow_cards: number | null
  red_cards: number | null
  passes: number | null
  passes_accuracy: number | null
  saves: number | null
  xg: number | null
}

/** One team's stats with every source folded together (server-side merge). */
export interface MergedTeamStat extends Omit<TeamStat, 'source'> {
  sources: string[]
  /** stat name -> the source its value came from */
  field_sources: Record<string, string>
}

export interface PlayerRating {
  team_id: number | null
  source: string
  player_name: string
  rating: number | null
  minutes: number | null
  position: string | null
  number: number | null
  is_starter: boolean
  captain: boolean
  goals: number | null
  assists: number | null
  yellow: number | null
  red: number | null
  xg: number | null
  xa: number | null
  bps: number | null
  bonus: number | null
  saves: number | null
}

export interface MatchDetail extends Match {
  venue: string | null
  duration: string | null
  referees: Referee[]
  goals: Goal[]
  bookings: Booking[]
  substitutions: Substitution[]
  team_stats: TeamStat[]
  /** Absent in a snapshot exported before the server-side merge existed. */
  merged_team_stats?: MergedTeamStat[]
  player_ratings: PlayerRating[]
  head_to_head: HeadToHead | null
  home_form: Match[]
  away_form: Match[]
}

export interface StandingRow {
  position: number
  played: number
  won: number
  draw: number
  lost: number
  points: number
  goals_for: number
  goals_against: number
  goal_difference: number
  form: string | null
  team: Team
}

export interface StandingsGroup {
  type: string
  group_name: string | null
  stage: string | null
  rows: StandingRow[]
}

export interface Standings {
  competition: Competition
  season: string | null
  groups: StandingsGroup[]
}

export interface Scorer {
  rank: number
  player_name: string
  position: string | null
  nationality: string | null
  played_matches: number | null
  goals: number
  assists: number | null
  penalties: number | null
  team: Team | null
}

export interface ScorersResponse {
  competition: Competition
  season: string | null
  scorers: Scorer[]
}

export interface Player {
  id: number
  name: string
  position: string | null
  date_of_birth: string | null
  nationality: string | null
  shirt_number: number | null
}

export interface SearchResults {
  teams: Team[]
  competitions: Competition[]
}

export interface TeamDetail extends Team {
  founded: number | null
  club_colors: string | null
  venue: string | null
  website: string | null
  coach_name: string | null
  area_name: string | null
  squad: Player[]
  competitions: Competition[]
  recent_matches: Match[]
  upcoming_matches: Match[]
}
