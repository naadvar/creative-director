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

function Spark() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="shrink-0 text-accent">
      <path
        d="M7 1.5 8.4 5.6 12.5 7 8.4 8.4 7 12.5 5.6 8.4 1.5 7 5.6 5.6 7 1.5Z"
        fill="currentColor"
      />
    </svg>
  )
}

function CheckCircle() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" className="shrink-0 text-good">
      <circle cx="10" cy="10" r="8.25" stroke="currentColor" strokeWidth="1.4" opacity="0.5" />
      <path
        d="M6.5 10.2 9 12.6 13.6 7.4"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function PlayMini() {
  return (
    <svg width="11" height="11" viewBox="0 0 11 11" fill="currentColor" className="shrink-0">
      <path d="M2.5 1.4v8.2a.5.5 0 0 0 .77.42l6.4-4.1a.5.5 0 0 0 0-.84L3.27.98A.5.5 0 0 0 2.5 1.4Z" />
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

const SILENT_RE = /well-executed as is|no major craft change/i

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
  const [leverFb, setLeverFb] = useState<'helpful' | 'not_useful' | null>(null)

  // Helpful / not-useful on the headline fix — the positive signal (👍) plus the
  // negative one, both labeled training data (helpful = keep this lever shape).
  const rateLever = (reason: 'helpful' | 'not_useful') => {
    setLeverFb(reason)
    if (videoId) api.noteFeedback(videoId, data.biggest_opportunity ?? '', reason).catch(() => {})
  }

  // One-tap dismissal: hide the note and record it (trust affordance + training signal).
  const dismiss = (i: number, reason: string) => {
    setDismissed((prev) => new Set(prev).add(i))
    if (videoId && rawSpots[i]) api.noteFeedback(videoId, rawSpots[i], reason).catch(() => {})
  }
  const visibleSpots = spots.map((s, i) => ({ s, i })).filter(({ i }) => !dismissed.has(i))

  const opp = data.biggest_opportunity ?? ''
  const isSilent = !opp || SILENT_RE.test(opp)
  const dimension =
    data.opportunity_dimension && data.opportunity_dimension !== 'none'
      ? data.opportunity_dimension
      : ''
  const jumpSec = data.lever_timestamp ? tsToSeconds(data.lever_timestamp) : null

  return (
    <div className="animate-rise rounded-2xl border border-border bg-surface p-5 sm:p-6">
      <div className="flex items-center gap-2">
        <span className="h-1.5 w-1.5 rounded-full bg-accent" />
        <h3 className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted">
          Craft read
        </h3>
      </div>

      {/* The verdict is the headline. */}
      <p className="mt-3 text-xl font-medium leading-snug tracking-tight">
        {linkify(data.verdict, onSeek)}
      </p>

      {/* The one prioritized lever — the visual anchor of the read. */}
      {isSilent ? (
        <div className="mt-5 flex items-center gap-3 rounded-xl border border-good/25 bg-good/[0.06] p-4">
          <CheckCircle />
          <p className="text-sm leading-relaxed">Nicely done — nothing major to change here.</p>
        </div>
      ) : opp ? (
        <div className="mt-5 rounded-xl border border-accent/40 bg-accent/[0.08] p-4">
          <div className="flex items-center gap-2">
            <Spark />
            <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-accent">
              Fix this first
            </span>
            {dimension ? (
              <span className="ml-auto rounded-full border border-accent/30 bg-accent/10 px-2.5 py-0.5 text-[11px] font-medium capitalize text-accent">
                {dimension}
              </span>
            ) : null}
          </div>
          <p className="mt-2 text-[15px] leading-relaxed">{linkify(opp, onSeek)}</p>
          {jumpSec != null && onSeek ? (
            <button
              type="button"
              onClick={() => onSeek(jumpSec)}
              className="mt-2.5 inline-flex items-center gap-1.5 text-xs font-medium text-accent transition-opacity hover:opacity-80"
            >
              <PlayMini />
              Jump to {data.lever_timestamp}
            </button>
          ) : null}
          {/* Helpful? — the one-tap signal that tunes the engine over time. */}
          <div className="mt-3 flex items-center gap-2 border-t border-accent/15 pt-2.5 text-[12px]">
            {leverFb ? (
              <span className="text-muted">
                {leverFb === 'helpful' ? 'Glad it helped — noted. 🙌' : 'Thanks — that helps us tune it.'}
              </span>
            ) : (
              <>
                <span className="text-muted">Was this fix helpful?</span>
                <button
                  type="button"
                  onClick={() => rateLever('helpful')}
                  className="rounded-full border border-border bg-surface px-2.5 py-1 font-medium text-muted transition-colors hover:border-good/50 hover:text-good"
                >
                  👍 Helpful
                </button>
                <button
                  type="button"
                  onClick={() => rateLever('not_useful')}
                  className="rounded-full border border-border bg-surface px-2.5 py-1 font-medium text-muted transition-colors hover:border-bad/50 hover:text-bad"
                >
                  👎 Not quite
                </button>
              </>
            )}
          </div>
        </div>
      ) : null}

      {/* Lead with what works — praise before critique on work they're proud of. */}
      {doneWell.length > 0 ? (
        <div className="mt-5">
          <h4 className="text-sm font-semibold">What&apos;s working</h4>
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

      {/* Context demoted into a collapsible — the read leads with the action, not the anatomy. */}
      <details className="group mt-5">
        <summary className="flex cursor-pointer list-none items-center gap-1.5 text-xs font-medium text-muted transition-colors hover:text-text">
          <svg
            width="12"
            height="12"
            viewBox="0 0 12 12"
            fill="none"
            className="transition-transform group-open:rotate-90"
          >
            <path
              d="M4.5 3 7.5 6 4.5 9"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          The full read
        </summary>
        <div className="mt-3 space-y-3">
          {data.what_it_is ? (
            <p className="text-sm leading-relaxed text-muted">{data.what_it_is}</p>
          ) : null}
          <div className="grid gap-2.5 sm:grid-cols-3">
            {STRUCTURE.map(([k, get]) => (
              <div key={k} className="rounded-lg border border-border bg-surface-2 p-3">
                <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">
                  {k}
                </div>
                <p className="mt-1 text-[13px] leading-snug">{linkify(get(data), onSeek)}</p>
              </div>
            ))}
          </div>
        </div>
      </details>

      <div className="mt-5 border-t border-border pt-3 text-[11px] leading-relaxed text-muted">
        Read from your frames — tap any timestamp to check it. Craft observations only, no
        performance or virality claims.
      </div>
    </div>
  )
}
