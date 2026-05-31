import type { VideoBreakdown } from '../api/types'
import {
  archetypeName,
  formatDuration,
  tierLabel,
  tierRange,
} from '../lib/format'
import ScoreRing from './ScoreRing'

const RING = { good: '#19d27c', mid: '#f5b53d', bad: '#f0544f' }

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
  // The honest "matches winners" score: the niche's data-derived predictive
  // features (NOT the old generic all-findings match%, which was noise vs
  // actual performance).
  const pm = b.pattern_match
  const hasData = pm != null && pm.total > 0
  const aligned = pm?.aligned ?? 0
  const total = pm?.total ?? 0
  const matchPct = hasData ? pm!.pct : 0
  const ringColor =
    matchPct >= 67 ? RING.good : matchPct >= 34 ? RING.mid : RING.bad

  const tier = b.tier
  const arch = archetypeName(b.archetype).toLowerCase()

  return (
    <div className="rounded-2xl border border-border bg-surface p-5 sm:p-6">
      <div className="flex flex-col items-center gap-6 sm:flex-row sm:gap-8">
        {hasData ? (
          <ScoreRing value={matchPct} color={ringColor} caption="pattern match" />
        ) : (
          <div className="grid h-[168px] w-[168px] shrink-0 place-items-center rounded-full border border-dashed border-border px-6 text-center text-xs leading-relaxed text-muted">
            No benchmark for this format yet
          </div>
        )}

        <div className="min-w-0 flex-1">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-muted">
            Scorecard
          </h2>
          <p className="mt-1.5 text-lg leading-snug">
            {hasData ? (
              <>
                This reel matches{' '}
                <span className="font-semibold" style={{ color: ringColor }}>
                  {aligned} of {total}
                </span>{' '}
                of the factors that actually predict performance in this niche.
              </>
            ) : (
              <>
                Not enough data yet to grade this niche&apos;s winning patterns.
              </>
            )}
          </p>
          {b.benchmark_scope === 'pooled' && tier ? (
            <p className="mt-1 text-xs text-muted">
              {tierLabel(tier)}-tier {arch} winners are too thin in this niche;
              comparing against all sizes instead.
            </p>
          ) : null}

          <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Tile
              label="Your size"
              value={tierLabel(tier)}
              hint={tierRange(tier)}
            />
            <Tile label="Format" value={archetypeName(b.archetype)} />
            <Tile label="Length" value={formatDuration(b.duration_seconds)} />
            <Tile
              label="Compared vs"
              value={`${b.archetype_n} winners`}
              hint={b.benchmark_scope === 'tier' ? 'same size + format' : 'all sizes, same format'}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
