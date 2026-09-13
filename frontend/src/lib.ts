import { format, isToday, isTomorrow } from 'date-fns'
import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'
import type { Match } from './types'

export const cn = (...values: ClassValue[]) => twMerge(clsx(values))
export const teamName = (id: number | null) =>
  id === 1 ? 'Old Gentlemen' : id === 2 ? 'Young Boys' : 'Unassigned'
export const teamTone = (id: number | null) => (id === 1 ? 'green' : id === 2 ? 'gold' : 'gray')
export const matchesTeam = (id: number | null, filter: string) =>
  filter === 'all' || (filter === 'unassigned' ? id === null : id === Number(filter))
export const sideName = (m: Match, side: 'home' | 'away') =>
  m.kind === 'mixed' ? (side === 'home' ? 'Green side' : 'Gold side') : teamName(side === 'home' ? 1 : 2)
export const initials = (name: string) =>
  name
    .split(' ')
    .map((n) => n[0])
    .slice(0, 2)
    .join('')
export const matchDate = (date: string) => format(new Date(date), 'EEE, MMM d')
export const matchTime = (date: string) => format(new Date(date), 'h:mm a')
export const relativeDay = (date: string) =>
  isToday(new Date(date)) ? 'Today' : isTomorrow(new Date(date)) ? 'Tomorrow' : format(new Date(date), 'EEEE')
export const nextMatches = (matches: Match[]) =>
  matches
    .filter((m) => m.status === 'scheduled' || m.status === 'live')
    .sort((a, b) => a.starts_at.localeCompare(b.starts_at))
export const completedMatches = (matches: Match[]) =>
  matches.filter((m) => m.status === 'completed').sort((a, b) => b.starts_at.localeCompare(a.starts_at))
export async function copyText(text: string) {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text)
      return
    } catch {
      // Some embedded browsers expose Clipboard but deny it. Try the user-initiated fallback.
    }
  }
  const previouslyFocused = document.activeElement as HTMLElement | null
  const field = document.createElement('textarea')
  field.value = text
  field.style.position = 'fixed'
  field.style.opacity = '0'
  // Keep focus inside an open dialog's focus trap while copying.
  ;(document.querySelector('[role="dialog"]') || document.body).append(field)
  field.select()
  const success = document.execCommand('copy')
  field.remove()
  previouslyFocused?.focus()
  if (!success) throw new Error('Copy is unavailable. Select the summary and copy it manually.')
}
