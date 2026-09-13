import { useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  ArrowLeft,
  ArrowRight,
  Award,
  CalendarDays,
  Check,
  Crown,
  Download,
  Edit3,
  Footprints,
  HeartPulse,
  Plus,
  Search,
  Shield,
  Star,
  Target,
  Trophy,
} from 'lucide-react'
import { toast } from 'sonner'
import { api, refreshClub, send, useClub } from '../api'
import type { Player, PlayerDetail, User } from '../types'
import { matchDate, matchesTeam, teamName, teamTone } from '../lib'
import {
  Avatar,
  Badge,
  Button,
  EmptyState,
  ErrorState,
  FormGuide,
  Loading,
  Modal,
  PageHeading,
  StatCard,
} from '../components/ui'

export function ProfileForm({
  player,
  onDone,
  onCancel,
}: {
  player?: Player
  onDone: () => void
  onCancel: () => void
}) {
  const [error, setError] = useState('')
  const mutation = useMutation({
    mutationFn: (data: unknown) =>
      send(player ? `/players/${player.id}` : '/players', data, player ? 'PUT' : 'POST'),
    onSuccess: () => {
      refreshClub()
      toast.success(player ? 'Profile updated' : 'Player added to the squad')
      onDone()
    },
    onError: (e: Error) => setError(e.message),
  })
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setError('')
    const f = new FormData(e.currentTarget)
    const data = Object.fromEntries(f)
    mutation.mutate({
      ...data,
      skill: data.skill === '' ? null : Number(data.skill),
      jersey: data.jersey === '' ? null : Number(data.jersey),
      positions: data.positions || null,
      dominant_foot: data.dominant_foot || null,
      age_group: data.age_group || null,
      availability: data.availability || null,
      preferred_times: data.preferred_times || null,
      ...(!player ? { team_id: data.team_id === '' ? null : Number(data.team_id) } : {}),
    })
  }
  return (
    <form className="form-stack" onSubmit={submit}>
      <div className="form-grid">
        <label>
          Full name
          <input name="name" defaultValue={player?.name} required minLength={2} maxLength={80} />
        </label>
        <label>
          Nickname
          <input name="nickname" defaultValue={player?.nickname} maxLength={40} />
        </label>
      </div>
      {!player && (
        <label>
          Primary team
          <select name="team_id" defaultValue="">
            <option value="">Unassigned</option>
            <option value="1">Old Gentlemen</option>
            <option value="2">Young Boys</option>
          </select>
        </label>
      )}
      <div className="form-grid">
        <label>
          Positions
          <input name="positions" defaultValue={player?.positions ?? ''} placeholder="CM,ST" />
          <small>GK, CB, LB, RB, CDM, CM, CAM, LW, RW, ST</small>
        </label>
        <label>
          Shirt number
          <input
            name="jersey"
            type="number"
            min="0"
            max="99"
            defaultValue={player?.jersey ?? ''}
            placeholder="Not provided"
          />
        </label>
        <label>
          Dominant foot
          <select name="dominant_foot" defaultValue={player?.dominant_foot ?? ''}>
            <option value="">Not provided</option>
            {['Right', 'Left', 'Both'].map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        </label>
        <label>
          Age group
          <select name="age_group" defaultValue={player?.age_group ?? ''}>
            <option value="">Not provided</option>
            {['18–24', '25–34', '35–44', '45+'].map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        </label>
        <label>
          Self-rating · 1–10
          <input
            name="skill"
            type="number"
            min="1"
            max="10"
            step="0.1"
            defaultValue={player?.skill ?? ''}
            placeholder="Unrated"
          />
        </label>
        <label>
          Current availability
          <select name="availability" defaultValue={player?.availability ?? ''}>
            <option value="">Not provided</option>
            <option value="available">Available</option>
            <option value="injured">Recovering from injury</option>
            <option value="away">Away / taking a break</option>
          </select>
        </label>
      </div>
      <label>
        Preferred playing times
        <input name="preferred_times" defaultValue={player?.preferred_times ?? ''} maxLength={200} />
      </label>
      <label>
        Contact preference
        <input
          name="contact_preference"
          defaultValue={player?.contact_preference || 'Messenger'}
          maxLength={80}
        />
      </label>
      <label>
        Photo URL · optional
        <input
          name="photo_url"
          type="url"
          placeholder="https://…"
          defaultValue={player?.photo_url}
          maxLength={500}
        />
      </label>
      <label>
        Injury / absence note
        <textarea name="injury_note" defaultValue={player?.injury_note} rows={2} maxLength={300} />
        <small>Visible to signed-in club members. Share only what you’re comfortable with.</small>
      </label>
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      <div className="modal-actions">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" busy={mutation.isPending}>
          <Check size={16} />
          {player ? 'Save profile' : 'Add player'}
        </Button>
      </div>
    </form>
  )
}

export function Roster({ user }: { user: User }) {
  const club = useClub(),
    [query, setQuery] = useState(''),
    [team, setTeam] = useState('all'),
    [add, setAdd] = useState(false)
  if (club.loading) return <Loading />
  if (club.error) return <ErrorState error={club.error} />
  const players = club.players.filter(
    (p) =>
      matchesTeam(p.team_id, team) &&
      `${p.name} ${p.nickname} ${p.positions}`.toLowerCase().includes(query.toLowerCase()),
  )
  return (
    <>
      <PageHeading
        eyebrow="FAMILIAR FACES. PROPER FOOTBALL."
        title="Meet the squad."
        description={`${club.players.length} players. Two teams. Everyone brings something to the pitch.`}
        action={
          <>
            <a className="btn btn-secondary" href="/api/v1/export/players" download>
              <Download size={16} />
              Export roster
            </a>
            {user.role === 'admin' && (
              <Button onClick={() => setAdd(true)}>
                <Plus size={16} />
                Add player
              </Button>
            )}
          </>
        }
      />
      <div className="toolbar">
        <div className="tabs">
          {[
            ['all', 'Everyone'],
            ['1', 'Old Gentlemen'],
            ['2', 'Young Boys'],
            ['unassigned', 'Unassigned'],
          ].map(([v, label]) => (
            <button className={team === v ? 'active' : ''} key={v} onClick={() => setTeam(v)}>
              {label}
            </button>
          ))}
        </div>
        <div className="search-field">
          <Search size={17} />
          <input
            placeholder="Find a player…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search roster"
          />
        </div>
      </div>
      <div className="roster-grid">
        {players.map((p) => {
          const stats = club.stats?.players.find((s) => s.player_id === p.id)
          return (
            <Link key={p.id} to={`/players/${p.id}`} className={`card player-card team-${p.team_id}`}>
              <div className="player-card-top">
                <Badge tone={teamTone(p.team_id)}>{teamName(p.team_id)}</Badge>
                <span className="shirt-number">
                  {p.jersey === null ? '—' : String(p.jersey).padStart(2, '0')}
                </span>
              </div>
              <Avatar player={p} size="lg" />
              <div className="player-card-name">
                <h3>{p.name}</h3>
                {p.is_captain && <Crown size={15} className="gold-text" />}
              </div>
              <p>
                {p.nickname && (
                  <>
                    “{p.nickname}” <span>·</span>
                  </>
                )}{' '}
                {p.positions?.replaceAll(',', ' / ') || 'Not provided'}
              </p>
              <div className="player-card-stats">
                <div>
                  <strong>{stats?.games || 0}</strong>
                  <span>GAMES</span>
                </div>
                <div>
                  <strong>{stats?.goals || 0}</strong>
                  <span>GOALS</span>
                </div>
                <div>
                  <strong>{stats?.rating?.toFixed(1) || '—'}</strong>
                  <span>RATING</span>
                </div>
              </div>
              <div className="player-card-bottom">
                <span className={p.availability === 'available' ? 'positive' : 'gold-text'}>
                  {p.availability === 'available' ? (
                    <>
                      <span className="status-dot" />
                      Ready to play
                    </>
                  ) : (
                    <>
                      <HeartPulse size={14} />
                      {p.availability === 'injured'
                        ? 'On the mend'
                        : p.availability === 'away'
                          ? 'Away for now'
                          : 'Availability unknown'}
                    </>
                  )}
                </span>
                <ArrowRight size={16} />
              </div>
            </Link>
          )
        })}
      </div>
      {!players.length && (
        <EmptyState title="No players found" description="Try another name, position, or team." />
      )}
      <Modal
        open={add}
        onOpenChange={setAdd}
        title="A new face in the squad"
        description="Add a roster profile. Invite this player from Club settings to connect an account to this profile."
        wide
      >
        <ProfileForm onDone={() => setAdd(false)} onCancel={() => setAdd(false)} />
      </Modal>
    </>
  )
}

export function PlayerProfile({ user }: { user: User }) {
  const { id } = useParams(),
    [edit, setEdit] = useState(false),
    [assign, setAssign] = useState(false)
  const query = useQuery({ queryKey: ['player', id], queryFn: () => api<PlayerDetail>(`/players/${id}`) })
  if (query.isPending) return <Loading />
  if (query.error) return <ErrorState error={query.error} />
  const p = query.data,
    s = p.stats
  const achievements = [
    s.goals >= 10 && { icon: <Target />, title: 'Double figures', desc: '10+ career goals' },
    s.games >= 10 && { icon: <Shield />, title: 'Club regular', desc: '10+ appearances' },
    s.attendance >= 85 &&
      s.games >= 5 && { icon: <Award />, title: 'Iron Man', desc: '85%+ attendance, 5+ games' },
    s.rating && s.rating >= 8 && { icon: <Star />, title: 'Class act', desc: '8.0+ average match rating' },
  ].filter(Boolean) as { icon: React.ReactNode; title: string; desc: string }[]
  return (
    <>
      <Link to="/players" className="back-link">
        <ArrowLeft size={16} />
        Back to the squad
      </Link>
      <section className={`card profile-hero team-${p.team_id}`}>
        <Avatar player={p} size="xl" />
        <div>
          <Badge tone={teamTone(p.team_id)}>
            {teamName(p.team_id)} {p.is_captain && <Crown size={12} />}
          </Badge>
          <h1>{p.name}</h1>
          <p>
            {p.nickname && (
              <>
                “{p.nickname}” <span>·</span>
              </>
            )}{' '}
            {p.jersey !== null && (
              <>
                #{p.jersey} <span>·</span>
              </>
            )}{' '}
            {p.positions?.replaceAll(',', ' / ') || 'Not provided'}
          </p>
        </div>
        {(user.player.id === p.id || user.role === 'admin') && (
          <Button variant="secondary" onClick={() => setEdit(true)}>
            <Edit3 size={16} />
            Edit profile
          </Button>
        )}
      </section>
      {(user.role === 'captain' || user.role === 'admin') && (
        <Button variant="secondary" onClick={() => setAssign(true)}>
          Assign primary team
        </Button>
      )}
      <Modal
        open={assign}
        onOpenChange={setAssign}
        title="Assign primary team"
        description="A primary team does not change which side this player represented in earlier games."
      >
        <TeamAssignmentForm player={p} onDone={() => setAssign(false)} />
      </Modal>
      <div className="stats-grid profile-stats">
        <StatCard
          label="Career appearances"
          value={s.games}
          icon={<CalendarDays size={19} />}
          sub={`${s.attendance}% club attendance`}
        />
        <StatCard
          label="Goals"
          value={s.goals}
          icon={<Target size={19} />}
          sub={`${s.assists} assists for the squad`}
        />
        <StatCard
          label="Win rate"
          value={`${s.win_rate}%`}
          icon={<Trophy size={19} />}
          sub={`${s.wins} wins · ${s.draws} draws`}
        />
        <StatCard
          label="Average rating"
          value={s.rating?.toFixed(1) || '—'}
          icon={<Star size={19} />}
          sub="Rated by the people on the pitch"
          accent
        />
      </div>
      <div className="profile-columns">
        <section className="card padded-card">
          <h2>The player behind the number</h2>
          <dl className="profile-facts">
            <div>
              <dt>
                <Footprints size={16} />
                Dominant foot
              </dt>
              <dd>{p.dominant_foot || 'Not provided'}</dd>
            </div>
            <div>
              <dt>Age group</dt>
              <dd>{p.age_group || 'Not provided'}</dd>
            </div>
            <div>
              <dt>Self-rating</dt>
              <dd>{p.skill === null ? 'Unrated' : `${p.skill} / 10`}</dd>
            </div>
            <div>
              <dt>Preferred times</dt>
              <dd>{p.preferred_times || 'Not provided'}</dd>
            </div>
            <div>
              <dt>Contact preference</dt>
              <dd>{p.contact_preference}</dd>
            </div>
            <div>
              <dt>Availability</dt>
              <dd>
                <Badge tone={p.availability === 'available' ? 'green' : p.availability ? 'gold' : 'gray'}>
                  {p.availability || 'Not provided'}
                </Badge>
              </dd>
            </div>
            <div>
              <dt>RSVP reliability</dt>
              <dd>{s.reliability === null ? 'No check-ins yet' : `${s.reliability}%`}</dd>
            </div>
            <div>
              <dt>Clean sheets</dt>
              <dd>{s.clean_sheets}</dd>
            </div>
          </dl>
          {p.injury_note && (
            <div className="injury-note">
              <HeartPulse size={18} />
              <p>{p.injury_note}</p>
            </div>
          )}
          <div className="profile-form">
            <span>LAST FIVE GAMES</span>
            <FormGuide form={s.form} />
          </div>
        </section>
        <div>
          <section className="card padded-card">
            <h2>A little well-earned recognition</h2>
            <div className="achievement-list">
              {achievements.length ? (
                achievements.map((a) => (
                  <div key={a.title}>
                    <span>{a.icon}</span>
                    <div>
                      <strong>{a.title}</strong>
                      <p>{a.desc}</p>
                    </div>
                  </div>
                ))
              ) : (
                <p className="muted">Keep playing. Your achievements will appear here.</p>
              )}
            </div>
          </section>
          <section className="card padded-card recent-player-games">
            <h2>Recent appearances</h2>
            {p.matches.length ? (
              p.matches.slice(0, 5).map((m) => (
                <Link to={`/matches/${m.id}`} key={m.id}>
                  <CalendarDays size={17} />
                  <div>
                    <strong>{m.title}</strong>
                    <span>{matchDate(m.starts_at)}</span>
                  </div>
                  <b>
                    {m.home_score} – {m.away_score}
                  </b>
                  <ArrowRight size={16} />
                </Link>
              ))
            ) : (
              <p className="muted">Your first appearance is waiting.</p>
            )}
          </section>
        </div>
      </div>
      <Modal
        open={edit}
        onOpenChange={setEdit}
        title="Make it your profile"
        description="Your teammates would like to know."
        wide
      >
        <ProfileForm player={p} onDone={() => setEdit(false)} onCancel={() => setEdit(false)} />
      </Modal>
    </>
  )
}

function TeamAssignmentForm({ player, onDone }: { player: Player; onDone: () => void }) {
  const [team, setTeam] = useState(player.team_id?.toString() ?? '')
  const mutation = useMutation({
    mutationFn: () =>
      send(`/players/${player.id}/team`, { team_id: team === '' ? null : Number(team) }, 'PATCH'),
    onSuccess: () => {
      refreshClub()
      toast.success('Primary team updated')
      onDone()
    },
    onError: (e: Error) => toast.error(e.message),
  })
  return (
    <form
      className="form-stack"
      onSubmit={(e) => {
        e.preventDefault()
        mutation.mutate()
      }}
    >
      <label>
        Primary team
        <select value={team} onChange={(e) => setTeam(e.target.value)}>
          <option value="">Unassigned</option>
          <option value="1">Old Gentlemen</option>
          <option value="2">Young Boys</option>
        </select>
      </label>
      <Button type="submit" busy={mutation.isPending}>
        Save team
      </Button>
    </form>
  )
}
