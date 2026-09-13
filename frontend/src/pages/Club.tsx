import { useState, type FormEvent } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  BookOpen,
  Check,
  Copy,
  Download,
  MapPin,
  MessageCircle,
  Plus,
  Settings2,
  Shield,
  Trash2,
  Users,
  Wrench,
} from 'lucide-react'
import { toast } from 'sonner'
import { api, refreshClub, send, useClub } from '../api'
import { copyText, teamName } from '../lib'
import type { Member, User } from '../types'
import { Avatar, Badge, Button, ErrorState, Loading, Modal, PageHeading } from '../components/ui'

export function Club({ user }: { user: User }) {
  const club = useClub(),
    [addNote, setAddNote] = useState(false),
    [member, setMember] = useState<Member | null>(null),
    [deleteId, setDeleteId] = useState<number | null>(null)
  const [invited, setInvited] = useState<Member | null>(null),
    [inviteUrl, setInviteUrl] = useState(''),
    [inviteBusy, setInviteBusy] = useState(false),
    [newSeason, setNewSeason] = useState(false)
  const members = useQuery({
    queryKey: ['members'],
    queryFn: () => api<Member[]>('/admin/members'),
    enabled: user.role === 'admin',
  })
  const mutation = useMutation({
    mutationFn: ({ path, data, method }: { path: string; data?: unknown; method?: string }) =>
      send(path, data, method),
    onSuccess: () => {
      refreshClub()
      setAddNote(false)
      setMember(null)
      setDeleteId(null)
      setNewSeason(false)
      toast.success('Club details updated')
    },
    onError: (e: Error) => toast.error(e.message),
  })
  if (club.loading) return <Loading />
  if (club.error) return <ErrorState error={club.error} />
  function saveNote(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    mutation.mutate({ path: '/notes', data: Object.fromEntries(new FormData(e.currentTarget)) })
  }
  function saveMember(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    mutation.mutate({
      path: `/admin/members/${member?.id}`,
      method: 'PATCH',
      data: {
        team_id: f.get('team_id') === '' ? null : Number(f.get('team_id')),
        role: f.get('role'),
        active: f.get('active') === 'on',
      },
    })
  }
  async function inviteProfile(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setInviteBusy(true)
    const f = new FormData(e.currentTarget)
    try {
      const result = await send<{ url: string }>(`/admin/members/${invited?.id}/invite`, {
        email: f.get('email'),
      })
      setInviteUrl(result.url)
      toast.success('Invitation created. Share the link with this player.')
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setInviteBusy(false)
    }
  }
  async function invite() {
    try {
      await copyText(
        `⚽ You’re invited to Lexington Football Club!\n\nJoin the squad on Lex Pickup Pro to check into games, see lineups, and follow your stats.\n\n${window.location.origin}/login\n\nChoose “Join the club” and ask the captain for the current invitation code. See you on the pitch!`,
      )
      toast.success('Invitation copied. Add the club code before sharing with a new member.')
    } catch (e) {
      toast.error((e as Error).message)
    }
  }
  return (
    <>
      <PageHeading
        eyebrow="THE HOME OFF THE PITCH"
        title="A well-run club. A better Saturday."
        description="The little things that keep the football happening."
        action={
          <Button variant="secondary" onClick={invite}>
            <Copy size={16} />
            Copy club invitation
          </Button>
        }
      />
      <div className="club-overview">
        <section className="club-about">
          <Shield size={31} />
          <div>
            <h2>Lexington Football Club</h2>
            <p>Est. 2019 · Lexington, Massachusetts</p>
            <span>Two teams. One shared love of the beautiful game.</span>
          </div>
          <Badge>MEMBERS CLUB</Badge>
        </section>
      </div>
      <div className="section-heading club-notices-heading">
        <h2>The club noticeboard</h2>
        {user.role === 'admin' && (
          <Button onClick={() => setAddNote(true)}>
            <Plus size={16} />
            Add notice
          </Button>
        )}
      </div>
      <div className="notices-grid">
        {club.notes.map((note) => (
          <article className="card notice-tile" key={note.id}>
            <div>
              <span className="notice-category">
                {note.category === 'pitch' ? (
                  <MapPin size={20} />
                ) : note.category === 'equipment' ? (
                  <Wrench size={20} />
                ) : (
                  <MessageCircle size={20} />
                )}
                {note.category}
              </span>
              {user.role === 'admin' && (
                <button
                  className="icon-btn"
                  onClick={() => setDeleteId(note.id)}
                  aria-label={`Delete ${note.title}`}
                >
                  <Trash2 size={15} />
                </button>
              )}
            </div>
            <h3>{note.title}</h3>
            <p>{note.body}</p>
            <small>
              Updated{' '}
              {new Date(note.updated_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
            </small>
          </article>
        ))}
      </div>
      {user.role === 'admin' && (
        <section className="card members-section">
          <div className="section-heading">
            <h2>Club members & access</h2>
            <Badge tone="gray">
              <Users size={12} />
              {members.data?.length || 0} members
            </Badge>
          </div>
          {members.isPending ? (
            <Loading />
          ) : members.error ? (
            <ErrorState error={members.error} />
          ) : (
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>MEMBER</th>
                    <th>PRIMARY TEAM</th>
                    <th>ACCESS</th>
                    <th>STATUS</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {members.data?.map((m) => (
                    <tr key={m.id}>
                      <td>
                        <div className="player-cell">
                          <Avatar player={m} size="sm" />
                          <span>
                            <strong>{m.name}</strong>
                            <small>{m.email || 'Roster profile · no account yet'}</small>
                          </span>
                        </div>
                      </td>
                      <td>{teamName(m.team_id)}</td>
                      <td>
                        <Badge tone={m.role === 'admin' ? 'gold' : 'gray'}>{m.role}</Badge>
                      </td>
                      <td>
                        <span className={m.active ? 'positive' : 'muted'}>
                          {m.active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td>
                        {!m.has_account && m.active && (
                          <Button
                            variant="ghost"
                            onClick={() => {
                              setInvited(m)
                              setInviteUrl('')
                            }}
                          >
                            Invite
                          </Button>
                        )}
                        <Button variant="ghost" onClick={() => setMember(m)}>
                          <Settings2 size={15} />
                          Edit
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
      <div className="club-tools-grid">
        {user.role === 'admin' && (
          <section className="card padded-card">
            <span className="tool-icon">
              <Shield size={22} />
            </span>
            <h3>A fresh season. Same club.</h3>
            <p>
              Start a new season for newly scheduled games. Previous results and career records stay in the
              archive.
            </p>
            <Button variant="secondary" onClick={() => setNewSeason(true)}>
              Start a new season
            </Button>
          </section>
        )}
        <section className="card padded-card">
          <span className="tool-icon">
            <Download size={22} />
          </span>
          <h3>Your club’s records, to keep.</h3>
          <p>Download spreadsheets for season reviews or your own records.</p>
          <div className="export-links">
            <a className="btn btn-secondary" href="/api/v1/export/players" download>
              Player statistics CSV
            </a>
            <a className="btn btn-secondary" href="/api/v1/export/matches" download>
              Match archive CSV
            </a>
          </div>
        </section>
        <section className="card padded-card">
          <span className="tool-icon">
            <BookOpen size={22} />
          </span>
          <h3>Messenger is still the group chat.</h3>
          <p>
            Use Lex Pickup Pro for the plans and the numbers. Share game links, lineup announcements, and
            season summaries straight back to your people.
          </p>
          <span className="small-note">Need account help? Contact your club administrator in Messenger.</span>
        </section>
      </div>
      <Modal
        open={!!invited}
        onOpenChange={(v) => !v && setInvited(null)}
        title={`Invite ${invited?.name || 'player'}`}
        description="A single-use link connects their account to this existing roster profile."
      >
        {inviteUrl ? (
          <div className="form-stack">
            <label>
              Personal invitation link
              <input
                aria-label="Personal invitation link"
                readOnly
                value={inviteUrl}
                onFocus={(e) => e.target.select()}
              />
            </label>
            <p className="small-note">
              Valid for 7 days and only for the email you entered. Share privately with this player.
            </p>
            <Button
              onClick={async () => {
                try {
                  await copyText(inviteUrl)
                  toast.success('Invitation link copied')
                } catch (e) {
                  toast.error((e as Error).message)
                }
              }}
            >
              <Copy size={16} />
              Copy invitation link
            </Button>
          </div>
        ) : (
          <form className="form-stack" onSubmit={inviteProfile}>
            <label>
              Player’s email
              <input name="email" type="email" required placeholder="player@example.com" />
            </label>
            <Button type="submit" busy={inviteBusy}>
              Create invitation
            </Button>
          </form>
        )}
      </Modal>
      <Modal
        open={newSeason}
        onOpenChange={setNewSeason}
        title="Open a new season"
        description="Newly scheduled games will belong to this season. Existing games and records keep their original season."
      >
        <form
          className="form-stack"
          onSubmit={(e) => {
            e.preventDefault()
            mutation.mutate({ path: '/seasons', data: { name: new FormData(e.currentTarget).get('name') } })
          }}
        >
          <label>
            Season name
            <input name="name" required minLength={3} maxLength={80} placeholder="Spring 2027" />
          </label>
          <Button type="submit" busy={mutation.isPending}>
            Start season
          </Button>
        </form>
      </Modal>
      <Modal
        open={addNote}
        onOpenChange={setAddNote}
        title="A note for the club"
        description="Pitch updates, kit reminders, and everything in between."
      >
        <form className="form-stack" onSubmit={saveNote}>
          <label>
            Title
            <input name="title" required minLength={2} maxLength={100} />
          </label>
          <label>
            Category
            <select name="category">
              <option value="general">Club news</option>
              <option value="pitch">Pitch & booking</option>
              <option value="equipment">Equipment</option>
            </select>
          </label>
          <label>
            Your note
            <textarea name="body" rows={5} required minLength={2} maxLength={2000} />
          </label>
          <Button type="submit" busy={mutation.isPending}>
            <Plus size={16} />
            Post notice
          </Button>
        </form>
      </Modal>
      <Modal
        open={!!member}
        onOpenChange={(v) => !v && setMember(null)}
        title={`Manage ${member?.name || 'member'}`}
        description="Keep primary team membership and account access up to date."
      >
        {member && (
          <form className="form-stack" onSubmit={saveMember}>
            <label>
              Primary team
              <select name="team_id" defaultValue={member.team_id ?? ''}>
                <option value="">Unassigned</option>
                <option value="1">Old Gentlemen</option>
                <option value="2">Young Boys</option>
              </select>
            </label>
            <label>
              Role
              <select name="role" defaultValue={member.role} disabled={!member.has_account}>
                <option value="player">Player · RSVP and own profile</option>
                <option value="captain">Captain · organize games</option>
                <option value="admin">Admin · manage the club</option>
              </select>
              {!member.has_account && <input type="hidden" name="role" value="player" />}
            </label>
            <label className="checkbox-label">
              <input name="active" type="checkbox" defaultChecked={member.active} />
              Active club member
            </label>
            <p className="small-note">
              Inactive members cannot sign in and are hidden from the active roster. Historical records are
              preserved.
            </p>
            <Button type="submit" busy={mutation.isPending}>
              <Check size={16} />
              Save member
            </Button>
          </form>
        )}
      </Modal>
      <Modal
        open={deleteId !== null}
        onOpenChange={(v) => !v && setDeleteId(null)}
        title="Remove this club notice?"
        description="It will no longer appear on the noticeboard."
      >
        <div className="modal-actions">
          <Button variant="secondary" onClick={() => setDeleteId(null)}>
            Keep notice
          </Button>
          <Button
            variant="danger"
            busy={mutation.isPending}
            onClick={() => mutation.mutate({ path: `/notes/${deleteId}`, method: 'DELETE' })}
          >
            Remove notice
          </Button>
        </div>
      </Modal>
    </>
  )
}
