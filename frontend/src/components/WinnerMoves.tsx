import type { VideoBreakdown } from '../api/types'

function fmt(v: number | null): string {
  if (v == null) return '—'
  return Number.isInteger(v) ? String(v) : v.toFixed(2)
}

/** The moat: specific, category-tuned "do what winners do" moves, derived from
 * the features that actually predict performance in this reel's niche. */
export default function WinnerMoves({ b }: { b: VideoBreakdown }) {
  const recs = b.recommendations ?? []
  if (recs.length === 0) return null
  return (
    <div className="rounded-2xl border border-accent/30 bg-surface p-5 sm:p-6">
      <h2 className="text-xs font-semibold uppercase tracking-widest text-muted">
        Do what winners do
      </h2>
      <p className="mt-1 text-sm text-muted">
        The biggest gaps between this reel and what actually predicts performance in its
        niche — most impactful first.
      </p>
      <ul className="mt-4 space-y-2.5">
        {recs.map((r) => (
          <li
            key={r.feature}
            className="flex items-start gap-3 rounded-lg border border-border bg-surface-2 px-3 py-2.5"
          >
            <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
            <div className="min-w-0">
              <div className="text-sm font-semibold leading-snug">{r.advice}</div>
              <div className="mt-0.5 text-xs text-muted">
                Winners ≈ <span className="text-text">{fmt(r.winner_value)}</span> · yours{' '}
                <span className="text-text">{fmt(r.your_value)}</span>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
