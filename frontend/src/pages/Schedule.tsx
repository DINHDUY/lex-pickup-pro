import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  addMonths,
  eachDayOfInterval,
  endOfMonth,
  endOfWeek,
  format,
  isSameDay,
  isSameMonth,
  startOfMonth,
  startOfWeek,
} from 'date-fns'
import {
  ArrowRight,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Download,
  List,
  MapPin,
  MessageCircle,
  Plus,
  Printer,
  Search,
} from 'lucide-react'
import { useClub } from '../api'
import { cn, matchDate, matchTime, nextMatches, sideName } from '../lib'
import type { Match, User } from '../types'
import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  Loading,
  PageHeading,
  RSVPButtons,
  TeamCrest,
} from '../components/ui'
import { CreateMatch } from '../components/CreateMatch'
import { ShareDialog } from '../components/ShareDialog'

export function Schedule({ user, history = false }: { user: User; history?: boolean }) {
  const club = useClub(),
    [create, setCreate] = useState(false),
    [share, setShare] = useState<Match | null>(null)
  const [view, setView] = useState('list'),
    [month, setMonth] = useState(new Date()),
    [query, setQuery] = useState(''),
    [filter, setFilter] = useState('all')
  if (club.loading) return <Loading />
  if (club.error) return <ErrorState error={club.error} />
  const source = history
    ? club.matches.filter((m) => ['completed', 'cancelled'].includes(m.status))
    : nextMatches(club.matches)
  const matches = source.filter(
    (m) =>
      (filter === 'all' || m.kind === filter) &&
      `${m.title} ${m.location} ${matchDate(m.starts_at)}`.toLowerCase().includes(query.toLowerCase()),
  )
  const days = eachDayOfInterval({
    start: startOfWeek(startOfMonth(month), { weekStartsOn: 1 }),
    end: endOfWeek(endOfMonth(month), { weekStartsOn: 1 }),
  })
  return (
    <>
      <PageHeading
        eyebrow={history ? 'THE CLUB SCRAPBOOK' : 'MAKE TIME FOR THE GAME'}
        title={history ? 'Every game has a story.' : 'See you on Saturday.'}
        description={
          history
            ? 'The goals, the results, and the games we’re still talking about.'
            : 'Your next run-out is right here. Let the squad know you’re in.'
        }
        action={
          history ? (
            <>
              <a className="btn btn-secondary" href="/api/v1/export/matches" download>
                <Download size={16} />
                Export CSV
              </a>
              <Button variant="secondary" onClick={() => window.print()}>
                <Printer size={16} />
                Print / PDF
              </Button>
            </>
          ) : (
            user.role !== 'player' && (
              <Button onClick={() => setCreate(true)}>
                <Plus size={17} />
                Schedule game
              </Button>
            )
          )
        }
      />
      <div className="toolbar">
        <div className="tabs">
          {[
            ['all', 'All games'],
            ['classic', 'Club derbies'],
            ['mixed', 'Mixed sides'],
          ].map(([id, name]) => (
            <button key={id} className={filter === id ? 'active' : ''} onClick={() => setFilter(id)}>
              {name}
            </button>
          ))}
        </div>
        <div className="toolbar-right">
          <div className="search-field">
            <Search size={16} />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Find a game…"
              aria-label="Search games"
            />
          </div>
          {!history && (
            <div className="view-toggle">
              <button
                className={view === 'list' ? 'active' : ''}
                onClick={() => setView('list')}
                aria-label="List view"
              >
                <List size={18} />
              </button>
              <button
                className={view === 'calendar' ? 'active' : ''}
                onClick={() => setView('calendar')}
                aria-label="Calendar view"
              >
                <CalendarDays size={18} />
              </button>
            </div>
          )}
        </div>
      </div>
      {view === 'calendar' && !history ? (
        <section className="card calendar-card">
          <div className="calendar-header">
            <h2>{format(month, 'MMMM yyyy')}</h2>
            <div>
              <Button
                variant="ghost"
                onClick={() => setMonth(addMonths(month, -1))}
                aria-label="Previous month"
              >
                <ChevronLeft size={18} />
              </Button>
              <Button variant="secondary" onClick={() => setMonth(new Date())}>
                Today
              </Button>
              <Button variant="ghost" onClick={() => setMonth(addMonths(month, 1))} aria-label="Next month">
                <ChevronRight size={18} />
              </Button>
            </div>
          </div>
          <div className="calendar-grid">
            {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((d) => (
              <span className="calendar-day-label" key={d}>
                {d}
              </span>
            ))}
            {days.map((day) => (
              <div
                className={cn(
                  'calendar-day',
                  !isSameMonth(day, month) && 'outside-month',
                  isSameDay(day, new Date()) && 'calendar-today',
                )}
                key={day.toISOString()}
              >
                <span>{format(day, 'd')}</span>
                {matches
                  .filter((m) => isSameDay(new Date(m.starts_at), day))
                  .map((m) => (
                    <Link to={`/matches/${m.id}`} key={m.id}>
                      <span>{matchTime(m.starts_at)}</span>
                      <strong>{m.kind === 'classic' ? 'OG vs YB' : 'Mixed sides'}</strong>
                    </Link>
                  ))}
              </div>
            ))}
          </div>
        </section>
      ) : (
        <div className="match-list">
          {matches.length ? (
            matches.map((m) => (
              <article className="card fixture-card" key={m.id}>
                <div className="fixture-date">
                  <span>{format(new Date(m.starts_at), 'MMM')}</span>
                  <strong>{format(new Date(m.starts_at), 'dd')}</strong>
                  <small>{format(new Date(m.starts_at), 'EEEE')}</small>
                </div>
                <div className="fixture-main">
                  <div className="fixture-top">
                    <Badge tone={m.kind === 'mixed' ? 'gold' : 'green'}>
                      {m.kind === 'mixed' ? 'Mixed sides' : 'Club derby'}
                    </Badge>
                    <span>
                      {m.status === 'cancelled'
                        ? 'Cancelled'
                        : history
                          ? 'Full time'
                          : matchTime(m.starts_at)}{' '}
                      <span>·</span> {m.capacity / 2} a side
                    </span>
                  </div>
                  <Link to={`/matches/${m.id}`} className="fixture-teams">
                    <span>
                      <TeamCrest team={1} size={30} />
                      {sideName(m, 'home')}
                    </span>
                    <strong>{m.status === 'completed' ? `${m.home_score} – ${m.away_score}` : 'vs'}</strong>
                    <span>
                      <TeamCrest team={2} size={30} />
                      {sideName(m, 'away')}
                    </span>
                  </Link>
                  <p>
                    <MapPin size={14} />
                    {m.location} · {m.pitch}
                  </p>
                </div>
                <div className="fixture-actions">
                  {!history && (
                    <>
                      <span className="fixture-confirmed">
                        <span className="status-dot" />
                        {m.going} / {m.capacity} confirmed
                      </span>
                      <RSVPButtons match={m} compact />
                    </>
                  )}
                  <div className="fixture-links">
                    <button className="text-link" onClick={() => setShare(m)}>
                      <MessageCircle size={15} />
                      Share
                    </button>
                    <Link to={`/matches/${m.id}`} className="text-link">
                      {history ? 'Match report' : 'Match center'}
                      <ArrowRight size={15} />
                    </Link>
                  </div>
                </div>
              </article>
            ))
          ) : (
            <EmptyState
              title={history ? 'No matches in the archive yet' : 'A clear calendar. Plenty of possibilities.'}
              description={
                query || filter !== 'all'
                  ? 'Try a different search or game type.'
                  : 'Your club’s games will appear here.'
              }
            >
              {!history && user.role !== 'player' && (
                <Button onClick={() => setCreate(true)}>Schedule the first game</Button>
              )}
            </EmptyState>
          )}
        </div>
      )}
      <CreateMatch open={create} onOpenChange={setCreate} />
      {share && <ShareDialog open onOpenChange={(v) => !v && setShare(null)} match={share} />}
    </>
  )
}
