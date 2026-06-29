import { Link } from 'react-router-dom'
import type { RevisionVerdict as Verdict } from '../api/types'

function tsToSeconds(ts?: string): number | null {
  if (!ts) return null
  const m = ts.match(/(\d{1,2}):(\d{2})/)
  return m ? parseInt(m[1], 10) * 60 + parseInt(m[2], 10) : null
}

const STYLE = {
  fixed: { ring: 'border-good/40 bg-good/[0.08]', pill: 'text-good', label: '✓ You fixed this' },
  still_there: {
    ring: 'border-accent/40 bg-accent/[0.07]',
    pill: 'text-accent',
    label: 'Still worth another pass',
  },
  cant_verify: {
    ring: 'border-border bg-surface',
    pill: 'text-muted',
    label: 'Couldn’t re-check this automatically',
  },
} as const

/** "Did my fix land?" — shown above the read on a re-upload. The verdict is grounded
 * by re-watching the new frames (it never inferred a fix from the noisy new read), so
 * it's honest: it only says "fixed" when it's verified, never silence-as-success. */
export default function RevisionVerdict({
  verdict,
  onSeek,
}: {
  verdict: Verdict
  onSeek?: (s: number) => void
}) {
  const s = STYLE[verdict.state] ?? STYLE.cant_verify
  const jump = tsToSeconds(verdict.prior_timestamp)
  const body =
    verdict.state === 'fixed'
      ? `Last time: “${verdict.prior_issue}” Re-watching your new frames, that’s resolved.`
      : verdict.state === 'still_there'
        ? `“${verdict.prior_issue}” — re-watching, here’s what I still see: ${
            verdict.evidence || 'it’s still present.'
          } The original fix still applies.`
        : `I couldn’t reliably re-check “${verdict.prior_issue}” on this version, so I won’t guess — your fresh read is below.`

  return (
    <div className={`rounded-2xl border p-5 ${s.ring}`}>
      <div className="flex items-center justify-between gap-2">
        <span className={`text-[11px] font-semibold uppercase tracking-[0.16em] ${s.pill}`}>
          {s.label}
        </span>
        {verdict.prior_video_id ? (
          <Link
            to={`/video/${verdict.prior_video_id}`}
            className="shrink-0 truncate text-xs text-muted hover:text-text"
          >
            see the original{verdict.prior_title ? ` · ${verdict.prior_title}` : ''}
          </Link>
        ) : null}
      </div>
      <p className="mt-2 text-[15px] leading-relaxed">{body}</p>
      {verdict.state === 'fixed' && verdict.evidence ? (
        <p className="mt-1.5 text-sm text-muted">{verdict.evidence}</p>
      ) : null}
      {jump != null && onSeek ? (
        <button
          type="button"
          onClick={() => onSeek(jump)}
          className="mt-2.5 inline-flex items-center gap-1.5 text-xs font-medium text-accent transition-opacity hover:opacity-80"
        >
          ▶ Compare at {verdict.prior_timestamp}
        </button>
      ) : null}
      <p className="mt-3 border-t border-white/5 pt-2.5 text-[11px] leading-relaxed text-muted">
        Verified by re-watching your new frames — tap the timestamp to check it yourself.
      </p>
    </div>
  )
}
