import { useState, type ReactNode } from 'react'
import { api } from '../api/client'
import type { CraftReadData } from '../api/types'

function Check() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="mt-0.5 shrink-0 text-good">
      <path
        d="M2.5 7.5 5.5 10.5 11.5 3.5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/** "m:ss" -> seconds, or null if it isn't a timestamp. */
function tsToSeconds(ts: string): number | null {
  const m = ts.match(/^(\d{1,2}):(\d{2})$/)
  if (!m) return null
  return parseInt(m[1], 10) * 60 + parseInt(m[2], 10)
}

/** A tappable timestamp. Tapping scrubs the player to that second so the creator
 * VERIFIES the claim against their own footage in one tap — which also turns any
 * mis-read into a self-defusing tap (it lands on the wrong frame) instead of an
 * absorbed claim. Falls back to plain text when there's no player to drive. */
function TimeChip({ ts, onSeek }: { ts: string; onSeek?: (s: number) => void }) {
  const secs = tsToSeconds(ts)
  if (secs == null || !onSeek) {
    return <span className="font-medium tabular-nums text-muted">{ts}</span>
  }
  return (
    <button
      type="button"
      onClick={() => onSeek(secs)}
      title="Jump to this moment"
      className="rounded bg-accent/10 px-1 font-medium tabular-nums text-accent underline-offset-2 hover:bg-accent/20 hover:underline"
    >
      {ts}
    </button>
  )
}

const TS_RE = /\b\d{1,2}:\d{2}\b/g

/** Render text with every "m:ss" turned into a tappable TimeChip. */
function linkify(text: string | undefined, onSeek?: (s: number) => void): ReactNode {
  if (!text) return null
  const out: ReactNode[] = []
  let last = 0
  let key = 0
  const re = new RegExp(TS_RE)
  let m: RegExpExecArray | null
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index))
    out.push(<TimeChip key={key++} ts={m[0]} onSeek={onSeek} />)
    last = m.index + m[0].length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

/** Split a blind-spot string "m:ss - observation. Fix: ..." into its parts. */
function parseSpot(s: string): { where: string; observation: string; fix: string } {
  let where = ''
  let body = s.trim()
  const m = body.match(/^([0-9][0-9:.\s-]*?)\s*[-–—]\s*(.*)$/)
  if (m) {
    where = m[1].trim()
    body = m[2]
  }
  const fi = body.search(/\bfix:\s*/i)
  if (fi >= 0) {
    return {
      where,
      observation: body.slice(0, fi).trim().replace(/[.\s]+$/, ''),
      fix: body.slice(fi).replace(/^[^:]*:\s*/, '').trim(),
    }
  }
  return { where, observation: body, fix: '' }
}

const STRUCTURE: [string, (d: CraftReadData) => string][] = [
  ['Hook', (d) => d.hook],
  ['Payoff', (d) => d.payoff],
  ['Pacing', (d) => d.pacing],
]

export default function CraftRead({
  data,
  onSeek,
  videoId,
}: {
  data: CraftReadData
  onSeek?: (second: number) => void
  videoId?: string
}) {
  const rawSpots = data.blind_spots ?? []
  const spots = rawSpots.map(parseSpot)
  const doneWell = data.done_well ?? []
  const [dismissed, setDismissed] = useState<Set<number>>(new Set())

  // One-tap dismissal: hide the note and record it (trust affordance + training signal).
  const dismiss = (i: number, reason: string) => {
    setDismissed((prev) => new Set(prev).add(i))
    if (videoId && rawSpots[i]) api.noteFeedback(videoId, rawSpots[i], reason).catch(() => {})
  }
  const visibleSpots = spots.map((s, i) => ({ s, i })).filter(({ i }) => !dismissed.has(i))

  return (
    <div className="rounded-2xl border border-border bg-surface p-5 sm:p-6">
      <h3 className="text-xs font-semibold uppercase tracking-widest text-muted">Craft read</h3>
      <p className="mt-2 text-lg leading-relaxed">{linkify(data.verdict, onSeek)}</p>

      {data.biggest_opportunity ? (
        <div className="mt-4 rounded-xl border border-accent/30 bg-accent/10 p-4">
          <div className="text-xs font-semibold uppercase tracking-widest text-accent">
            Biggest opportunity
          </div>
          <p className="mt-1.5 text-sm leading-relaxed">{linkify(data.biggest_opportunity, onSeek)}</p>
        </div>
      ) : null}

      {data.what_it_is ? (
        <p className="mt-4 text-sm leading-relaxed text-muted">{data.what_it_is}</p>
      ) : null}

      <div className="mt-4 grid gap-2.5 sm:grid-cols-3">
        {STRUCTURE.map(([k, get]) => (
          <div key={k} className="rounded-lg border border-border bg-surface-2 p-3">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">{k}</div>
            <p className="mt-1 text-[13px] leading-snug">{linkify(get(data), onSeek)}</p>
          </div>
        ))}
      </div>

      {/* Lead with what works — praise before critique on work they're proud of. */}
      {doneWell.length > 0 ? (
        <div className="mt-5">
          <h4 className="text-sm font-semibold">What's working</h4>
          <ul className="mt-2.5 space-y-2">
            {doneWell.map((d, i) => (
              <li key={i} className="flex gap-2.5 text-sm leading-relaxed text-muted">
                <Check />
                <span>{linkify(d, onSeek)}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {visibleSpots.length > 0 ? (
        <div className="mt-5">
          <h4 className="text-sm font-semibold">Worth a second look</h4>
          <ul className="mt-2.5 space-y-2.5">
            {visibleSpots.map(({ s, i }) => (
              <li key={i} className="rounded-lg border border-border bg-surface-2 p-3">
                <div className="flex items-baseline gap-2">
                  {s.where ? (
                    <span className="shrink-0 text-[11px]">{linkify(s.where, onSeek)}</span>
                  ) : null}
                  <span className="text-sm leading-relaxed">{linkify(s.observation, onSeek)}</span>
                </div>
                {s.fix ? (
                  <div className="mt-1.5 flex gap-2 text-[13px] leading-relaxed">
                    <span className="shrink-0 font-medium text-accent">Try</span>
                    <span>{linkify(s.fix, onSeek)}</span>
                  </div>
                ) : null}
                {/* Calm one-tap override — the creator is the expert on their own footage. */}
                <div className="mt-2 flex items-center gap-2 text-[11px] text-muted/60">
                  <span>Off-base?</span>
                  <button
                    type="button"
                    onClick={() => dismiss(i, 'not_in_reel')}
                    className="underline-offset-2 transition-colors hover:text-text hover:underline"
                  >
                    not in my reel
                  </button>
                  <span aria-hidden>·</span>
                  <button
                    type="button"
                    onClick={() => dismiss(i, 'not_useful')}
                    className="underline-offset-2 transition-colors hover:text-text hover:underline"
                  >
                    not useful
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="mt-5 border-t border-border pt-3 text-xs text-muted">
        Read from your frames — tap any timestamp to check it. Craft observations only, no
        performance or virality claims.
      </div>
    </div>
  )
}
