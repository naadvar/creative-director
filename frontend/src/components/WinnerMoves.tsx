import type { VideoBreakdown } from '../api/types'

function fmt(v: number | null): string {
  if (v == null) return '—'
  return Number.isInteger(v) ? String(v) : v.toFixed(2)
}

/** Weak proxy signals — numeric feature gaps vs cohort winners. These are
 * correlational at best, so they're demoted below the read and tucked behind a
 * collapsed disclosure rather than surfaced as prime advice. Renders bare (no
 * outer card) so it can live inside a Collapsible. */
export default function WinnerMoves({ b }: { b: VideoBreakdown }) {
  const recs = b.recommendations ?? []
  if (recs.length === 0) return null
  return (
    <div>
      <p className="text-sm text-muted">
        Raw feature gaps between this reel and cohort winners. These are weak,
        correlational signals — patterns, not causes. Treat as curiosities, not
        a to-do list.
      </p>
      <ul className="mt-4 space-y-2.5">
        {recs.map((r) => (
          <li
            key={r.feature}
            className="flex items-start gap-3 rounded-lg border border-border bg-surface-2 px-3 py-2.5"
          >
            <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-muted" />
            <div className="min-w-0">
              <div className="text-sm font-medium leading-snug">{r.advice}</div>
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
