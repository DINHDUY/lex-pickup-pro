import { useEffect, useState, type FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Activity } from 'lucide-react'
import { api, ApiError, queryClient, send } from '../api'
import { Avatar, Button, ErrorState, Loading, Modal } from '../components/ui'
import type { User } from '../types'

export type Onboarding = {
  name: string
  email: string
  expires_at: string
  status: 'selection' | 'link_required' | 'completed'
  invited_player_id: number | null
  completed_player_id: number | null
}
type Candidate = {
  id: number
  name: string
  nickname: string
  photo_url: string
  team_id: number | null
  team_name: string
}

export function ClaimProfile({ session }: { session: Onboarding | null }) {
  const navigate = useNavigate()
  const [input, setInput] = useState('')
  const [search, setSearch] = useState('')
  const [offset, setOffset] = useState(0)
  const [selected, setSelected] = useState<Candidate | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [expired, setExpired] = useState(false)
  const [help, setHelp] = useState(false)
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearch(input)
      setOffset(0)
    }, 250)
    return () => window.clearTimeout(timer)
  }, [input])
  const candidates = useQuery({
    queryKey: ['claim-players', search, offset],
    queryFn: () =>
      api<{ players: Candidate[]; total: number }>(
        `/auth/onboarding/players?${new URLSearchParams({ search, offset: String(offset) })}`,
      ),
    enabled: session?.status === 'selection' && !expired,
    staleTime: 0,
  })
  const unavailable =
    expired || !session || (candidates.error instanceof ApiError && candidates.error.status === 401)

  async function finish(path: string, data: unknown) {
    setBusy(true)
    setError('')
    try {
      const user = await send<User>(path, data)
      queryClient.clear()
      queryClient.setQueryData(['me'], user)
      navigate('/', { replace: true })
    } catch (e) {
      setError((e as Error).message)
      if (e instanceof ApiError && e.status === 409) {
        setSelected(null)
        await queryClient.invalidateQueries({ queryKey: ['claim-players'] })
        await queryClient.invalidateQueries({ queryKey: ['onboarding'] })
      }
      if (e instanceof ApiError && e.status === 401 && path.endsWith('/claim')) setExpired(true)
    } finally {
      setBusy(false)
    }
  }
  async function cancel() {
    setBusy(true)
    try {
      await send('/auth/onboarding/cancel')
      queryClient.clear()
      queryClient.setQueryData(['me'], null)
      navigate('/login', { replace: true })
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  function link(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    void finish('/auth/onboarding/link', { password: new FormData(e.currentTarget).get('password') })
  }
  return (
    <main className="claim-page">
      <section className="claim-panel" aria-labelledby="claim-title">
        <div className="claim-brand">
          <Activity aria-hidden="true" /> lexpickup <strong>PRO</strong>
        </div>
        {unavailable ? (
          <>
            <h1 id="claim-title">Sign in to choose your profile</h1>
            <p>Your Facebook sign-in is missing or has expired. Sign in again to continue.</p>
            <a className="btn btn-primary" href="/api/v1/auth/facebook/login">
              Continue with Facebook
            </a>
            <a href="/login">Back to sign in</a>
          </>
        ) : (
          <>
            <span className="eyebrow">WELCOME TO THE CLUB</span>
            <h1 id="claim-title">
              {session.status === 'link_required'
                ? 'Connect your existing account'
                : session.status === 'completed'
                  ? 'Your profile is connected'
                  : 'Choose your player profile'}
            </h1>
            <p>
              Signed in with Facebook as <strong>{session.name}</strong>.
            </p>
            <p className="claim-email">
              Login email: <strong>{session.email}</strong>
            </p>
            {session.status === 'link_required' ? (
              <form className="form-stack" onSubmit={link}>
                <p>
                  You already have an account with this email. Confirm its password to connect Facebook and
                  keep your profile and access.
                </p>
                <label>
                  Existing account password
                  <input
                    name="password"
                    type="password"
                    autoComplete="current-password"
                    required
                    maxLength={128}
                  />
                </label>
                <Button busy={busy} type="submit">
                  Connect Facebook
                </Button>
              </form>
            ) : session.status === 'completed' ? (
              <Button
                busy={busy}
                onClick={() =>
                  void finish('/auth/onboarding/claim', { player_id: session.completed_player_id })
                }
              >
                Enter the clubhouse
              </Button>
            ) : (
              <>
                <p>
                  Choose any unclaimed profile below. Your team, match history, and statistics will stay with
                  it.
                </p>
                <label className="claim-search">
                  Search profiles
                  <input
                    type="search"
                    value={input}
                    maxLength={80}
                    placeholder="Name or nickname"
                    onChange={(e) => setInput(e.target.value)}
                  />
                </label>
                {candidates.isPending ? (
                  <Loading />
                ) : candidates.error ? (
                  <ErrorState error={candidates.error} />
                ) : (
                  <>
                    <p role="status">
                      {candidates.data.total} unclaimed {candidates.data.total === 1 ? 'profile' : 'profiles'}
                    </p>
                    {candidates.data.players.length === 0 && (
                      <p>No profiles found. Try another name or ask a club administrator for help.</p>
                    )}
                    <div className="claim-grid">
                      {candidates.data.players.map((player) => (
                        <button
                          key={player.id}
                          type="button"
                          className="claim-candidate"
                          disabled={busy}
                          onClick={() => {
                            setSelected(player)
                            setError('')
                          }}
                          aria-label={`Select ${player.name}, ${player.team_name}, profile ${player.id}`}
                        >
                          <Avatar player={player} />
                          <span>
                            <strong>{player.name}</strong>
                            {player.nickname && <span>{player.nickname}</span>}
                            <small>
                              {player.team_name} · Profile #{player.id}
                            </small>
                          </span>
                        </button>
                      ))}
                    </div>
                    {candidates.data.total > 20 && (
                      <nav className="claim-actions" aria-label="Profile pages">
                        <Button
                          variant="secondary"
                          disabled={offset === 0}
                          onClick={() => setOffset(offset - 20)}
                        >
                          Previous
                        </Button>
                        <span>Page {Math.floor(offset / 20) + 1}</span>
                        <Button
                          variant="secondary"
                          disabled={offset + 20 >= candidates.data.total}
                          onClick={() => setOffset(offset + 20)}
                        >
                          Next
                        </Button>
                      </nav>
                    )}
                  </>
                )}
              </>
            )}
            {error && !selected && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
            <div className="claim-actions">
              <Button variant="ghost" onClick={() => setHelp(!help)}>
                My profile is missing or already claimed
              </Button>
              <Button variant="secondary" busy={busy} onClick={() => void cancel()}>
                Cancel
              </Button>
            </div>
            {help && (
              <p role="status">
                Ask a club administrator to add your roster profile, resolve an existing claim, or help you
                access your existing account.
              </p>
            )}
          </>
        )}
        <Modal
          open={!!selected && !unavailable}
          onOpenChange={(open) => {
            if (!open && !busy) setSelected(null)
          }}
          title="Confirm your profile"
          description="Connect your Facebook login to this existing player."
        >
          {selected && (
            <div className="form-stack">
              <strong>{selected.name}</strong>
              <span>
                {selected.team_name} · Profile #{selected.id}
              </span>
              <p>
                Connect this profile to <strong>{session?.email}</strong>? Its existing history and statistics
                will be yours when you sign in.
              </p>
              {error && (
                <p className="form-error" role="alert">
                  {error}
                </p>
              )}
              <Button
                busy={busy}
                onClick={() => void finish('/auth/onboarding/claim', { player_id: selected.id })}
              >
                This is my profile
              </Button>
              <Button variant="secondary" disabled={busy} onClick={() => setSelected(null)}>
                Choose another profile
              </Button>
            </div>
          )}
        </Modal>
      </section>
    </main>
  )
}
