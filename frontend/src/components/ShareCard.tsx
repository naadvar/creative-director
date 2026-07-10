import { useRef, useState } from 'react'
import { toPng } from 'html-to-image'
import { Capacitor } from '@capacitor/core'
import { Directory, Filesystem } from '@capacitor/filesystem'
import { Share } from '@capacitor/share'
import { api } from '../api/client'
import type { CraftReadData } from '../api/types'

const SHARE_HOST = 'creative-director-psi.vercel.app'
const SILENT_RE = /well-executed as is|no major craft change/i

/** Trim to the first sentence (or a hard cap) so the card stays tight. */
function tighten(s: string, max = 150): string {
  const t = (s || '').trim()
  const dot = t.search(/[.!?](\s|$)/)
  const cut = dot > 30 && dot < max ? dot + 1 : Math.min(t.length, max)
  return t.slice(0, cut).trim() + (cut < t.length ? '…' : '')
}

function PlayMark() {
  return (
    <svg width="14" height="14" viewBox="0 0 12 12" fill="currentColor" className="text-white">
      <path d="M3 1.7v8.6a.6.6 0 0 0 .92.5l6.7-4.3a.6.6 0 0 0 0-1L3.92 1.2A.6.6 0 0 0 3 1.7Z" />
    </svg>
  )
}

export default function ShareCard({
  read,
  title,
  durationLabel,
  onClose,
}: {
  read: CraftReadData
  title: string
  durationLabel: string
  onClose: () => void
}) {
  const cardRef = useRef<HTMLDivElement>(null)
  const [busy, setBusy] = useState(false)
  const [toast, setToast] = useState('')

  const opp = read.biggest_opportunity || ''
  const isSilent = !opp || SILENT_RE.test(opp)
  const dim =
    read.opportunity_dimension && read.opportunity_dimension !== 'none'
      ? read.opportunity_dimension
      : ''
  const working = (read.done_well || [])[0]

  async function render(): Promise<string | null> {
    if (!cardRef.current) return null
    return toPng(cardRef.current, { pixelRatio: 2, cacheBust: true, backgroundColor: '#07070a' })
  }

  async function save() {
    setBusy(true)
    try {
      const url = await render()
      if (url) {
        const a = document.createElement('a')
        a.href = url
        a.download = 'craft-read.png'
        a.click()
        setToast('Saved')
      }
    } catch {
      setToast('Could not render')
    } finally {
      setBusy(false)
      setTimeout(() => setToast(''), 1800)
    }
  }

  async function share() {
    setBusy(true)
    api.track('share_tapped')
    try {
      const url = await render()
      // Native (Capacitor): the Web Share API can't share a File from the webview,
      // so write the PNG to the cache dir and hand the file URI to the native sheet.
      // Any failure falls through to the web chain below.
      if (url && Capacitor.isNativePlatform()) {
        try {
          const base64 = url.split(',')[1] // strip the "data:image/png;base64," prefix
          const { uri } = await Filesystem.writeFile({
            path: 'craft-read.png',
            data: base64,
            directory: Directory.Cache,
          })
          await Share.share({ files: [uri], title: 'My craft read' })
          return
        } catch {
          /* native share unavailable/cancelled — fall through to the web path */
        }
      }
      const nav = navigator as Navigator & {
        canShare?: (d: ShareData) => boolean
      }
      if (url && nav.share) {
        const blob = await (await fetch(url)).blob()
        const file = new File([blob], 'craft-read.png', { type: 'image/png' })
        if (nav.canShare?.({ files: [file] })) {
          await nav.share({ files: [file], title: 'My craft read' })
          return
        }
      }
      if (nav.share) {
        await nav.share({ title: 'Creative Director', url: `https://${SHARE_HOST}` })
      } else {
        await navigator.clipboard.writeText(`https://${SHARE_HOST}`)
        setToast('Link copied')
      }
    } catch {
      /* user cancelled or unsupported — no-op */
    } finally {
      setBusy(false)
      setTimeout(() => setToast(''), 1800)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div className="w-full max-w-sm" onClick={(e) => e.stopPropagation()}>
        <div
          ref={cardRef}
          className="overflow-hidden rounded-3xl border border-border p-6"
          style={{
            background:
              'radial-gradient(130% 80% at 50% -10%, rgba(124,92,255,0.20), transparent 55%), #07070a',
          }}
        >
          <div className="flex items-center gap-2">
            <span className="grid h-7 w-7 place-items-center rounded-lg bg-grad">
              <PlayMark />
            </span>
            <span className="text-[11px] font-bold uppercase tracking-[0.18em] text-muted">
              Craft read
            </span>
          </div>

          <p className="mt-4 truncate text-xs text-muted">
            {title} · {durationLabel}
          </p>
          <p className="mt-1 text-[17px] font-semibold leading-snug tracking-tight">
            {tighten(read.verdict, 130)}
          </p>

          {!isSilent && opp ? (
            <div className="mt-4 rounded-2xl border border-accent/40 bg-accent/[0.1] p-4">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-bold uppercase tracking-[0.16em] text-accent">
                  Fix this first
                </span>
                {dim ? (
                  <span className="ml-auto rounded-full bg-accent/15 px-2 py-0.5 text-[10px] font-medium capitalize text-accent">
                    {dim}
                  </span>
                ) : null}
              </div>
              <p className="mt-1.5 text-sm leading-relaxed">{tighten(opp, 170)}</p>
            </div>
          ) : (
            <div className="mt-4 rounded-2xl border border-good/25 bg-good/[0.08] p-4 text-sm">
              Well-executed as is — nothing major to change.
            </div>
          )}

          {working ? (
            <p className="mt-3 text-xs leading-relaxed text-muted">
              <span className="font-semibold text-good">Working:</span> {tighten(working, 100)}
            </p>
          ) : null}

          <div className="mt-5 flex items-center justify-between border-t border-border pt-3">
            <span className="text-[11px] text-muted">{SHARE_HOST}</span>
            <span className="text-grad text-[11px] font-bold">Creative Director</span>
          </div>
        </div>

        <div className="mt-3 flex gap-2">
          <button
            type="button"
            onClick={() => void save()}
            disabled={busy}
            className="flex-1 rounded-xl bg-grad py-2.5 text-sm font-bold text-white transition-all hover:brightness-110 disabled:opacity-60"
          >
            {busy ? 'Rendering…' : toast || 'Save image'}
          </button>
          <button
            type="button"
            onClick={() => void share()}
            disabled={busy}
            className="flex-1 rounded-xl border border-border bg-surface py-2.5 text-sm font-semibold transition-colors hover:border-accent/50 disabled:opacity-60"
          >
            Share
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border border-border bg-surface px-4 py-2.5 text-sm text-muted transition-colors hover:text-text"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
