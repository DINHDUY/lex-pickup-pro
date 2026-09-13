import { useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  ArrowLeft,
  CalendarDays,
  Check,
  Clock3,
  Download,
  ExternalLink,
  Flag,
  MapPin,
  MessageCircle,
  Plus,
  Save,
  Shuffle,
  Star,
  Target,
  Trash2,
  Users,
  X,
} from 'lucide-react'
import { toast } from 'sonner'
import { api, refreshClub, send, useClub } from '../api'
import { cn, matchDate, matchTime, sideName } from '../lib'
import type { LineupSlot, MatchDetail, Player, Side, User } from '../types'
import {
  Avatar,
  Badge,
  Button,
  EmptyState,
  ErrorState,
  Loading,
  Modal,
  RSVPButtons,
  TeamCrest,
} from '../components/ui'
import { ShareDialog } from '../components/ShareDialog'
import { CreateMatch } from '../components/CreateMatch'
import { matchSummary } from '../share'

const formationBySize: Record<number, string[]> = {
  5: ['2-2'],
  6: ['2-2-1'],
  7: ['2-3-1', '3-2-1'],
  8: ['3-3-1'],
  9: ['3-3-2'],
  10: ['3-4-2'],
  11: ['4-3-3'],
}

function LineupBuilder({
  match,
  players,
  canEdit,
}: {
  match: MatchDetail
  players: Player[]
  canEdit: boolean
}) {
  const [lineup, setLineup] = useState<LineupSlot[]>(match.lineup),
    [formation, setFormation] = useState(match.formation),
    [selected, setSelected] = useState<number | null>(null)
  const editable = canEdit && match.status === 'scheduled'
  const [side, setSide] = useState<Side>('home')
  const save = useMutation({
    mutationFn: () => send(`/matches/${match.id}/lineup`, { formation, players: lineup }, 'PUT'),
    onSuccess: () => {
      refreshClub()
      toast.success('Lineup saved. Your team sheet is ready.')
    },
    onError: (e: Error) => toast.error(e.message),
  })
  const balance = useMutation({
    mutationFn: () =>
      send<{ estimated_player_ids: number[]; estimated_skill: number }>(`/matches/${match.id}/balance`),
    onSuccess: (result) => {
      refreshClub()
      toast.success(
        result.estimated_player_ids.length
          ? `Mixed sides created. ${result.estimated_player_ids.length} unrated players balanced using ${result.estimated_skill}/10 estimates.`
          : 'Balanced mixed sides created from confirmed players',
      )
    },
    onError: (e: Error) => toast.error(e.message),
  })
  const rows = [1, ...formation.split('-').map(Number)]
  const positions = rows.flatMap((count, row) =>
    Array.from({ length: count }, (_, col) => ({
      x: ((col + 1) * 100) / (count + 1),
      y: 86 - row * (69 / (rows.length - 1)),
    })),
  )
  const eligible = players.filter((p) => match.rsvps.find((r) => r.player_id === p.id)?.status !== 'out')
  function assign(playerId: number, slot: number) {
    if (!editable) return
    setLineup((previous) => [
      ...previous.filter((p) => p.player_id !== playerId && !(p.side === side && p.slot === slot)),
      { player_id: playerId, side, slot },
    ])
    setSelected(null)
  }
  function place(slot: number) {
    if (selected) assign(selected, slot)
    else {
      const existing = lineup.find((p) => p.side === side && p.slot === slot)
      if (existing) setSelected(existing.player_id)
    }
  }
  const dirty = JSON.stringify(lineup) !== JSON.stringify(match.lineup) || formation !== match.formation
  return (
    <>
      {players.some((p) => p.skill === null) && (
        <p className="small-note">
          Auto-balance uses a neutral 5.5/10 estimate for unrated players. Their profiles stay unrated.
        </p>
      )}
      <div className="lineup-toolbar">
        <div className="tabs">
          <button
            onClick={() => {
              setSide('home')
              setSelected(null)
            }}
            className={side === 'home' ? 'active' : ''}
          >
            {sideName(match, 'home')}
          </button>
          <button
            onClick={() => {
              setSide('away')
              setSelected(null)
            }}
            className={side === 'away' ? 'active' : ''}
          >
            {sideName(match, 'away')}
          </button>
        </div>
        <div className="lineup-tools">
          <select
            value={formation}
            onChange={(e) => setFormation(e.target.value)}
            disabled={!editable}
            aria-label="Formation"
          >
            {formationBySize[match.capacity / 2].map((f) => (
              <option key={f}>{f}</option>
            ))}
          </select>
          {editable && (
            <>
              <Button variant="secondary" onClick={() => balance.mutate()} busy={balance.isPending}>
                <Shuffle size={15} />
                Balance sides
              </Button>
              <Button onClick={() => save.mutate()} busy={save.isPending} disabled={!dirty}>
                <Save size={15} />
                Save lineup
              </Button>
            </>
          )}
        </div>
      </div>
      <div className="lineup-layout">
        <div className="football-pitch">
          <div className="pitch-markings">
            <span className="pitch-center" />
            <span className="pitch-halfway" />
            <span className="pitch-box pitch-box-top" />
            <span className="pitch-box pitch-box-bottom" />
            <span className="pitch-goal pitch-goal-top" />
            <span className="pitch-goal pitch-goal-bottom" />
          </div>
          {positions.map((pos, slot) => {
            const entry = lineup.find((p) => p.side === side && p.slot === slot)
            const p = players.find((p) => p.id === entry?.player_id)
            return (
              <div
                className="pitch-position"
                style={{ left: `${pos.x}%`, top: `${pos.y}%` }}
                key={slot}
                onDragOver={(e) => editable && e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault()
                  const playerId = Number(e.dataTransfer.getData('text/plain'))
                  if (eligible.some((p) => p.id === playerId)) assign(playerId, slot)
                }}
              >
                <button
                  onClick={() => place(slot)}
                  disabled={!editable}
                  className={cn(
                    'pitch-player',
                    side === 'away' && 'pitch-player-gold',
                    selected === p?.id && 'pitch-selected',
                    !p && 'pitch-empty',
                  )}
                  aria-label={`${side} position ${slot + 1}${p ? `: ${p.name}` : ': empty'}`}
                  draggable={editable && !!p}
                  onDragStart={(e) => p && e.dataTransfer.setData('text/plain', String(p.id))}
                >
                  {p ? (p.jersey ?? '•') : <Plus size={19} />}
                </button>
                <span>{p ? p.name.split(' ').at(-1) : slot === 0 ? 'Goalkeeper' : 'Add player'}</span>
                {p && editable && (
                  <button
                    className="remove-pitch-player"
                    aria-label={`Remove ${p.name} from lineup`}
                    onClick={() => setLineup((previous) => previous.filter((l) => l.player_id !== p.id))}
                  >
                    <X size={12} />
                  </button>
                )}
              </div>
            )
          })}
          <div className="pitch-caption">
            {sideName(match, side)} · {formation}
          </div>
        </div>
        <div className="card player-bench">
          <h3>{editable ? 'Build your side' : 'The team sheet'}</h3>
          <p>
            {editable
              ? 'Tap a player, then a position. Or drag them onto the pitch.'
              : 'Your captain’s plan for the game.'}
          </p>
          {editable && (
            <div className="lineup-selection" role="status">
              {selected
                ? `${players.find((p) => p.id === selected)?.name} selected. Tap a pitch position.`
                : 'Choose a player to get started.'}
            </div>
          )}
          <div className="bench-players">
            {(editable
              ? eligible
              : players.filter((p) => lineup.some((l) => l.player_id === p.id && l.side === side))
            ).map((p) => {
              const assigned = lineup.find((l) => l.player_id === p.id)
              const going = match.rsvps.find((r) => r.player_id === p.id)?.status === 'going'
              return (
                <button
                  key={p.id}
                  className={cn('bench-player', selected === p.id && 'selected')}
                  onClick={() => editable && setSelected(selected === p.id ? null : p.id)}
                  disabled={!editable}
                  draggable={editable}
                  onDragStart={(e) => e.dataTransfer.setData('text/plain', String(p.id))}
                >
                  <Avatar player={p} size="sm" />
                  <span>
                    <strong>{p.name}</strong>
                    <small>
                      {p.positions || 'Position not provided'} ·{' '}
                      {p.skill === null ? 'Unrated' : `${p.skill} skill`} {going ? '· Going' : ''}
                    </small>
                  </span>
                  {assigned ? (
                    <Badge tone={assigned.side === 'home' ? 'green' : 'gold'}>
                      {assigned.side === 'home' ? 'Green' : 'Gold'}
                    </Badge>
                  ) : (
                    <Plus size={15} />
                  )}
                </button>
              )
            })}
          </div>
        </div>
      </div>
      {editable && (
        <p className="small-note">
          Balancing uses Going responses and self-ratings, and changes the game to mixed sides. Save manual
          edits before leaving. {dirty && <strong> You have unsaved lineup changes.</strong>}
        </p>
      )}
    </>
  )
}

export function MatchPage({ user }: { user: User }) {
  const { id } = useParams(),
    club = useClub()
  const query = useQuery({ queryKey: ['match', id], queryFn: () => api<MatchDetail>(`/matches/${id}`) })
  const [editMatch, setEditMatch] = useState(false)
  const [tab, setTab] = useState('overview'),
    [share, setShare] = useState(false),
    [shareLineup, setShareLineup] = useState(false)
  const [resultOpen, setResultOpen] = useState(false),
    [eventOpen, setEventOpen] = useState(false),
    [eventPlayer, setEventPlayer] = useState(''),
    [eventKind, setEventKind] = useState('goal'),
    [removeId, setRemoveId] = useState<number | null>(null)
  const canEdit = user.role !== 'player'
  const action = useMutation({
    mutationFn: ({ path, data, method }: { path: string; data?: unknown; method?: string }) =>
      send(`/matches/${id}/${path}`, data, method || 'POST'),
    onSuccess: () => {
      refreshClub()
      setResultOpen(false)
      setEventOpen(false)
      setRemoveId(null)
      toast.success('Match updated')
    },
    onError: (e: Error) => toast.error(e.message),
  })
  if (query.isPending || club.loading) return <Loading />
  if (query.error || club.error) return <ErrorState error={(query.error || club.error)!} />
  const m = query.data,
    playerMap = new Map([...club.players, ...m.players].map((p) => [p.id, p]))
  const lineupPlayers = m.lineup
    .map((l) => ({ ...l, player: playerMap.get(l.player_id) }))
    .filter((l) => l.player)
  const eventSide = m.lineup.find((l) => l.player_id === Number(eventPlayer))?.side
  const customLineup = `${matchSummary(m)}\n\n📋 LINEUPS (${m.formation})\n${(['home', 'away'] as Side[])
    .map(
      (side) =>
        `${sideName(m, side)}: ${
          lineupPlayers
            .filter((l) => l.side === side)
            .sort((a, b) => a.slot - b.slot)
            .map((l) => l.player!.name)
            .join(', ') || 'To be announced'
        }`,
    )
    .join('\n')}`
  function saveResult(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    action.mutate({
      path: 'result',
      data: {
        home_score: Number(f.get('home_score')),
        away_score: Number(f.get('away_score')),
        status: f.get('status'),
      },
      method: 'PATCH',
    })
  }
  function saveEvent(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    action.mutate({
      path: 'events',
      data: {
        player_id: Number(f.get('player_id')),
        assist_player_id:
          eventKind === 'goal' && f.get('assist_player_id') ? Number(f.get('assist_player_id')) : null,
        minute: Number(f.get('minute')),
        kind: eventKind,
      },
    })
  }
  return (
    <>
      <Link to={m.status === 'completed' ? '/history' : '/schedule'} className="back-link">
        <ArrowLeft size={16} />
        Back to {m.status === 'completed' ? 'match history' : 'schedule'}
      </Link>
      <div className="match-page-title">
        <div className="match-title-meta">
          <Badge tone={m.status === 'live' ? 'red' : m.status === 'completed' ? 'gray' : 'green'}>
            {m.status === 'live'
              ? 'LIVE'
              : m.status === 'completed'
                ? 'FULL TIME'
                : m.status === 'cancelled'
                  ? 'CANCELLED'
                  : 'UPCOMING'}
          </Badge>
          <span>
            {m.kind === 'mixed' ? 'Mixed sides' : 'Club derby'} · {m.capacity / 2} a side
          </span>
        </div>
        <div className="heading-actions">
          {canEdit && m.status === 'scheduled' && (
            <Button variant="secondary" onClick={() => setEditMatch(true)}>
              Edit game
            </Button>
          )}
          <Button variant="secondary" onClick={() => setShare(true)}>
            <MessageCircle size={16} />
            Share to Messenger
          </Button>
          {canEdit && m.status !== 'cancelled' && (
            <Button onClick={() => setResultOpen(true)}>
              <Flag size={16} />
              {m.status === 'completed'
                ? 'Correct result'
                : m.status === 'live'
                  ? 'Update result'
                  : 'Match day controls'}
            </Button>
          )}
        </div>
      </div>
      <section className="match-detail-hero">
        <div className="hero-pitch-lines" aria-hidden="true">
          <div />
          <span />
        </div>
        <div className="match-detail-teams">
          <div>
            <TeamCrest team={1} size={82} />
            <h1>{sideName(m, 'home')}</h1>
          </div>
          <div className="match-center-score">
            {['live', 'completed'].includes(m.status) ? (
              <strong>
                {m.home_score}
                <span>:</span>
                {m.away_score}
              </strong>
            ) : (
              <strong className="match-vs">VS</strong>
            )}
            <Badge tone="gray">{m.status === 'completed' ? 'FULL TIME' : matchTime(m.starts_at)}</Badge>
          </div>
          <div>
            <TeamCrest team={2} size={82} />
            <h1>{sideName(m, 'away')}</h1>
          </div>
        </div>
        <div className="hero-game-info">
          <span>
            <CalendarDays size={16} />
            {matchDate(m.starts_at)}
          </span>
          <span>
            <MapPin size={16} />
            {m.pitch}
          </span>
          <span>
            <Clock3 size={16} />
            {m.duration_minutes} minutes
          </span>
        </div>
      </section>
      <div className="match-tabs tabs">
        {[
          ['overview', 'Game plan'],
          ['lineup', 'Lineups'],
          ['events', 'Match events'],
          ['ratings', 'Player ratings'],
        ].map(([v, label]) => (
          <button key={v} className={tab === v ? 'active' : ''} onClick={() => setTab(v)}>
            {label}
            {v === 'events' && <span>{m.events.length}</span>}
          </button>
        ))}
      </div>
      {tab === 'overview' && (
        <div className="match-overview-grid">
          <section className="card padded-card">
            <h2>{m.title}</h2>
            <div className="match-location">
              <span className="location-icon">
                <MapPin size={26} />
              </span>
              <div>
                <strong>{m.location}</strong>
                <p>{m.address}</p>
                <span>{m.pitch}</span>
              </div>
            </div>
            <a
              className="text-link"
              href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(m.address || m.location)}`}
              target="_blank"
              rel="noreferrer"
            >
              Get directions
              <ExternalLink size={14} />
            </a>
            <hr />
            <h3>A note from your captain</h3>
            <p className="match-notes">{m.notes || 'No extra notes. Bring your best game.'}</p>
            <a className="btn btn-secondary calendar-link" href={`/api/v1/matches/${m.id}/calendar`} download>
              <Download size={16} />
              Add to calendar
            </a>
          </section>
          <section className="card padded-card">
            <div className="section-heading no-padding">
              <h2>{m.status === 'scheduled' ? 'Are you in?' : 'The squad'}</h2>
              <Users size={19} />
            </div>
            <p className="muted">
              {m.status === 'scheduled'
                ? 'Let your captain know. You can change your mind before kickoff.'
                : 'The people who made this game happen.'}
            </p>
            {m.status === 'scheduled' && <RSVPButtons match={m} />}
            <div className="match-attendance-stats">
              <div>
                <strong>{m.going}</strong>
                <span>Going</span>
              </div>
              <div>
                <strong>{m.maybe}</strong>
                <span>Maybe</span>
              </div>
              <div>
                <strong>{m.out}</strong>
                <span>Not going</span>
              </div>
            </div>
            <div className="confirmed-avatars">
              {m.rsvps
                .filter((r) => r.status === 'going')
                .map((r) => {
                  const p = playerMap.get(r.player_id)
                  return (
                    p && (
                      <Link key={p.id} to={`/players/${p.id}`} title={p.name}>
                        <Avatar player={p} size="sm" />
                      </Link>
                    )
                  )
                })}
            </div>
            <button className="text-link" onClick={() => setTab('lineup')}>
              See the team sheet
              <Users size={14} />
            </button>
          </section>
        </div>
      )}
      {tab === 'lineup' && (
        <>
          <LineupBuilder
            key={`${m.id}-${JSON.stringify(m.lineup)}-${m.formation}-${m.kind}`}
            match={m}
            players={m.status === 'scheduled' ? club.players : Array.from(playerMap.values())}
            canEdit={canEdit}
          />
          <div className="lineup-share">
            <Button variant="secondary" onClick={() => setShareLineup(true)}>
              <MessageCircle size={16} />
              Share lineup announcement
            </Button>
          </div>
        </>
      )}
      {tab === 'events' && (
        <section className="card padded-card">
          <div className="section-heading no-padding">
            <h2>The story of the game</h2>
            {canEdit && ['live', 'completed'].includes(m.status) && (
              <Button onClick={() => setEventOpen(true)}>
                <Plus size={16} />
                Add event
              </Button>
            )}
          </div>
          {m.events.length ? (
            <div className="event-timeline">
              {m.events.map((e) => (
                <div className="match-event" key={e.id}>
                  <span className="event-minute">{e.minute}′</span>
                  <span className={`event-symbol event-${e.kind}`}>
                    {e.kind.includes('card') ? <span /> : <Target size={21} />}
                  </span>
                  <div>
                    <strong>
                      {playerMap.get(e.player_id)?.name || 'Club player'}
                      <Badge tone={e.kind === 'goal' ? 'green' : 'gold'}>{e.kind.replaceAll('_', ' ')}</Badge>
                    </strong>
                    <p>
                      {e.assist_player_id
                        ? `Assist: ${playerMap.get(e.assist_player_id)?.name || 'Club player'}`
                        : sideName(m, e.side)}
                    </p>
                  </div>
                  {canEdit && (
                    <button
                      className="icon-btn"
                      aria-label={`Remove event at ${e.minute} minutes`}
                      onClick={() => setRemoveId(e.id)}
                    >
                      <Trash2 size={16} />
                    </button>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              title="Every moment counts"
              description={
                m.status === 'scheduled'
                  ? 'Start the game from Match day controls, then record goals, assists, and cards.'
                  : 'Add the goals and assists behind the scoreline.'
              }
            />
          )}
        </section>
      )}
      {tab === 'ratings' && (
        <section className="card padded-card">
          <h2>A little credit where it’s due.</h2>
          <p className="muted">
            Rate performances from 1–10. One rating per player; you can update it later.
          </p>
          {m.status !== 'completed' ? (
            <EmptyState
              title="Let the football do the talking first"
              description="Ratings open when the game is marked complete."
            />
          ) : (
            <div className="rating-list">
              {lineupPlayers
                .filter((l) => l.player_id !== user.player.id)
                .map((l) => (
                  <form
                    key={l.player_id}
                    onSubmit={(e) => {
                      e.preventDefault()
                      const f = new FormData(e.currentTarget)
                      action.mutate({
                        path: 'ratings',
                        data: { player_id: l.player_id, value: Number(f.get('value')) },
                        method: 'PUT',
                      })
                    }}
                  >
                    <Avatar player={l.player!} size="sm" />
                    <div>
                      <strong>{l.player!.name}</strong>
                      <span>{sideName(m, l.side)}</span>
                    </div>
                    <Star size={16} className="gold-text" />
                    <input
                      aria-label={`Rating for ${l.player!.name}`}
                      name="value"
                      type="number"
                      min="1"
                      max="10"
                      step="0.1"
                      required
                      defaultValue={m.my_ratings.find((r) => r.player_id === l.player_id)?.value || 7}
                    />
                    <Button type="submit" variant="secondary" busy={action.isPending}>
                      {m.my_ratings.some((r) => r.player_id === l.player_id) ? 'Update' : 'Rate'}
                    </Button>
                  </form>
                ))}
            </div>
          )}
        </section>
      )}
      <CreateMatch open={editMatch} onOpenChange={setEditMatch} match={m} />
      <ShareDialog open={share} onOpenChange={setShare} match={m} />
      <ShareDialog
        open={shareLineup}
        onOpenChange={setShareLineup}
        customText={customLineup}
        title="The team sheet, ready to share"
      />
      <Modal
        open={resultOpen}
        onOpenChange={setResultOpen}
        title="Match day controls"
        description="Keep the scoreline current. Completed games update club statistics."
      >
        <form className="form-stack" onSubmit={saveResult}>
          <div className="form-grid">
            <label>
              {sideName(m, 'home')}
              <input type="number" name="home_score" min="0" max="99" defaultValue={m.home_score} required />
            </label>
            <label>
              {sideName(m, 'away')}
              <input type="number" name="away_score" min="0" max="99" defaultValue={m.away_score} required />
            </label>
          </div>
          <label>
            Game status
            <select
              aria-label="Game status"
              name="status"
              defaultValue={m.status === 'scheduled' ? 'live' : m.status}
            >
              {m.status !== 'completed' && (
                <>
                  <option value="scheduled">Scheduled</option>
                  <option value="live">Live · game on</option>
                </>
              )}
              <option value="completed">Completed · full time</option>
              <option value="cancelled">Cancelled</option>
            </select>
          </label>
          <p className="small-note">
            Assign both lineups before completing a match. Live goal events add to the score automatically;
            post-match events attribute goals within the saved score.
          </p>
          <Button type="submit" busy={action.isPending}>
            <Check size={16} />
            Save match
          </Button>
        </form>
      </Modal>
      <Modal
        open={eventOpen}
        onOpenChange={setEventOpen}
        title="Capture the moment"
        description="Goals, assists, and the occasional card."
      >
        <form className="form-stack" onSubmit={saveEvent}>
          <div className="form-grid">
            <label>
              Event
              <select value={eventKind} onChange={(e) => setEventKind(e.target.value)}>
                <option value="goal">Goal</option>
                <option value="own_goal">Own goal</option>
                <option value="yellow_card">Yellow card</option>
                <option value="red_card">Red card</option>
              </select>
            </label>
            <label>
              Minute
              <input name="minute" type="number" min="0" max={m.duration_minutes} defaultValue={1} required />
            </label>
          </div>
          <label>
            Player
            <select
              aria-label="Player"
              name="player_id"
              value={eventPlayer}
              onChange={(e) => setEventPlayer(e.target.value)}
              required
            >
              <option value="">Choose a player</option>
              {lineupPlayers.map((l) => (
                <option key={l.player_id} value={l.player_id}>
                  {l.player!.name} · {sideName(m, l.side)}
                </option>
              ))}
            </select>
          </label>
          {eventKind === 'goal' && (
            <label>
              Assist · optional
              <select name="assist_player_id" key={eventPlayer}>
                <option value="">Unassisted</option>
                {lineupPlayers
                  .filter((l) => l.side === eventSide && l.player_id !== Number(eventPlayer))
                  .map((l) => (
                    <option key={l.player_id} value={l.player_id}>
                      {l.player!.name}
                    </option>
                  ))}
              </select>
            </label>
          )}
          <Button type="submit" busy={action.isPending}>
            <Plus size={16} />
            Add event
          </Button>
        </form>
      </Modal>
      <Modal
        open={removeId !== null}
        onOpenChange={(v) => !v && setRemoveId(null)}
        title="Remove this event?"
        description="The player’s statistics will be corrected. Live scores are adjusted; a completed result stays as recorded."
      >
        <div className="modal-actions">
          <Button variant="secondary" onClick={() => setRemoveId(null)}>
            Keep event
          </Button>
          <Button
            variant="danger"
            busy={action.isPending}
            onClick={() => action.mutate({ path: `events/${removeId}`, method: 'DELETE' })}
          >
            Remove event
          </Button>
        </div>
      </Modal>
    </>
  )
}
