import { Check, Clipboard, Download, MessageCircle, Send } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { Button, Modal } from './ui'
import { copyText } from '../lib'
import { matchSummary } from '../share'
import type { Match } from '../types'

export function ShareDialog({
  open,
  onOpenChange,
  match,
  customText,
  title = 'Share with the squad',
}: {
  open: boolean
  onOpenChange: (value: boolean) => void
  match?: Match
  customText?: string
  title?: string
}) {
  const [copied, setCopied] = useState(false)
  const text = customText || (match ? matchSummary(match) : '')
  async function copy() {
    try {
      await copyText(text)
      setCopied(true)
      toast.success('Copied. Paste it into your Messenger group.')
      setTimeout(() => setCopied(false), 2500)
    } catch (e) {
      toast.error((e as Error).message)
    }
  }
  async function share() {
    try {
      if (navigator.share) await navigator.share({ title: 'Lex Pickup Pro', text })
      else await copy()
    } catch (e) {
      if ((e as Error).name !== 'AbortError') toast.error('Sharing is unavailable. Use Copy summary instead.')
    }
  }
  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      description="Less back-and-forth. Everyone on the same page."
    >
      <div className="share-intro">
        <span className="messenger-icon">
          <MessageCircle size={22} />
        </span>
        <div>
          <strong>Ready for Messenger</strong>
          <p>Copy the summary and paste it into your group chat.</p>
        </div>
      </div>
      <textarea className="share-preview" value={text} readOnly aria-label="Shareable summary" rows={12} />
      <div className="modal-actions">
        <Button variant="secondary" onClick={share}>
          <Send size={16} />
          Share…
        </Button>
        <Button onClick={copy}>
          {copied ? <Check size={16} /> : <Clipboard size={16} />}
          {copied ? 'Copied!' : 'Copy summary'}
        </Button>
      </div>
      {match && (
        <a className="calendar-download" href={`/api/v1/matches/${match.id}/calendar`} download>
          <Download size={15} />
          Add this game to your calendar
        </a>
      )}
    </Modal>
  )
}
