import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Check, CircleHelp, MessageCircle, Minus, X } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { api, useClub } from '../api'
import { matchDate, nextMatches, teamName, teamTone } from '../lib'
import type { MatchDetail, User } from '../types'
import {
  Avatar,
  Badge,
  Button,
  EmptyState,
  ErrorState,
  Loading,
  PageHeading,
  RSVPButtons,
} from '../components/ui'
import { ShareDialog } from '../components/ShareDialog'

export function Availability({ user }: { user: User }) {
  const club = useClub(),
    [selected, setSelected] = useState(''),
    [share, setShare] = useState(false),
    [filter, setFilter] = useState('all')
  const upcoming = nextMatches(club.matches),
    matchId = selected || String(upcoming[0]?.id || '')
  const detail = useQuery({
    queryKey: ['match', matchId],
    queryFn: () => api<MatchDetail>(`/matches/${matchId}`),
    enabled: !!matchId,
  })
  if (club.loading) return <Loading />
  if (club.error) return <ErrorState error={club.error} />
  const m = detail.data
  const players = club.players.filter(
    (p) => filter === 'all' || (m?.rsvps.find((r) => r.player_id === p.id)?.status || 'pending') === filter,
  )
  return (
    <>
      <PageHeading
        eyebrow="LESS CHASING. MORE PLAYING."
        title="Who’s up for a game?"
        description="One clear team sheet. No scrolling through a hundred messages."
        action={
          m && (
            <Button variant="secondary" onClick={() => setShare(true)}>
              <MessageCircle size={16} />
              Share reminder
            </Button>
          )
        }
      />
      {!upcoming.length ? (
        <EmptyState
          title="Nothing to check into yet"
          description="Once a game is scheduled, you can let the captain know you’re in."
        />
      ) : (
        <>
          <div className="card availability-game">
            <label>
              CHECK-IN FOR
              <select value={matchId} onChange={(e) => setSelected(e.target.value)} aria-label="Select game">
                {upcoming.map((m) => (
                  <option key={m.id} value={m.id}>
                    {matchDate(m.starts_at)} · {m.title}
                  </option>
                ))}
              </select>
            </label>
            {m && (
              <div>
                <span>Your response, {user.player.name.split(' ')[0]}</span>
                <RSVPButtons match={m} />
              </div>
            )}
          </div>
          {detail.isPending ? (
            <Loading />
          ) : detail.error ? (
            <ErrorState error={detail.error} />
          ) : (
            m && (
              <>
                <div className="availability-counts">
                  {[
                    ['going', 'Going', m.going, <Check size={20} />],
                    ['maybe', 'Maybe', m.maybe, <CircleHelp size={20} />],
                    ['out', 'Not going', m.out, <X size={20} />],
                    ['pending', 'Yet to respond', club.players.length - m.rsvps.length, <Minus size={20} />],
                  ].map(([id, label, count, icon]) => (
                    <button
                      key={String(id)}
                      className={`card availability-count count-${id} ${filter === id ? 'active' : ''}`}
                      onClick={() => setFilter(filter === id ? 'all' : String(id))}
                    >
                      <span>{icon}</span>
                      <strong>{count}</strong>
                      <small>{label}</small>
                    </button>
                  ))}
                </div>
                <section className="card">
                  <div className="section-heading">
                    <h2>The team sheet</h2>
                    <Badge tone="gray">{m.capacity - m.going} spots available</Badge>
                  </div>
                  <div className="table-scroll">
                    <table className="data-table availability-table">
                      <thead>
                        <tr>
                          <th>PLAYER</th>
                          <th>TEAM</th>
                          <th>STATUS</th>
                          <th>PLAYER NOTE</th>
                        </tr>
                      </thead>
                      <tbody>
                        {players.map((p) => {
                          const response = m.rsvps.find((r) => r.player_id === p.id)?.status
                          return (
                            <tr key={p.id}>
                              <td>
                                <Link to={`/players/${p.id}`} className="player-cell">
                                  <Avatar player={p} size="sm" />
                                  <span>
                                    <strong>
                                      {p.name}
                                      {p.id === user.player.id ? ' (you)' : ''}
                                    </strong>
                                    <small>{p.positions?.replaceAll(',', ' / ') || 'Not provided'}</small>
                                  </span>
                                </Link>
                              </td>
                              <td>
                                <Badge tone={teamTone(p.team_id)}>{teamName(p.team_id)}</Badge>
                              </td>
                              <td>
                                <span className={`response-status status-${response || 'pending'}`}>
                                  {response === 'going' ? (
                                    <Check size={15} />
                                  ) : response === 'maybe' ? (
                                    <CircleHelp size={15} />
                                  ) : response === 'out' ? (
                                    <X size={15} />
                                  ) : (
                                    <Minus size={15} />
                                  )}
                                  {response === 'going'
                                    ? 'Going'
                                    : response === 'maybe'
                                      ? 'Maybe'
                                      : response === 'out'
                                        ? 'Not going'
                                        : 'Awaiting response'}
                                </span>
                              </td>
                              <td className="muted">
                                {p.injury_note || (p.availability === 'away' ? 'Away for now' : '—')}
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                  {!players.length && <p className="table-empty">No players in this group yet.</p>}
                </section>
                <p className="small-note">
                  Check-ins close at kickoff. A full game? Choose Maybe to join the reserve list, and your
                  captain can follow up.
                </p>
              </>
            )
          )}
        </>
      )}
      {m && <ShareDialog open={share} onOpenChange={setShare} match={m} />}
    </>
  )
}
