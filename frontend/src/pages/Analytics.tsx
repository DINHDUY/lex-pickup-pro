import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  ArrowDown,
  Award,
  CalendarCheck2,
  Download,
  MessageCircle,
  Printer,
  Star,
  Target,
  Trophy,
  Users,
} from 'lucide-react'
import { api } from '../api'
import type { PlayerStats, Season, Stats } from '../types'
import { teamName, matchesTeam } from '../lib'
import {
  Avatar,
  Badge,
  Button,
  EmptyState,
  ErrorState,
  FormGuide,
  Loading,
  PageHeading,
  StatCard,
} from '../components/ui'
import { ShareDialog } from '../components/ShareDialog'

type SortKey = 'goals' | 'assists' | 'games' | 'rating' | 'win_rate' | 'attendance' | 'reliability'
export default function Analytics() {
  const [season, setSeason] = useState(''),
    [sort, setSort] = useState<SortKey>('goals'),
    [team, setTeam] = useState('all'),
    [compareA, setCompareA] = useState(''),
    [compareB, setCompareB] = useState(''),
    [share, setShare] = useState(false)
  const seasons = useQuery({ queryKey: ['seasons'], queryFn: () => api<Season[]>('/seasons') })
  const query = useQuery({
    queryKey: ['stats', season],
    queryFn: () => api<Stats>(`/stats${season ? `?season_id=${season}` : ''}`),
  })
  if (query.isPending) return <Loading />
  if (query.error) return <ErrorState error={query.error} />
  const stats = query.data,
    players = [...stats.players]
      .filter((p) => matchesTeam(p.team_id, team))
      .sort((a, b) => (b[sort] || 0) - (a[sort] || 0))
  const a = stats.players.find((p) => p.player_id === Number(compareA)) || stats.players[0],
    b = stats.players.find((p) => p.player_id === Number(compareB)) || stats.players[1]
  const avgRating = stats.players.filter((p) => p.rating !== null)
  const leaders = [
    {
      title: 'Golden Boot',
      desc: 'The one finding the net.',
      key: 'goals' as const,
      icon: <Target size={21} />,
      unit: 'goals',
    },
    {
      title: 'The Playmaker',
      desc: 'Making everyone look good.',
      key: 'assists' as const,
      icon: <Award size={21} />,
      unit: 'assists',
    },
    {
      title: 'Iron Man',
      desc: 'First name on the team sheet.',
      key: 'games' as const,
      icon: <CalendarCheck2 size={21} />,
      unit: 'games',
    },
  ]
  const shareText = `🏆 LEX PICKUP PRO · ${season ? seasons.data?.find((s) => s.id === Number(season))?.name : 'CAREER RECORDS'}\n\n${stats.matches_played} games · ${stats.total_goals} goals\n\n${leaders
    .map((l) => {
      const p = [...stats.players].sort((a, b) => b[l.key] - a[l.key])[0]
      return p ? `${l.title}: ${p.name} (${p[l.key]} ${l.unit})` : ''
    })
    .join(
      '\n',
    )}\n\nOld Gentlemen: ${stats.teams[0]?.wins || 0} derby wins\nYoung Boys: ${stats.teams[1]?.wins || 0} derby wins\n\nGood football. Great company.\n${window.location.origin}/analytics`
  const trend = stats.trend.map((t) => ({
    ...t,
    month: new Date(`${t.month}-15`).toLocaleDateString('en-US', { month: 'short' }),
  }))
  const compareKeys: { key: keyof PlayerStats; label: string; unit?: string }[] = [
    { key: 'games', label: 'Appearances' },
    { key: 'goals', label: 'Goals' },
    { key: 'assists', label: 'Assists' },
    { key: 'win_rate', label: 'Win rate', unit: '%' },
    { key: 'rating', label: 'Average rating' },
    { key: 'reliability', label: 'RSVP reliability', unit: '%' },
  ]
  return (
    <>
      <PageHeading
        eyebrow="THE NUMBERS BEHIND THE GAME"
        title="A little friendly competition."
        description="Celebrate the goals, the assists, and the people who keep showing up."
        action={
          <>
            <Button variant="secondary" onClick={() => setShare(true)}>
              <MessageCircle size={16} />
              Share season
            </Button>
            <Button variant="secondary" onClick={() => window.print()}>
              <Printer size={16} />
              Print / PDF
            </Button>
          </>
        }
      />
      <div className="analytics-season">
        <Badge>
          <span className="status-dot" />
          {season ? seasons.data?.find((s) => s.id === Number(season))?.name : 'All-time club records'}
        </Badge>
        <select value={season} onChange={(e) => setSeason(e.target.value)} aria-label="Statistics season">
          <option value="">Career · all seasons</option>
          {seasons.data?.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
      </div>
      <div className="stats-grid">
        <StatCard
          label="Games played"
          value={stats.matches_played}
          icon={<Trophy size={19} />}
          sub="Every Saturday adds to the story"
        />
        <StatCard
          label="Goals scored"
          value={stats.total_goals}
          icon={<Target size={19} />}
          sub={`${stats.matches_played ? (stats.total_goals / stats.matches_played).toFixed(1) : 0} goals per game`}
        />
        <StatCard
          label="Shared appearances"
          value={stats.players.reduce((s, p) => s + p.games, 0)}
          icon={<Users size={19} />}
          sub="Showing up is half the game"
        />
        <StatCard
          label="Average player rating"
          value={
            avgRating.length
              ? (avgRating.reduce((s, p) => s + (p.rating || 0), 0) / avgRating.length).toFixed(1)
              : '—'
          }
          icon={<Star size={19} />}
          sub="From your teammates and captains"
          accent
        />
      </div>
      <div className="award-grid">
        {leaders.map((l) => {
          const p = [...stats.players].sort((a, b) => b[l.key] - a[l.key])[0]
          return (
            <section className="card award-card" key={l.key}>
              <div className="award-heading">
                <span>{l.icon}</span>
                <div>
                  <h3>{l.title}</h3>
                  <p>{l.desc}</p>
                </div>
              </div>
              {p && p[l.key] > 0 ? (
                <Link to={`/players/${p.player_id}`}>
                  <Avatar player={p} size="md" />
                  <div>
                    <strong>{p.name}</strong>
                    <span>{teamName(p.team_id)}</span>
                  </div>
                  <b>
                    {p[l.key]}
                    <small>{l.unit}</small>
                  </b>
                </Link>
              ) : (
                <p className="muted">The race is about to begin.</p>
              )}
            </section>
          )
        })}
      </div>
      <div className="charts-grid">
        <section className="card padded-card">
          <h2>Goals keep us coming back</h2>
          <p className="muted">Club goals by month</p>
          {trend.length ? (
            <div className="chart-container">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={trend} margin={{ left: -22, right: 12, top: 15, bottom: 0 }}>
                  <defs>
                    <linearGradient id="goalFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#3c8964" stopOpacity={0.25} />
                      <stop offset="100%" stopColor="#3c8964" stopOpacity={0.01} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid vertical={false} stroke="var(--border)" strokeDasharray="4 4" />
                  <XAxis
                    dataKey="month"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: 'var(--muted)', fontSize: 11 }}
                  />
                  <YAxis
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: 'var(--muted)', fontSize: 11 }}
                    allowDecimals={false}
                  />
                  <Tooltip
                    contentStyle={{
                      background: 'var(--surface)',
                      borderColor: 'var(--border)',
                      borderRadius: 10,
                      color: 'var(--text)',
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="goals"
                    name="Goals"
                    stroke="#3c8964"
                    strokeWidth={3}
                    fill="url(#goalFill)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyState
              title="Room for a great season"
              description="The chart will grow with every completed game."
            />
          )}
        </section>
        <section className="card padded-card">
          <h2>The rivalry, in numbers</h2>
          <p className="muted">Fixed-team matches only</p>
          <div className="chart-container">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={[
                  { name: 'Wins', OG: stats.teams[0]?.wins || 0, YB: stats.teams[1]?.wins || 0 },
                  {
                    name: 'Goals for',
                    OG: stats.teams[0]?.goals_for || 0,
                    YB: stats.teams[1]?.goals_for || 0,
                  },
                  {
                    name: 'Goals against',
                    OG: stats.teams[0]?.goals_against || 0,
                    YB: stats.teams[1]?.goals_against || 0,
                  },
                ]}
                margin={{ left: -22, right: 10, top: 15 }}
              >
                <CartesianGrid vertical={false} stroke="var(--border)" strokeDasharray="4 4" />
                <XAxis
                  dataKey="name"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: 'var(--muted)', fontSize: 11 }}
                />
                <YAxis
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: 'var(--muted)', fontSize: 11 }}
                  allowDecimals={false}
                />
                <Tooltip
                  contentStyle={{
                    background: 'var(--surface)',
                    borderColor: 'var(--border)',
                    borderRadius: 10,
                    color: 'var(--text)',
                  }}
                />
                <Legend wrapperStyle={{ fontSize: 11, paddingTop: 12 }} />
                <Bar dataKey="OG" name="Old Gentlemen" fill="#397657" radius={[4, 4, 0, 0]} maxBarSize={30} />
                <Bar dataKey="YB" name="Young Boys" fill="#d5ac63" radius={[4, 4, 0, 0]} maxBarSize={30} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>
      </div>
      <section className="card leaderboard-section">
        <div className="section-heading">
          <h2>The season’s standouts</h2>
          <div className="toolbar-right">
            <select value={team} onChange={(e) => setTeam(e.target.value)} aria-label="Leaderboard team">
              <option value="all">Both teams</option>
              <option value="1">Old Gentlemen</option>
              <option value="2">Young Boys</option>
              <option value="unassigned">Unassigned</option>
            </select>
            <a className="text-link" href="/api/v1/export/players" download>
              <Download size={15} />
              Career CSV
            </a>
          </div>
        </div>
        <div className="table-scroll">
          <table className="data-table full-leaderboard">
            <thead>
              <tr>
                <th>#</th>
                <th>PLAYER</th>
                {(
                  [
                    'games',
                    'goals',
                    'assists',
                    'rating',
                    'win_rate',
                    'attendance',
                    'reliability',
                  ] as SortKey[]
                ).map((k) => (
                  <th key={k}>
                    <button onClick={() => setSort(k)} className={sort === k ? 'sorted' : ''}>
                      {k === 'win_rate' ? 'WIN %' : k.toUpperCase()}
                      {sort === k && <ArrowDown size={12} />}
                    </button>
                  </th>
                ))}
                <th>FORM</th>
              </tr>
            </thead>
            <tbody>
              {players.map((p, i) => (
                <tr key={p.player_id}>
                  <td className="muted">{i + 1}</td>
                  <td>
                    <Link to={`/players/${p.player_id}`} className="player-cell">
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
                  <td>{p.win_rate}%</td>
                  <td>{p.attendance}%</td>
                  <td>{p.reliability === null ? '—' : `${p.reliability}%`}</td>
                  <td>
                    <FormGuide form={p.form} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="table-footer">
          Attendance = completed games played / club games. Reliability = appearances / Going responses.
          Ratings are peer and organizer averages.
        </p>
      </section>
      {a && b && (
        <section className="card comparison-card">
          <div className="section-heading">
            <h2>Side by side</h2>
            <Badge tone="gray">PLAYER COMPARISON</Badge>
          </div>
          <div className="comparison-selectors">
            <label>
              First player
              <select value={compareA || a.player_id} onChange={(e) => setCompareA(e.target.value)}>
                {stats.players.map((p) => (
                  <option key={p.player_id} value={p.player_id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            <span>vs</span>
            <label>
              Second player
              <select value={compareB || b.player_id} onChange={(e) => setCompareB(e.target.value)}>
                {stats.players.map((p) => (
                  <option key={p.player_id} value={p.player_id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="comparison-avatars">
            <div>
              <Avatar player={a} size="lg" />
              <strong>{a.name}</strong>
              <small>{teamName(a.team_id)}</small>
            </div>
            <div>
              <Avatar player={b} size="lg" />
              <strong>{b.name}</strong>
              <small>{teamName(b.team_id)}</small>
            </div>
          </div>
          <div className="comparison-metrics">
            {compareKeys.map(({ key, label, unit = '' }) => (
              <div key={key}>
                <strong className={Number(a[key]) > Number(b[key]) ? 'positive' : ''}>
                  {a[key] === null ? '—' : `${a[key]}${unit}`}
                </strong>
                <span>{label}</span>
                <strong className={Number(b[key]) > Number(a[key]) ? 'positive' : ''}>
                  {b[key] === null ? '—' : `${b[key]}${unit}`}
                </strong>
              </div>
            ))}
          </div>
        </section>
      )}
      <ShareDialog
        open={share}
        onOpenChange={setShare}
        customText={shareText}
        title="A season worth sharing"
      />
    </>
  )
}
