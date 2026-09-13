export type Role = 'player' | 'captain' | 'admin'
export type RSVPStatus = 'going' | 'maybe' | 'out'
export type Side = 'home' | 'away'
export type MatchStatus = 'scheduled' | 'live' | 'completed' | 'cancelled'
export interface Player {
  id: number
  name: string
  nickname: string
  team_id: number | null
  positions: string | null
  dominant_foot: string | null
  age_group: string | null
  photo_url: string
  contact_preference: string
  preferred_times: string | null
  availability: 'available' | 'injured' | 'away' | null
  injury_note: string
  skill: number | null
  jersey: number | null
  is_captain: boolean
  active: boolean
  joined_at: string
}
export interface User {
  id: number
  email: string
  role: Role
  player: Player
}
export interface Match {
  id: number
  season_id: number
  title: string
  starts_at: string
  duration_minutes: number
  location: string
  address: string
  pitch: string
  notes: string
  kind: 'classic' | 'mixed'
  status: MatchStatus
  home_score: number
  away_score: number
  capacity: number
  formation: string
  going: number
  going_player_ids: number[]
  maybe: number
  out: number
  my_rsvp: RSVPStatus | null
}
export interface LineupSlot {
  player_id: number
  side: Side
  slot: number
}
export interface MatchEvent {
  id: number
  player_id: number
  assist_player_id: number | null
  kind: string
  side: Side
  minute: number
}
export interface MatchDetail extends Match {
  players: Player[]
  rsvps: { player_id: number; status: RSVPStatus }[]
  lineup: LineupSlot[]
  events: MatchEvent[]
  my_ratings: { player_id: number; value: number }[]
}
export interface PlayerStats {
  player_id: number
  name: string
  nickname: string
  team_id: number | null
  jersey: number | null
  positions: string | null
  photo_url: string
  games: number
  goals: number
  assists: number
  wins: number
  draws: number
  clean_sheets: number
  form: string[]
  rating: number | null
  win_rate: number
  attendance: number
  reliability: number | null
}
export interface TeamStats {
  id: number
  name: string
  short_name: string
  color: string
  motto: string
  games: number
  wins: number
  draws: number
  losses: number
  goals_for: number
  goals_against: number
  form: string[]
}
export interface Stats {
  players: PlayerStats[]
  teams: TeamStats[]
  matches_played: number
  total_goals: number
  trend: { month: string; matches: number; goals: number; attendance: number }[]
}
export interface ClubNote {
  id: number
  title: string
  body: string
  category: string
  updated_at: string
}
export interface PlayerDetail extends Player {
  stats: PlayerStats
  matches: Match[]
}
export interface Member extends Player {
  email: string | null
  role: Role
  has_account: boolean
}
export interface Season {
  id: number
  name: string
  active: boolean
}
