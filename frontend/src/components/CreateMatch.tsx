import { useState, type FormEvent } from 'react'
import { useMutation } from '@tanstack/react-query'
import { CalendarPlus, Repeat2 } from 'lucide-react'
import { toast } from 'sonner'
import { useNavigate } from 'react-router-dom'
import { format, addDays, nextSaturday } from 'date-fns'
import { refreshClub, send } from '../api'
import { Button, Modal } from './ui'
import type { Match } from '../types'

export function CreateMatch({
  open,
  onOpenChange,
  match,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  match?: Match
}) {
  const navigate = useNavigate()
  const defaultDate = nextSaturday(addDays(new Date(), 0))
  defaultDate.setHours(10, 0, 0, 0)
  const [error, setError] = useState('')
  const mutation = useMutation({
    mutationFn: (data: unknown) =>
      send<Match[]>(match ? `/matches/${match.id}` : '/matches', data, match ? 'PUT' : 'POST'),
    onSuccess: (games) => {
      refreshClub()
      onOpenChange(false)
      toast.success(
        match
          ? 'Game details updated'
          : games.length > 1
            ? `${games.length} weekly games scheduled`
            : 'Game is on the calendar',
      )
      navigate(`/matches/${games[0].id}`)
    },
    onError: (e: Error) => setError(e.message),
  })
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setError('')
    const f = new FormData(e.currentTarget)
    mutation.mutate({
      title: f.get('title'),
      starts_at: new Date(String(f.get('starts_at'))).toISOString(),
      kind: f.get('kind'),
      capacity: Number(f.get('capacity')),
      duration_minutes: Number(f.get('duration_minutes')),
      location: f.get('location'),
      address: f.get('address'),
      pitch: f.get('pitch'),
      notes: f.get('notes'),
      repeat_weeks: match ? 1 : Number(f.get('repeat_weeks')),
    })
  }
  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title={match ? 'Update the game plan' : 'Get a game going'}
      description={
        match
          ? 'Update this game. Clear saved lineups before changing the number of players.'
          : 'A place, a time, and your favorite people.'
      }
      wide
    >
      <form onSubmit={submit} className="form-stack">
        <label>
          Game name
          <input
            name="title"
            defaultValue={match?.title || 'Saturday morning football'}
            required
            minLength={3}
            maxLength={100}
          />
        </label>
        <div className="form-grid">
          <label>
            Kickoff · your local time
            <input
              type="datetime-local"
              name="starts_at"
              defaultValue={format(match ? new Date(match.starts_at) : defaultDate, "yyyy-MM-dd'T'HH:mm")}
              required
            />
          </label>
          <label>
            Format
            <select name="kind" defaultValue={match?.kind || 'classic'}>
              <option value="classic">Old Gentlemen vs Young Boys</option>
              <option value="mixed">Mixed & balanced sides</option>
            </select>
          </label>
          <label>
            Players
            <select name="capacity" defaultValue={match?.capacity || 14}>
              {[10, 12, 14, 16, 18, 20, 22].map((n) => (
                <option value={n} key={n}>
                  {n / 2} a side · {n} players
                </option>
              ))}
            </select>
          </label>
          <label>
            Duration
            <select name="duration_minutes" defaultValue={match?.duration_minutes || 90}>
              <option value="60">60 minutes</option>
              <option value="90">90 minutes</option>
              <option value="120">120 minutes</option>
            </select>
          </label>
        </div>
        <label>
          Location
          <input
            name="location"
            defaultValue={match?.location || 'Lexington Recreation Center'}
            required
            maxLength={120}
          />
        </label>
        <div className="form-grid">
          <label>
            Street address
            <input
              name="address"
              defaultValue={match?.address ?? '1625 Massachusetts Ave, Lexington, MA'}
              maxLength={250}
            />
          </label>
          <label>
            Pitch / booking
            <input name="pitch" defaultValue={match?.pitch ?? 'Center Field · Pitch 1'} maxLength={100} />
          </label>
        </div>
        {!match && (
          <label>
            <span className="inline-label">
              <Repeat2 size={15} />
              Repeat weekly
            </span>
            <select name="repeat_weeks">
              <option value="1">Just this game</option>
              <option value="4">Every week for 4 weeks</option>
              <option value="8">Every week for 8 weeks</option>
              <option value="12">Every week for 12 weeks</option>
            </select>
            <small>Recurring games keep the same Eastern time, including daylight saving changes.</small>
          </label>
        )}
        <label>
          Notes for the squad
          <textarea
            name="notes"
            rows={2}
            maxLength={2000}
            defaultValue={match?.notes ?? 'Bring a dark and a light shirt. Arrive 15 minutes early.'}
          />
        </label>
        {error && (
          <p role="alert" className="form-error">
            {error}
          </p>
        )}
        <div className="modal-actions">
          <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="submit" busy={mutation.isPending}>
            <CalendarPlus size={16} />
            {match ? 'Save game' : 'Schedule game'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
