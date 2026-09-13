import * as Dialog from '@radix-ui/react-dialog'
import { ArrowRight, Check, CheckCircle2, CircleHelp, Loader2, RefreshCw, Shield, X } from 'lucide-react'
import { useMutation } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { useState, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { refreshClub, send } from '../api'
import { cn, initials, teamName } from '../lib'
import type { Match, Player, RSVPStatus } from '../types'

export function Button({
  className,
  variant = 'primary',
  busy,
  children,
  disabled,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  busy?: boolean
}) {
  return (
    <button className={cn('btn', `btn-${variant}`, className)} disabled={disabled || busy} {...props}>
      {busy && <Loader2 size={16} className="spin" />}
      {children}
    </button>
  )
}
export function Modal({
  open,
  onOpenChange,
  title,
  description,
  children,
  wide = false,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: string
  children: ReactNode
  wide?: boolean
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="modal-overlay" />
        <Dialog.Content className={cn('modal-content', wide && 'modal-wide')}>
          <div className="modal-heading">
            <div>
              <Dialog.Title>{title}</Dialog.Title>
              <Dialog.Description className={description ? '' : 'sr-only'}>
                {description || title}
              </Dialog.Description>
            </div>
            <Dialog.Close className="icon-btn" aria-label="Close dialog">
              <X size={20} />
            </Dialog.Close>
          </div>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
export function Badge({
  children,
  tone = 'green',
  className,
}: {
  children: ReactNode
  tone?: 'green' | 'gold' | 'gray' | 'red'
  className?: string
}) {
  return <span className={cn('badge', `badge-${tone}`, className)}>{children}</span>
}
export function Avatar({
  player,
  size = 'md',
  className,
}: {
  player: Pick<Player, 'name' | 'team_id'> & { photo_url?: string }
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
  className?: string
}) {
  const [failed, setFailed] = useState(false)
  return (
    <span
      className={cn(
        'avatar',
        `avatar-${size}`,
        player.team_id === 2 && 'avatar-gold',
        player.team_id === null && 'avatar-neutral',
        className,
      )}
    >
      {player.photo_url && !failed ? (
        <img
          src={player.photo_url}
          alt={player.name}
          referrerPolicy="no-referrer"
          onError={() => setFailed(true)}
        />
      ) : (
        initials(player.name)
      )}
    </span>
  )
}
export function TeamCrest({
  team = 1,
  size = 48,
  className,
}: {
  team?: number
  size?: number
  className?: string
}) {
  return (
    <svg
      width={size}
      height={size * 1.12}
      viewBox="0 0 76 85"
      fill="none"
      className={cn('team-crest', className)}
      role="img"
      aria-label={`${teamName(team)} crest`}
    >
      <path
        d="M6 8 38 2 70 8v38c0 17-18 30-32 37C24 76 6 63 6 46Z"
        fill={team === 1 ? '#e8f1df' : '#faeac5'}
      />
      <path
        d="M11 12 38 7l27 5v33c0 15-15 27-27 33-12-6-27-18-27-33Z"
        stroke={team === 1 ? '#245b46' : '#906b27'}
        strokeWidth="1.5"
      />
      <path
        d="m38 17 2.1 4.2 4.6.7-3.3 3.2.8 4.6-4.2-2.2-4.2 2.2.8-4.6-3.3-3.2 4.6-.7Z"
        fill={team === 1 ? '#245b46' : '#906b27'}
      />
      <text
        x="38"
        y="52"
        textAnchor="middle"
        fontSize="23"
        fontWeight="800"
        fontFamily="Arial,sans-serif"
        fill={team === 1 ? '#245b46' : '#906b27'}
      >
        {team === 1 ? 'OG' : 'YB'}
      </text>
      <text
        x="38"
        y="65"
        textAnchor="middle"
        fontSize="6"
        letterSpacing="2"
        fontFamily="Arial,sans-serif"
        fill={team === 1 ? '#245b46' : '#906b27'}
      >
        LEX CLUB
      </text>
    </svg>
  )
}
export function FormGuide({ form }: { form: string[] }) {
  return (
    <div className="form-guide" aria-label={`Recent form: ${form.join(', ') || 'No games'}`}>
      {form.length ? (
        form.map((v, i) => (
          <span key={i} className={`form-${v.toLowerCase()}`}>
            {v}
          </span>
        ))
      ) : (
        <span className="muted">—</span>
      )}
    </div>
  )
}
export function PageHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string
  title: string
  description?: string
  action?: ReactNode
}) {
  return (
    <div className="page-heading">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {action && <div className="heading-actions">{action}</div>}
    </div>
  )
}
export function SectionHeading({
  title,
  to,
  link = 'View all',
  aside,
}: {
  title: string
  to?: string
  link?: string
  aside?: ReactNode
}) {
  return (
    <div className="section-heading">
      <h2>{title}</h2>
      {to ? (
        <Link to={to} className="text-link">
          {link}
          <ArrowRight size={14} />
        </Link>
      ) : (
        aside
      )}
    </div>
  )
}
export function Loading() {
  return (
    <div className="loading-state" role="status">
      <Loader2 className="spin" size={28} />
      <span>Getting the club ready…</span>
    </div>
  )
}
export function ErrorState({ error }: { error: Error }) {
  return (
    <div className="empty-state" role="alert">
      <CircleHelp size={32} />
      <h3>Couldn’t load the club</h3>
      <p>{error.message}</p>
      <Button variant="secondary" onClick={() => refreshClub()}>
        <RefreshCw size={16} />
        Try again
      </Button>
    </div>
  )
}
export function EmptyState({
  title,
  description,
  children,
}: {
  title: string
  description: string
  children?: ReactNode
}) {
  return (
    <div className="empty-state">
      <Shield size={32} />
      <h3>{title}</h3>
      <p>{description}</p>
      {children}
    </div>
  )
}
export function RSVPButtons({ match, compact = false }: { match: Match; compact?: boolean }) {
  const mutation = useMutation({
    mutationFn: (status: RSVPStatus) => send(`/matches/${match.id}/rsvp`, { status }, 'PUT'),
    onSuccess: () => {
      refreshClub()
      toast.success('Availability updated. Your captain is in the loop.')
    },
    onError: (e: Error) => toast.error(e.message),
  })
  return (
    <div className={cn('rsvp-buttons', compact && 'rsvp-compact')} aria-label="Your availability">
      {(
        [
          ['going', 'Going', Check],
          ['maybe', 'Maybe', CircleHelp],
          ['out', 'Not going', X],
        ] as const
      ).map(([status, label, Icon]) => (
        <button
          key={status}
          className={cn('rsvp-option', `rsvp-${status}`, match.my_rsvp === status && 'selected')}
          disabled={mutation.isPending || match.status !== 'scheduled'}
          onClick={() => mutation.mutate(status)}
          aria-pressed={match.my_rsvp === status}
        >
          {mutation.isPending && mutation.variables === status ? (
            <Loader2 size={15} className="spin" />
          ) : (
            <Icon size={15} />
          )}
          {label}
        </button>
      ))}
    </div>
  )
}
export function StatCard({
  label,
  value,
  icon,
  sub,
  accent = false,
}: {
  label: string
  value: ReactNode
  icon: ReactNode
  sub: ReactNode
  accent?: boolean
}) {
  return (
    <div className={cn('stat-card', accent && 'stat-accent')}>
      <div className="stat-top">
        <span>{label}</span>
        <span className="stat-icon">{icon}</span>
      </div>
      <strong>{value}</strong>
      <div className="stat-sub">{sub}</div>
    </div>
  )
}
export function SuccessHint({ children }: { children: ReactNode }) {
  return (
    <div className="success-hint">
      <CheckCircle2 size={16} />
      {children}
    </div>
  )
}
