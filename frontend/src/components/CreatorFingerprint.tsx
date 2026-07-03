import type { Fingerprint } from '../api/types'

/** "Your creator fingerprint" — a descriptive style summary built from the
 * creator's own uploaded reels. Renders nothing until they have ≥1 analyzed reel. */
export default function CreatorFingerprint({ fp }: { fp: Fingerprint }) {
  if (!fp.ready) return null
  return (
    <div className="rounded-2xl border border-accent/30 bg-accent/[0.06] p-4 sm:p-5">
      <div className="flex flex-wrap items-baseline gap-x-2">
        <span className="text-xs font-semibold uppercase tracking-widest text-accent">
          Your creator fingerprint
        </span>
        <span className="text-[11px] text-muted">
          · {fp.n_reels} reel{fp.n_reels === 1 ? '' : 's'} analyzed
        </span>
      </div>
      <p className="mt-2 text-sm leading-relaxed">{fp.summary}</p>
      {fp.recurring && fp.recurring.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {fp.recurring.map((r) => (
            <span
              key={r.type}
              className="rounded-full border border-border bg-surface px-2.5 py-1 text-[11px] text-muted"
            >
              {r.label} <span className="text-muted/60">×{r.count}</span>
            </span>
          ))}
        </div>
      ) : null}
      <p className="mt-3 text-[11px] text-muted">
        Built from your own uploads. Never a performance prediction.
      </p>
    </div>
  )
}
