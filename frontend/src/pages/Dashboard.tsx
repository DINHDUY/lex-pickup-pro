import { useState } from 'react'
import { Link } from 'react-router-dom'
import { format } from 'date-fns'
import {
  ArrowDownToLine,
  ArrowRight,
  CalendarDays,
  Check,
  ChevronRight,
  Clock3,
  Flame,
  MapPin,
  MessageCircle,
  Plus,
  Shield,
  Sparkles,
  Target,
  TrendingUp,
  Trophy,
  Users,
} from 'lucide-react'
import { useClub } from '../api'
import type { User } from '../types'
import { teamName, completedMatches, matchDate, matchTime, nextMatches, relativeDay, sideName } from '../lib'
import {
  Avatar,
  Badge,
  Button,
  EmptyState,
  ErrorState,
  FormGuide,
  Loading,
  PageHeading,
  RSVPButtons,
  SectionHeading,
  StatCard,
  TeamCrest,
} from '../components/ui'
import { CreateMatch } from '../components/CreateMatch'
import { ShareDialog } from '../components/ShareDialog'

export function Dashboard({ user }: { user: User }) {
  const club = useClub(),
    [create, setCreate] = useState(false),
    [share, setShare] = useState(false)
  if (club.loading) return <Loading />
  if (club.error) return <ErrorState error={club.error} />
  const stats = club.stats!,
    next = nextMatches(club.matches)[0],
    recent = completedMatches(club.matches),
    leader = stats.players[0]
  const myStats = stats.players.find((p) => p.player_id === user.player.id)
  const totalAttendance = stats.players.reduce((sum, p) => sum + p.games, 0)
  return (
    <>
      <PageHeading
        eyebrow="LET’S MAKE IT A GOOD ONE"
        title={`Hey ${user.player.name.split(' ')[0]}, welcome back`}
        description="A little friendly rivalry. A whole lot of good football."
        action={
          <>
            <span className="today-label">
              <CalendarDays size={15} />
              {format(new Date(), 'EEE, MMM d, yyyy')}
            </span>
            {user.role !== 'player' && (
              <Button onClick={() => setCreate(true)}>
                <Plus size={17} />
                Schedule game
              </Button>
            )}
          </>
        }
      />
      <div className="dashboard-feature-row">
        <section className="next-game-card">
          <div className="hero-pitch-lines" aria-hidden="true">
            <div />
            <span />
          </div>
          <div className="hero-top">
            <span className="hero-label">
              <span /> NEXT UP ON THE PITCH
            </span>
            {next && (
              <span className="hero-format">
                {next.capacity / 2} A SIDE <span>·</span>{' '}
                {next.kind === 'mixed' ? 'MIXED GAME' : 'CLUB FRIENDLY'}
              </span>
            )}
          </div>
          {next ? (
            <>
              <div className="hero-teams">
                <div className="hero-team">
                  <TeamCrest team={1} size={70} />
                  <h2>{sideName(next, 'home')}</h2>
                  <span>
                    {next.kind === 'classic' ? 'Experience never gets old.' : 'One club. Fresh combinations.'}
                  </span>
                </div>
                <div className="hero-vs">
                  <span>VS</span>
                  <small>THE WEEKLY RITUAL</small>
                </div>
                <div className="hero-team">
                  <TeamCrest team={2} size={70} />
                  <h2>{sideName(next, 'away')}</h2>
                  <span>
                    {next.kind === 'classic' ? 'Young legs. Big ambitions.' : 'Balanced for a better game.'}
                  </span>
                </div>
              </div>
              <div className="hero-game-info">
                <span>
                  <CalendarDays size={16} />
                  {matchDate(next.starts_at)}
                </span>
                <span>
                  <Clock3 size={16} />
                  {matchTime(next.starts_at)}
                </span>
                <span>
                  <MapPin size={16} />
                  {next.pitch.split(' · ')[0]}
                </span>
              </div>
              <div className="hero-bottom">
                <span>
                  <span className="hero-ball">⚽</span> Same pitch. New stories.
                </span>
                <Link to={`/matches/${next.id}`}>
                  Match details <ArrowRight size={16} />
                </Link>
              </div>
            </>
          ) : (
            <div className="hero-empty">
              <h2>The next chapter is yours.</h2>
              <p>Schedule the next game and get the squad together.</p>
              <Link to="/schedule" className="btn btn-secondary">
                Open schedule <ArrowRight size={16} />
              </Link>
            </div>
          )}
        </section>
        <section className="card checkin-card">
          <div className="checkin-heading">
            <span className="checkin-icon">
              <CalendarDays size={21} />
            </span>
            <Badge tone="gray">{next ? relativeDay(next.starts_at) : 'Your club'}</Badge>
          </div>
          <h2>{next ? 'See you on the pitch?' : 'Ready when you are.'}</h2>
          <p>{next ? 'A quick check-in helps us get game-ready.' : 'Your next game will appear here.'}</p>
          {next && (
            <>
              <div className="attendance-count">
                <strong>
                  {next.going}
                  <span> / {next.capacity}</span>
                </strong>
                <span>players confirmed</span>
              </div>
              <div className="progress-track">
                <span style={{ width: `${Math.min(100, (next.going / next.capacity) * 100)}%` }} />
              </div>
              <div className="attendance-people">
                <div className="avatar-stack">
                  {club.players
                    .filter((p) => next.going_player_ids.includes(p.id))
                    .slice(0, 4)
                    .map((p) => (
                      <Avatar key={p.id} player={p} size="xs" />
                    ))}
                </div>
                <span>
                  {next.maybe} maybe <span>·</span> {Math.max(0, next.capacity - next.going)} spots open
                </span>
              </div>
              <RSVPButtons match={next} compact />
              <button className="checkin-share" onClick={() => setShare(true)}>
                <MessageCircle size={15} />
                Share to Messenger
                <ArrowRight size={14} />
              </button>
            </>
          )}
        </section>
      </div>
      <div className="stats-grid">
        <StatCard
          label="Club members"
          value={club.players.length}
          icon={<Users size={19} />}
          sub={
            <>
              <span className="positive">
                <span className="status-dot" />
                Two teams.
              </span>{' '}
              One community.
            </>
          }
        />
        <StatCard
          label="Games this season"
          value={stats.matches_played}
          icon={<CalendarDays size={19} />}
          sub={
            <>
              <span className="positive">
                <Check size={13} />
                {recent.filter((m) => m.kind === 'classic').length} club derbies
              </span>
              <span>in the books</span>
            </>
          }
        />
        <StatCard
          label="Goals & good times"
          value={stats.total_goals}
          icon={<Target size={19} />}
          sub={
            <>
              <span className="positive">
                <TrendingUp size={13} />
                {stats.matches_played ? (stats.total_goals / stats.matches_played).toFixed(1) : '0'}
              </span>{' '}
              goals per game
            </>
          }
        />
        <StatCard
          label="Your appearances"
          value={myStats?.games || 0}
          icon={<Flame size={19} />}
          sub={
            <>
              <span className="positive">{myStats?.win_rate || 0}% win rate</span>
              <span>Keep showing up.</span>
            </>
          }
          accent
        />
      </div>
      <div className="dashboard-middle">
        <section className="card results-card">
          <SectionHeading title="Last time on the pitch" to="/history" link="Match history" />
          {recent.length ? (
            <>
              <div className="last-result-meta">
                <Badge tone="gray">FULL TIME</Badge>
                <span>
                  {matchDate(recent[0].starts_at)} <span>·</span>{' '}
                  {recent[0].kind === 'mixed' ? 'Mixed sides' : 'Club friendly'}
                </span>
              </div>
              <Link className="last-result" to={`/matches/${recent[0].id}`}>
                <div>
                  <TeamCrest team={1} size={42} />
                  <strong>{sideName(recent[0], 'home')}</strong>
                </div>
                <div className="result-score">
                  <strong>
                    {recent[0].home_score}
                    <span>:</span>
                    {recent[0].away_score}
                  </strong>
                  <span>
                    {recent[0].home_score === recent[0].away_score
                      ? 'Honors even'
                      : `${sideName(recent[0], recent[0].home_score > recent[0].away_score ? 'home' : 'away')} win`}
                  </span>
                </div>
                <div>
                  <TeamCrest team={2} size={42} />
                  <strong>{sideName(recent[0], 'away')}</strong>
                </div>
              </Link>
              <div className="result-footer">
                <span>
                  <Sparkles size={15} />
                  Another one for the club scrapbook.
                </span>
                <Link to={`/matches/${recent[0].id}`}>
                  View report <ChevronRight size={15} />
                </Link>
              </div>
            </>
          ) : (
            <EmptyState title="The story starts here" description="Your first result will live here." />
          )}
        </section>
        <section className="card rivalry-card">
          <SectionHeading title="A friendly rivalry" to="/teams" link="Our teams" />
          <div className="rivalry-label">SEASON HEAD-TO-HEAD</div>
          <div className="rivalry-numbers">
            <div>
              <strong>{stats.teams[0]?.wins || 0}</strong>
              <span>Old Gentlemen</span>
            </div>
            <div className="draw-number">
              <strong>{stats.teams[0]?.draws || 0}</strong>
              <span>Draws</span>
            </div>
            <div>
              <strong>{stats.teams[1]?.wins || 0}</strong>
              <span>Young Boys</span>
            </div>
          </div>
          <div className="rivalry-bar">
            <span style={{ flex: stats.teams[0]?.wins || 0.1 }} />
            <span style={{ flex: stats.teams[0]?.draws || 0.1 }} />
            <span style={{ flex: stats.teams[1]?.wins || 0.1 }} />
          </div>
          <div className="rivalry-form">
            <span>Recent form</span>
            <FormGuide form={stats.teams[0]?.form || []} />
            <FormGuide form={stats.teams[1]?.form || []} />
          </div>
        </section>
      </div>
      <div className="dashboard-lower">
        <section className="card leaders-card">
          <SectionHeading title="Making their mark" to="/analytics" link="All statistics" />
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>PLAYER</th>
                  <th>GP</th>
                  <th>GOALS</th>
                  <th>ASSISTS</th>
                  <th>RATING</th>
                </tr>
              </thead>
              <tbody>
                {stats.players.slice(0, 5).map((p, i) => (
                  <tr key={p.player_id}>
                    <td>
                      <span className={i === 0 ? 'rank-first' : 'muted'}>
                        {i === 0 ? <Trophy size={16} /> : String(i + 1).padStart(2, '0')}
                      </span>
                    </td>
                    <td>
                      <Link className="player-cell" to={`/players/${p.player_id}`}>
                        <Avatar player={p} size="sm" />
                        <span>
                          <strong>{p.name}</strong>
                          <small>{teamName(p.team_id)}</small>
                        </span>
                      </Link>
                    </td>
                    <td>{p.games}</td>
                    <td className="goals-cell">{p.goals}</td>
                    <td>{p.assists}</td>
                    <td>
                      <span className="rating-pill">{p.rating?.toFixed(1) || '—'}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="table-footer">
            <span>
              <Trophy size={14} />
              {leader?.name.split(' ')[0] || 'Your next star'} leads the Golden Boot race
            </span>
            <span>{new Date().getFullYear()} season</span>
          </div>
        </section>
        <section className="card notice-card">
          <SectionHeading title="Around the club" aside={<span className="notice-dot" />} />
          {club.notes[0] && (
            <div className="club-notice">
              <span className="note-eyebrow">
                <MessageCircle size={14} />
                FROM THE CLUBHOUSE
              </span>
              <h3>{club.notes[0].title}</h3>
              <p>{club.notes[0].body}</p>
              <Link to="/club" className="text-link">
                Club noticeboard
                <ArrowRight size={14} />
              </Link>
            </div>
          )}
          <div className="community-note">
            <span>
              <Shield size={20} />
            </span>
            <div>
              <strong>{totalAttendance} shared appearances.</strong>
              <p>The best part? We’re just getting started.</p>
            </div>
          </div>
        </section>
      </div>
      <div className="dashboard-bottom-note">
        <span>Here for the football. Staying for the people.</span>
        <a href="/api/v1/export/players" download>
          <ArrowDownToLine size={14} />
          Export season stats
        </a>
      </div>
      <CreateMatch open={create} onOpenChange={setCreate} />
      {next && <ShareDialog open={share} onOpenChange={setShare} match={next} />}
    </>
  )
}
