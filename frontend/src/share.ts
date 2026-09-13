import { format } from 'date-fns'
import { sideName } from './lib'
import type { Match } from './types'

export function matchSummary(match: Match) {
  const link = `${window.location.origin}/matches/${match.id}`
  const when = format(new Date(match.starts_at), 'EEEE, MMMM d · h:mm a')
  const score =
    match.status === 'completed'
      ? `🏁 Full time: ${sideName(match, 'home')} ${match.home_score} – ${match.away_score} ${sideName(match, 'away')}`
      : `${sideName(match, 'home')} vs ${sideName(match, 'away')}`
  return `⚽ LEX PICKUP PRO\n${match.title}\n\n${score}\n📅 ${when}\n📍 ${match.location} · ${match.pitch}\n\n${match.status === 'completed' ? 'Good football. Great company. See you at the next one!' : `${match.going}/${match.capacity} confirmed · ${match.maybe} maybe\nBring a light and a dark shirt. Arrive 15 minutes early.\nLet your captain know: Going / Maybe / Not going.`}\n\n${link}`
}
