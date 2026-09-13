import { useState, type FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Activity, ArrowRight, Check, ShieldCheck, Sparkles } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { api, queryClient, send } from '../api'
import type { User } from '../types'
import { Button, TeamCrest } from '../components/ui'

export function Login({ returnTo }: { returnTo: string }) {
  const inviteToken = new URLSearchParams(window.location.search).get('invite') || ''
  const [register, setRegister] = useState(!!inviteToken),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('')
  const [demoRole, setDemoRole] = useState('admin')
  const config = useQuery({
    queryKey: ['config'],
    queryFn: () =>
      api<{ demo_enabled: boolean; registration_enabled: boolean; facebook_auth_enabled: boolean }>('/config'),
  })
  const navigate = useNavigate()
  const facebookAuthEnabled = config.data?.facebook_auth_enabled ?? false
  async function authenticate(data: unknown, endpoint: string) {
    setBusy(true)
    setError('')
    try {
      const user = await send<User>(endpoint, data)
      queryClient.clear()
      queryClient.setQueryData(['me'], user)
      navigate(inviteToken || returnTo === '/login' ? '/' : returnTo)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    authenticate(
      {
        email: f.get('email'),
        password: f.get('password'),
        ...(register
          ? {
              name: inviteToken ? 'Invited player' : f.get('name'),
              team_id: inviteToken || !f.get('team_id') ? null : Number(f.get('team_id')),
              invite_code: inviteToken ? '' : f.get('invite_code'),
              invite_token: inviteToken,
            }
          : {}),
      },
      register ? '/auth/register' : '/auth/login',
    )
  }
  return (
    <div className="login-page">
      <div className="login-story">
        <div className="login-brand">
          <Activity size={28} />
          <strong>
            lex<span>pickup</span>
          </strong>
          <b>PRO</b>
        </div>
        <div className="login-story-content">
          <span className="login-pill">
            <span /> THE SATURDAY TRADITION
          </span>
          <h1>
            Good football.
            <br />
            Great company.
            <br />
            <em>One club.</em>
          </h1>
          <p>For the goals, the friendly rivalry, and the people who make you show up every week.</p>
          <div className="login-crests">
            <TeamCrest team={1} size={74} />
            <span>
              ONE CLUB.
              <br />
              TWO SIDES.
            </span>
            <TeamCrest team={2} size={74} />
          </div>
        </div>
        <span className="login-footer">
          LEXINGTON, MASSACHUSETTS <span>EST. 2019</span>
        </span>
        <div className="login-field-art" aria-hidden="true">
          <div />
          <span />
        </div>
      </div>
      <div className="login-form-side">
        <div className="login-form-inner">
          <span className="eyebrow">YOUR CLUB. YOUR GAME.</span>
          <h2>
            {register ? (inviteToken ? 'Your spot is saved.' : 'Join the squad.') : 'Back for another game?'}
          </h2>
          <p className="login-subtitle">
            {register
              ? inviteToken
                ? 'Use your invited email and choose a password to claim your roster profile.'
                : 'A familiar face. A place on the team sheet.'
              : 'Welcome to your home off the pitch.'}
          </p>
          {facebookAuthEnabled ? (
            <div className="form-stack">
              <Button
                className="login-submit"
                type="button"
                onClick={() => {
                  const fbUrl = new URL('/api/v1/auth/facebook/login', window.location.origin)
                  if (inviteToken) fbUrl.searchParams.set('invite', inviteToken)
                  window.location.href = fbUrl.toString()
                }}
              >
                Continue with Facebook
                <ArrowRight size={17} />
              </Button>
            </div>
          ) : (
            <>
              <form className="form-stack" onSubmit={submit}>
                {register && !inviteToken && (
                  <label>
                    Your name
                    <input
                      name="name"
                      placeholder="First and last name"
                      autoComplete="name"
                      required
                      minLength={2}
                      maxLength={80}
                    />
                  </label>
                )}
                <label>
                  Email address
                  <input name="email" type="email" placeholder="you@example.com" autoComplete="email" required />
                </label>
                <label>
                  Password
                  <input
                    name="password"
                    type="password"
                    placeholder={register ? 'At least 10 characters' : 'Enter your password'}
                    autoComplete={register ? 'new-password' : 'current-password'}
                    required
                    minLength={register ? 10 : 1}
                    maxLength={128}
                  />
                </label>
                {register && !inviteToken && (
                  <>
                    <label>
                      Your primary team
                      <select name="team_id">
                        <option value="">Unassigned</option>
                        <option value="1">Old Gentlemen</option>
                        <option value="2">Young Boys</option>
                      </select>
                    </label>
                    <label>
                      Club invitation code
                      <input name="invite_code" placeholder="Ask your captain" required maxLength={100} />
                    </label>
                  </>
                )}
                {error && (
                  <p className="form-error" role="alert">
                    {error}
                  </p>
                )}
                <Button className="login-submit" busy={busy} type="submit">
                  {register ? 'Create your account' : 'Sign in'}
                  <ArrowRight size={17} />
                </Button>
              </form>
              {config.data?.registration_enabled && (
                <p className="auth-switch">
                  {register ? 'Already part of the club?' : 'New to the squad?'}{' '}
                  <button
                    onClick={() => {
                      setRegister(!register)
                      setError('')
                    }}
                  >
                    {register ? 'Sign in' : 'Join the club'}
                  </button>
                </p>
              )}
              {config.data?.demo_enabled && (
                <div className="demo-box">
                  <div>
                    <Sparkles size={18} />
                    <strong>Take the clubhouse for a spin</strong>
                  </div>
                  <p>Explore a full season with 24 players and a proper rivalry.</p>
                  <div className="demo-controls">
                    <select
                      value={demoRole}
                      onChange={(e) => setDemoRole(e.target.value)}
                      aria-label="Demo account role"
                    >
                      <option value="admin">Club admin</option>
                      <option value="captain">Team captain</option>
                      <option value="player">Player</option>
                    </select>
                    <Button
                      variant="secondary"
                      busy={busy}
                      onClick={() =>
                        authenticate(
                          { email: `${demoRole}@lexpickup.club`, password: 'PickupPro2026!' },
                          '/auth/login',
                        )
                      }
                    >
                      Enter demo <ArrowRight size={15} />
                    </Button>
                  </div>
                </div>
              )}
            </>
            
          )}
          <div className="login-trust">
            <ShieldCheck size={15} />
            <span>Members only</span>
            <Check size={14} />
            <span>Built for the love of the game</span>
          </div>
        </div>
      </div>
    </div>
  )
}
