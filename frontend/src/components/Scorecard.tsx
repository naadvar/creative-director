import type { VideoBreakdown } from '../api/types'
import {
  archetypeName,
  formatDuration,
  tierLabel,
  tierRange,
} from '../lib/format'

/** Honest standing within the cohort, derived from the tercile (0/1/2). No
 * 0–100 score, no red/green verdict — just where this reel sits among its
 * peers. Null when we don't have a labeled standing to show. */
function standingLine(tercile: number | null): string | null {
  switch (tercile) {
    case 2:
      return 'Sits in the top third of its cohort'
    case 1:
      return 'Sits in the middle third of its cohort'
    case 0:
      return 'Sits in the bottom third of its cohort'
    default:
      return null
  }
}

function Tile({
  label,
  value,
  hint,
}: {
  label: string
  value: string
  hint?: string
}) {
  return (
    <div className="rounded-lg border border-border bg-surface-2 px-3 py-2.5">
      <div className="text-[10px] font-medium uppercase tracking-wider text-muted">
        {label}
      </div>
      <div className="mt-0.5 text-sm font-semibold leading-tight">{value}</div>
      {hint ? (
        <div className="mt-0.5 text-[11px] text-muted">{hint}</div>
      ) : null}
    </div>
  )
}

export default function Scorecard({ b }: { b: VideoBreakdown }) {
  const tier = b.tier
  const arch = archetypeName(b.archetype).toLowerCase()
  // An honest one-line cohort descriptor: "14s · visual demo · 240 winners".
  const cohort = [
    formatDuration(b.duration_seconds),
    archetypeName(b.archetype).toLowerCase(),
  ]
    .filter(Boolean)
    .join(' · ')
  // Standing comes from the labeled tercile, when one exists. No invented
  // numbers, no red/green verdict.
  const standing = standingLine(b.tercile)

  return (
    <div className="rounded-2xl border border-border bg-surface p-5 sm:p-6">
      <h2 className="text-xs font-semibold uppercase tracking-widest text-muted">
        This reel
      </h2>
      <p className="mt-1.5 text-lg leading-snug">{cohort}</p>
      {standing ? (
        <p className="mt-1 text-sm text-muted">{standing}</p>
      ) : null}
      {b.benchmark_scope === 'pooled' && tier ? (
        <p className="mt-1 text-xs text-muted">
          {tierLabel(tier)}-tier {arch} winners are too thin in this niche;
          comparing against all sizes instead.
        </p>
      ) : null}

      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Tile label="Your size" value={tierLabel(tier)} hint={tierRange(tier)} />
        <Tile label="Format" value={archetypeName(b.archetype)} />
        <Tile label="Length" value={formatDuration(b.duration_seconds)} />
        <Tile
          label="Compared vs"
          value={`${b.archetype_n} winners`}
          hint={
            b.benchmark_scope === 'tier'
              ? 'same size + format'
              : 'all sizes, same format'
          }
        />
      </div>
    </div>
  )
}
