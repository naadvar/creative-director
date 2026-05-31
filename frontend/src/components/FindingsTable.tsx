import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { ExampleVideo, Finding, Trajectory } from '../api/types'
import {
  fixabilityStyle,
  formatDuration,
  round1,
  thumbnailUrl,
} from '../lib/format'

const TRAJECTORY_VISUAL: Record<
  Trajectory,
  { arrow: string; text: string; cls: string; blurb: string }
> = {
  improving: {
    arrow: '↗',
    text: 'improving',
    cls: 'text-good',
    blurb:
      "You're already moving toward this in your recent reels — keep going.",
  },
  stable: {
    arrow: '→',
    text: 'stable',
    cls: 'text-muted',
    blurb: 'Your recent reels look about the same on this dimension.',
  },
  declining: {
    arrow: '↘',
    text: 'drifting',
    cls: 'text-bad',
    blurb:
      "Your recent reels are moving FURTHER from winners on this. Worth addressing.",
  },
}

function TrajectoryArrow({ t }: { t: Trajectory | null }) {
  if (!t) return null
  const v = TRAJECTORY_VISUAL[t]
  return (
    <span
      title={v.blurb}
      className={`inline-flex items-center gap-0.5 text-[10px] font-medium uppercase tracking-wider ${v.cls}`}
    >
      <span aria-hidden className="text-xs leading-none">
        {v.arrow}
      </span>
      <span>{v.text}</span>
    </span>
  )
}

function statusLabel(f: Finding): { text: string; cls: string } {
  if (f.direction === 'aligned') return { text: 'in line', cls: 'text-good' }
  if (f.direction === 'above') return { text: 'higher than winners', cls: 'text-mid' }
  if (f.direction === 'below') return { text: 'lower than winners', cls: 'text-mid' }
  return { text: f.direction, cls: 'text-muted' }
}

function fmt(v: number | null, unit: string): string {
  return v == null ? 'n/a' : `${round1(v)}${unit}`
}

function FixBadge({ fix }: { fix: Finding['fixability'] }) {
  const s = fixabilityStyle(fix)
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider ${s.text} ${s.bg} ${s.border}`}
      title={s.blurb}
    >
      {s.label}
    </span>
  )
}

function GapBar({ f }: { f: Finding }) {
  if (f.your_value == null || f.benchmark_value <= 0) return null
  const logRatio = Math.log2(Math.max(f.gap_ratio, 1e-3))
  const norm = Math.max(-1, Math.min(1, logRatio))
  const youPct = ((norm + 1) / 2) * 100
  const accent =
    f.direction === 'aligned'
      ? 'bg-good'
      : 'bg-mid'
  return (
    <div className="relative mt-1.5 h-1 w-full rounded-full bg-white/5">
      <div className="absolute left-1/2 top-1/2 h-2 w-px -translate-x-1/2 -translate-y-1/2 bg-muted" />
      <div
        className={`absolute top-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full ${accent}`}
        style={{ left: `${youPct}%` }}
      />
    </div>
  )
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 12 12"
      fill="none"
      className={`text-muted transition-transform ${open ? 'rotate-90' : ''}`}
      aria-hidden
    >
      <path
        d="m4.5 3 3 3-3 3"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function ExampleCard({
  ex,
  unit,
}: {
  ex: ExampleVideo
  unit: string
}) {
  return (
    <Link
      to={`/video/${ex.video_id}`}
      className="group flex shrink-0 flex-col gap-1.5 rounded-lg border border-border bg-surface p-2.5 transition-colors hover:border-accent/50"
      style={{ width: 160 }}
    >
      <div className="aspect-[9/12] overflow-hidden rounded-md bg-surface-2">
        <img
          src={thumbnailUrl(ex.video_id)}
          alt=""
          loading="lazy"
          className="h-full w-full object-cover transition-transform group-hover:scale-105"
        />
      </div>
      <div className="min-w-0 leading-tight">
        <div className="truncate text-xs font-medium" title={ex.title}>
          {ex.title}
        </div>
        <div className="truncate text-[11px] text-muted" title={ex.channel}>
          {ex.channel}
        </div>
        <div className="mt-1 flex items-center justify-between text-[11px]">
          <span className="tabular-nums">
            <span className="text-muted">{round1(ex.value)}{unit}</span>
          </span>
          {ex.duration_seconds != null ? (
            <span className="text-muted">{formatDuration(ex.duration_seconds)}</span>
          ) : null}
        </div>
      </div>
    </Link>
  )
}

function ExampleRow({
  videoId,
  feature,
  unit,
}: {
  videoId: string
  feature: string
  unit: string
}) {
  const [state, setState] = useState<
    | { kind: 'loading' }
    | { kind: 'ready'; examples: ExampleVideo[] }
    | { kind: 'error'; message: string }
  >({ kind: 'loading' })

  useEffect(() => {
    let alive = true
    setState({ kind: 'loading' })
    api
      .examples(videoId, feature)
      .then((r) => {
        if (alive) setState({ kind: 'ready', examples: r.examples })
      })
      .catch((e) => {
        if (alive) setState({ kind: 'error', message: String(e) })
      })
    return () => {
      alive = false
    }
  }, [videoId, feature])

  if (state.kind === 'loading') {
    return <p className="px-3 py-2 text-xs text-muted">Loading examples…</p>
  }
  if (state.kind === 'error') {
    return (
      <p className="px-3 py-2 text-xs text-bad">
        Couldn't load examples: {state.message}
      </p>
    )
  }
  if (state.examples.length === 0) {
    return (
      <p className="px-3 py-2 text-xs text-muted">
        No comparable winning reels available in this niche for this feature.
      </p>
    )
  }
  return (
    <div className="px-3 pb-3">
      <p className="mb-2 text-[10px] uppercase tracking-wider text-muted">
        Real winning reels close to the target value for this feature
      </p>
      <div className="flex gap-2.5 overflow-x-auto pb-1">
        {state.examples.map((ex) => (
          <ExampleCard key={ex.video_id} ex={ex} unit={unit} />
        ))}
      </div>
    </div>
  )
}

export default function FindingsTable({
  videoId,
  findings,
}: {
  videoId: string
  findings: Finding[]
}) {
  const [open, setOpen] = useState<string | null>(null)

  if (findings.length === 0) {
    return (
      <p className="text-sm text-muted">No comparable features for this archetype.</p>
    )
  }

  const firstActionable = findings.findIndex(
    (f) => f.off_benchmark && f.causal !== 'likely-proxy',
  )

  return (
    <div className="space-y-1">
      <div className="grid grid-cols-[1fr_auto_auto] gap-x-4 px-1 pb-1.5 text-xs uppercase tracking-wider text-muted">
        <span>Feature</span>
        <span className="text-right">This / winners</span>
        <span className="text-right">Effort</span>
      </div>
      <ul className="divide-y divide-border rounded-lg border border-border bg-surface-2">
        {findings.map((f, i) => {
          const st = statusLabel(f)
          const dim = !f.off_benchmark || f.causal === 'likely-proxy'
          const top = i === firstActionable
          const expanded = open === f.feature
          const toggle = () => setOpen(expanded ? null : f.feature)
          return (
            <li key={f.feature} className="relative">
              {top ? (
                <span
                  aria-hidden
                  className="absolute inset-y-0 left-0 w-0.5 rounded-full bg-good"
                />
              ) : null}
              <button
                type="button"
                onClick={toggle}
                aria-expanded={expanded}
                className={`grid w-full grid-cols-[1fr_auto_auto] items-center gap-x-4 px-3 py-2.5 text-left transition-colors hover:bg-white/[0.02] ${top ? 'bg-good/8' : ''}`}
              >
                <div className={`min-w-0 ${dim ? 'opacity-70' : ''}`}>
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <Chevron open={expanded} />
                    <span className="text-sm font-medium">{f.label}</span>
                    {f.causal === 'likely-proxy' ? (
                      <span
                        className="rounded-full border border-border bg-white/5 px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wider text-muted"
                        title="Likely a proxy for creator skill — copying the number won't move views."
                      >
                        weak signal
                      </span>
                    ) : null}
                  </div>
                  <div className="mt-0.5 flex items-center gap-2 text-xs">
                    <span className={st.cls}>{st.text}</span>
                    <TrajectoryArrow t={f.trajectory} />
                  </div>
                  <GapBar f={f} />
                </div>
                <div
                  className={`whitespace-nowrap text-right text-sm tabular-nums ${dim ? 'opacity-70' : ''}`}
                >
                  <span className="font-semibold">{fmt(f.your_value, f.unit)}</span>
                  <span className="text-muted"> / ~{fmt(f.benchmark_value, f.unit)}</span>
                </div>
                <div className="text-right">
                  <FixBadge fix={f.fixability} />
                </div>
              </button>
              {expanded ? (
                <ExampleRow
                  videoId={videoId}
                  feature={f.feature}
                  unit={f.unit}
                />
              ) : null}
            </li>
          )
        })}
      </ul>
      <p className="pt-1 text-[11px] text-muted">
        Click any row to see real winning reels close to the target.
      </p>
    </div>
  )
}
