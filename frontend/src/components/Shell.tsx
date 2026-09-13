import { useEffect, useState, type ReactNode } from 'react'
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom'
import {
  Activity,
  ArrowUpRight,
  Bell,
  CalendarDays,
  CalendarCheck2,
  ChartNoAxesCombined,
  ChevronDown,
  CircleHelp,
  Download,
  History,
  House,
  LogOut,
  Menu,
  Moon,
  Search,
  Settings2,
  Shield,
  Sun,
  Users,
} from 'lucide-react'
import { useRegisterSW } from 'virtual:pwa-register/react'
import { toast } from 'sonner'
import { queryClient, send, useClub } from '../api'
import { cn, matchDate, nextMatches } from '../lib'
import type { User } from '../types'
import { Avatar, Badge, Button, Modal } from './ui'

const navigation = [
  { to: '/', name: 'Overview', icon: House },
  { to: '/schedule', name: 'Schedule', icon: CalendarDays },
  { to: '/players', name: 'Players', icon: Users },
  { to: '/teams', name: 'Our teams', icon: Shield },
  { to: '/availability', name: 'Availability', icon: CalendarCheck2 },
  { to: '/analytics', name: 'Statistics', icon: ChartNoAxesCombined },
  { to: '/history', name: 'Match history', icon: History },
]
interface InstallPrompt extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: string }>
}

export function Shell({ user, children }: { user: User; children: ReactNode }) {
  const [mobile, setMobile] = useState(false),
    [searchOpen, setSearchOpen] = useState(false),
    [search, setSearch] = useState('')
  const [notifications, setNotifications] = useState(false),
    [account, setAccount] = useState(false),
    [help, setHelp] = useState(false)
  const [dark, setDark] = useState(document.documentElement.classList.contains('dark'))
  const [install, setInstall] = useState<InstallPrompt | null>(null)
  const [installHelp, setInstallHelp] = useState(false)
  const {
    needRefresh: [needRefresh],
    updateServiceWorker,
  } = useRegisterSW()
  const club = useClub(),
    location = useLocation(),
    navigate = useNavigate()
  const current =
    navigation.find((n) => n.to === location.pathname)?.name ||
    (location.pathname.startsWith('/matches')
      ? 'Match center'
      : location.pathname.startsWith('/players/')
        ? 'Player profile'
        : 'Clubhouse')
  useEffect(() => {
    setMobile(false)
    setAccount(false)
  }, [location.pathname])
  useEffect(() => {
    const handler = (e: Event) => {
      e.preventDefault()
      setInstall(e as InstallPrompt)
    }
    const keys = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setSearchOpen((v) => !v)
      }
      if (e.key === 'Escape') setMobile(false)
    }
    window.addEventListener('beforeinstallprompt', handler)
    window.addEventListener('keydown', keys)
    return () => {
      window.removeEventListener('beforeinstallprompt', handler)
      window.removeEventListener('keydown', keys)
    }
  }, [])
  function theme() {
    const next = !dark
    setDark(next)
    document.documentElement.classList.toggle('dark', next)
    localStorage.setItem('lex-theme', next ? 'dark' : 'light')
  }
  async function logout() {
    try {
      await send('/auth/logout')
      queryClient.clear()
      queryClient.setQueryData(['me'], null)
      navigate('/login')
    } catch (e) {
      toast.error((e as Error).message)
    }
  }
  async function installApp() {
    if (!install) {
      setInstallHelp(true)
      return
    }
    await install.prompt()
    const choice = await install.userChoice
    if (choice.outcome === 'accepted') setInstall(null)
  }
  const upcoming = nextMatches(club.matches).filter((m) => !m.my_rsvp)
  const filteredPlayers = club.players
    .filter((p) => `${p.name} ${p.nickname}`.toLowerCase().includes(search.toLowerCase()))
    .slice(0, 5)
  const filteredMatches = club.matches
    .filter((m) => `${m.title} ${matchDate(m.starts_at)}`.toLowerCase().includes(search.toLowerCase()))
    .slice(0, 4)
  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link">
        Skip to content
      </a>
      {mobile && (
        <button className="sidebar-overlay" onClick={() => setMobile(false)} aria-label="Close navigation" />
      )}
      <aside className={cn('sidebar', mobile && 'sidebar-open')}>
        <Link to="/" className="brand">
          <span className="brand-mark">
            <Activity size={25} strokeWidth={2.5} />
          </span>
          <span>
            lex<span className="brand-light">pickup</span>
            <small>THE BEAUTIFUL GAME. TOGETHER.</small>
          </span>
          <span className="pro-tag">PRO</span>
        </Link>
        <div className="club-switch">
          <span className="club-icon">
            <Shield size={19} />
          </span>
          <div>
            <strong>Lexington Football Club</strong>
            <span>Est. 2019 · Lexington, MA</span>
          </div>
          <span className="club-online" />
        </div>
        <div className="nav-label">YOUR CLUB</div>
        <nav className="desktop-nav">
          {navigation.map(({ to, name, icon: Icon }) => (
            <NavLink
              end={to === '/'}
              key={to}
              to={to}
              className={({ isActive }) => cn('nav-item', isActive && 'active')}
            >
              <Icon size={19} />
              <span>{name}</span>
              {to === '/schedule' && <span className="nav-count">{nextMatches(club.matches).length}</span>}
            </NavLink>
          ))}
        </nav>
        <div className="nav-label manage-label">CLUBHOUSE</div>
        <NavLink to="/club" className={({ isActive }) => cn('nav-item', isActive && 'active')}>
          <Settings2 size={19} />
          <span>Club management</span>
        </NavLink>
        <div className="sidebar-bottom">
          <div className="club-mantra">
            <span className="tiny-ball">✦</span>
            <strong>More than a game.</strong>
            <p>
              A weekly ritual.
              <br />A proper community.
            </p>
            <div className="mantra-line" />
          </div>
          <button className="nav-item" onClick={installApp}>
            <Download size={18} />
            <span>Install the app</span>
            <ArrowUpRight size={15} />
          </button>
          <button className="nav-item" onClick={() => setHelp(true)}>
            <CircleHelp size={18} />
            <span>Help & getting started</span>
          </button>
          <div className="sidebar-user">
            <Avatar player={user.player} size="sm" />
            <div>
              <strong>{user.player.name}</strong>
              <span>
                {user.role === 'admin'
                  ? 'Club administrator'
                  : user.role === 'captain'
                    ? 'Team captain'
                    : 'Club member'}
              </span>
            </div>
            <button className="icon-btn" onClick={logout} aria-label="Sign out">
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-btn mobile-menu"
              onClick={() => setMobile((v) => !v)}
              aria-label="Open navigation"
              aria-expanded={mobile}
            >
              <Menu size={22} />
            </button>
            <span className="breadcrumb-club">Clubhouse</span>
            <span className="breadcrumb-separator">/</span>
            <strong>{current}</strong>
          </div>
          <div className="topbar-actions">
            <button
              aria-label="Search the club"
              className="search-trigger"
              onClick={() => setSearchOpen(true)}
            >
              <Search size={16} />
              <span>Search the club…</span>
              <kbd>⌘ K</kbd>
            </button>
            <button
              className="icon-btn"
              onClick={theme}
              aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
            >
              {dark ? <Sun size={19} /> : <Moon size={19} />}
            </button>
            <button
              className="icon-btn notification-button"
              onClick={() => setNotifications(true)}
              aria-label="Match reminders"
            >
              <Bell size={19} />
              {upcoming.length > 0 && <span className="notification-dot" />}
            </button>
            <div className="account-wrapper">
              <button
                className="account-button"
                aria-label="Account menu"
                aria-expanded={account}
                onClick={() => setAccount((v) => !v)}
              >
                <Avatar player={user.player} size="sm" />
                <ChevronDown size={14} />
              </button>
              {account && (
                <div className="account-menu">
                  <strong>{user.player.name}</strong>
                  <span>{user.email}</span>
                  <Link to={`/players/${user.player.id}`}>My player profile</Link>
                  <button onClick={logout}>
                    Sign out <LogOut size={15} />
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>
        {needRefresh && (
          <div className="update-banner">
            <span>A fresh version is ready.</span>
            <Button variant="secondary" onClick={() => updateServiceWorker(true)}>
              Update app
            </Button>
          </div>
        )}
        <main id="main-content" className="main-content" key={location.pathname}>
          {children}
        </main>
        <footer className="footer">
          <span>
            Lex Pickup Pro <span className="footer-dot">·</span> Good football. Great company.
          </span>
          <span>
            <span className="status-dot" /> Made for our Saturdays
          </span>
        </footer>
      </div>
      <nav className="mobile-bottom-nav">
        {navigation
          .filter((n) => ['/', '/schedule', '/players', '/analytics'].includes(n.to))
          .map(({ to, name, icon: Icon }) => (
            <NavLink end={to === '/'} key={to} to={to}>
              <Icon size={20} />
              <span>{name}</span>
            </NavLink>
          ))}
        <button onClick={() => setMobile(true)}>
          <Menu size={20} />
          <span>More</span>
        </button>
      </nav>
      <Modal
        open={searchOpen}
        onOpenChange={setSearchOpen}
        title="Find your next move"
        description="Search players and games."
      >
        <div className="search-field">
          <Search size={18} />
          <input
            autoFocus
            placeholder="A player, nickname, or game…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Search players and matches"
          />
        </div>
        <div className="search-results">
          <span className="eyebrow">PLAYERS</span>
          {filteredPlayers.map((p) => (
            <Link key={p.id} to={`/players/${p.id}`} onClick={() => setSearchOpen(false)}>
              <Avatar player={p} size="sm" />
              <span>
                {p.name}
                <small>{p.positions || 'Not provided'}</small>
              </span>
              <ArrowUpRight size={15} />
            </Link>
          ))}
          <span className="eyebrow">GAMES</span>
          {filteredMatches.map((m) => (
            <Link key={m.id} to={`/matches/${m.id}`} onClick={() => setSearchOpen(false)}>
              <CalendarDays size={22} />
              <span>
                {m.title}
                <small>{matchDate(m.starts_at)}</small>
              </span>
              <Badge tone="gray">{m.status}</Badge>
            </Link>
          ))}
          {!filteredPlayers.length && !filteredMatches.length && (
            <p className="muted">No matches. Try another name or date.</p>
          )}
        </div>
      </Modal>
      <Modal
        open={notifications}
        onOpenChange={setNotifications}
        title="Your match reminders"
        description="A quick check-in goes a long way."
      >
        <div className="search-results">
          {upcoming.length ? (
            upcoming.map((m) => (
              <Link key={m.id} to={`/matches/${m.id}`} onClick={() => setNotifications(false)}>
                <CalendarCheck2 size={24} />
                <span>
                  {m.title}
                  <small>{matchDate(m.starts_at)} · Let the captain know if you’re in.</small>
                </span>
                <ArrowUpRight size={16} />
              </Link>
            ))
          ) : (
            <div className="empty-state">
              <CalendarCheck2 size={32} />
              <h3>You’re all caught up</h3>
              <p>All upcoming games have your response.</p>
            </div>
          )}
        </div>
      </Modal>
      <Modal
        open={help}
        onOpenChange={setHelp}
        title="Welcome to your clubhouse"
        description="Everything the group chat can’t keep organized."
      >
        <div className="help-steps">
          <p>
            <strong>1. Get on the team sheet.</strong> Open the next game and choose Going, Maybe, or Not
            going. You can change your response before kickoff.
          </p>
          <p>
            <strong>2. Know the plan.</strong> Check the pitch, time, and lineup in the match center. Save the
            game to your phone calendar.
          </p>
          <p>
            <strong>3. Keep the group in the loop.</strong> Use Share to Messenger to copy a clean summary, or
            open your phone’s sharing menu.
          </p>
          <p>
            <strong>4. Make every game count.</strong> Captains record scores and goals; participants rate
            performances. Your stats update automatically.
          </p>
          <p>For account or password help, contact your club administrator through Messenger.</p>
        </div>
      </Modal>
      <Modal
        open={installHelp}
        onOpenChange={setInstallHelp}
        title="Your club, one tap away"
        description="Install Lex Pickup Pro on your phone."
      >
        <div className="help-steps">
          <p>
            <strong>iPhone or iPad:</strong> Open in Safari, tap Share, then “Add to Home Screen.”
          </p>
          <p>
            <strong>Android:</strong> Open the browser menu and choose “Install app” or “Add to Home screen.”
          </p>
          <p>
            <strong>Desktop:</strong> Look for the install icon in Chrome or Edge’s address bar.
          </p>
          <p className="muted">Installation is available on the built app over HTTPS or localhost.</p>
        </div>
      </Modal>
    </div>
  )
}
