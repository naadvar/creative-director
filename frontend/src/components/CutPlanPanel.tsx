import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import type { CutPlan, CutSegment, TrimRecompute } from '../api/types'
import { timestamp } from '../lib/format'
import Spinner from './Spinner'

interface CutPlanPanelProps {
  videoId: string
  /** Bumped by the parent when the category changes, to refetch the plan. */
  categoryVersion?: number
  /** Seek the shared player (used to preview a trim point or a removed range). */
  onSeek?: (second: number) => void
  /** Play the winner-cut EDL (kept segments) in the shared player. */
  onPlayWinnerCut?: (segments: CutSegment[]) => void
  /** Current playhead second from the shared player, for the track marker. */
  currentSecond?: number
}

const hasCategory = (plan: CutPlan): boolean =>
  plan.benchmark_scope === 'category' &&
  Boolean(plan.category_label) &&
  plan.category_label !== 'Uncategorized'

/** "Powerlifting winners" / "winners in your tier" — names the cohort badge. */
function scopeLabel(plan: CutPlan): string {
  return hasCategory(plan) ? `${plan.category_label} winners` : 'winners in your tier'
}

/** Inline phrase for the body copy: "winning powerlifting reels" / "winning reels your size". */
function cohortPhrase(plan: CutPlan): string {
  return hasCategory(plan)
    ? `winning ${plan.category_label.toLowerCase()} reels`
    : 'winning reels your size'
}

function CheckRow({ label, pass }: { label: string; pass: boolean }) {
  return (
    <li className="flex items-center gap-2.5 text-sm">
      <span
        className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[11px] font-bold transition-colors ${
          pass
            ? 'border-good/50 bg-good/15 text-good'
            : 'border-border bg-white/5 text-muted'
        }`}
        aria-hidden
      >
        {pass ? '✓' : '○'}
      </span>
      <span className={pass ? 'text-text' : 'text-muted'}>{label}</span>
    </li>
  )
}

export default function CutPlanPanel({
  videoId,
  categoryVersion = 0,
  onSeek,
  onPlayWinnerCut,
  currentSecond,
}: CutPlanPanelProps) {
  const plan = useAsync(() => api.cutplan(videoId), [videoId, categoryVersion])
  const auto = useAsync(() => api.autocut(videoId), [videoId, categoryVersion])
  const [trimStart, setTrimStart] = useState(0)
  const [recompute, setRecompute] = useState<TrimRecompute | null>(null)
  const [recomputing, setRecomputing] = useState(false)
  const [dragging, setDragging] = useState(false)
  const trackRef = useRef<HTMLDivElement>(null)

  const p = plan.data
  const duration = p?.duration ?? 0
  // Cap the trim handle so a creator can't "align" by gutting the video.
  const handleMax = useMemo(
    () => Math.max(1, Math.min(duration - 1, Math.round(duration * 0.6))),
    [duration],
  )

  // Debounced live recompute as the handle moves (also fires once on load at 0).
  useEffect(() => {
    if (!p) return
    setRecomputing(true)
    const t = setTimeout(() => {
      api
        .cutplanTrim(videoId, trimStart)
        .then((r) => setRecompute(r))
        .catch(() => {})
        .finally(() => setRecomputing(false))
    }, 160)
    return () => clearTimeout(t)
  }, [videoId, trimStart, p])

  if (plan.loading) {
    return (
      <div className="rounded-2xl border border-border bg-surface p-5">
        <Spinner label="Building cut plan…" />
      </div>
    )
  }
  // No timeline for this video -> no cut plan. Stay quiet rather than erroring.
  if (plan.error || !p) return null

  const pct = (s: number) => `${Math.min(100, Math.max(0, (s / duration) * 100))}%`

  const secondFromClientX = (clientX: number): number => {
    const el = trackRef.current
    if (!el) return trimStart
    const rect = el.getBoundingClientRect()
    const frac = (clientX - rect.left) / rect.width
    return Math.max(0, Math.min(handleMax, Math.round(frac * duration)))
  }

  const onPointerDown = (e: React.PointerEvent) => {
    e.currentTarget.setPointerCapture(e.pointerId)
    setDragging(true)
    setTrimStart(secondFromClientX(e.clientX))
  }
  const onPointerMove = (e: React.PointerEvent) => {
    if (!dragging) return
    setTrimStart(secondFromClientX(e.clientX))
  }
  const endDrag = () => {
    if (!dragging) return
    setDragging(false)
    onSeek?.(trimStart)
  }
  const onKeyDown = (e: React.KeyboardEvent) => {
    let next: number | null = null
    if (e.key === 'ArrowLeft') next = Math.max(0, trimStart - 1)
    else if (e.key === 'ArrowRight') next = Math.min(handleMax, trimStart + 1)
    if (next != null) {
      e.preventDefault()
      setTrimStart(next)
      onSeek?.(next)
    }
  }

  const aligned = recompute?.aligned ?? 0
  const total = recompute?.total ?? 0
  const allPass = total > 0 && aligned === total
  const a = auto.data

  return (
    <div className="rounded-2xl border border-border bg-surface p-4 sm:p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h3 className="text-base font-semibold">Cut it like a winner</h3>
        <span className="text-xs text-muted">
          compared to{' '}
          <span className="font-medium text-text/80">{scopeLabel(p)}</span>
        </span>
      </div>

      {/* ============ Winner cut (auto) ============ */}
      {auto.loading ? (
        <p className="mt-3 text-sm text-muted">Building the winner cut…</p>
      ) : a && a.changed ? (
        <div className="mt-3">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <button
              type="button"
              onClick={() => onPlayWinnerCut?.(a.segments)}
              className="inline-flex items-center gap-2 rounded-lg bg-accent px-3.5 py-2 text-sm font-semibold text-ink transition-transform hover:scale-[1.02]"
            >
              <svg width="11" height="12" viewBox="0 0 11 12" fill="currentColor" aria-hidden>
                <path d="M1 1.3v9.4a.6.6 0 0 0 .92.5l7.5-4.7a.6.6 0 0 0 0-1L1.92.8A.6.6 0 0 0 1 1.3Z" />
              </svg>
              Play the winner cut
            </button>
            <span className="text-sm">
              <span className="font-semibold tabular-nums">{a.original_duration}s</span>
              <span className="text-muted"> → </span>
              <span className="font-semibold tabular-nums text-good">{a.new_duration}s</span>
              <span className="text-muted"> · trims {a.removed_seconds}s of dead air</span>
            </span>
          </div>

          {/* kept (green) vs removed (red) strip */}
          <div className="relative mt-3 h-2.5 w-full overflow-hidden rounded-full bg-bad/25" title="green = kept, red = removed">
            {a.segments.map((s) => (
              <div
                key={`keep-${s.start}`}
                className="absolute inset-y-0 bg-good"
                style={{ left: pct(s.start), width: pct(s.end - s.start) }}
              />
            ))}
          </div>

          {/* what got cut, and why */}
          <ul className="mt-3 space-y-1.5">
            {a.removed.map((r) => (
              <li key={`rm-${r.start}`}>
                <button
                  type="button"
                  onClick={() => onSeek?.(r.start)}
                  className="flex w-full items-baseline gap-2 rounded px-1 py-0.5 text-left text-sm transition-colors hover:bg-white/5"
                >
                  <span className="shrink-0 font-semibold tabular-nums text-bad">
                    −{r.end - r.start}s
                  </span>
                  <span className="shrink-0 tabular-nums text-muted">
                    {timestamp(r.start)}–{timestamp(r.end)}
                  </span>
                  <span className="text-muted">{r.reason}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : a ? (
        <div className="mt-3 flex items-center gap-2 text-sm text-good">
          <span aria-hidden>✓</span>
          <span>Already tight — no dead air to cut. This reel is paced like winners.</span>
        </div>
      ) : null}

      <p className="mt-2.5 text-xs leading-relaxed text-muted">
        The winner cut removes only footage with <span className="text-text/70">no one on screen and no motion</span> —
        never live footage. It matches how {cohortPhrase(p)} are paced; it doesn’t promise more views.
      </p>

      {/* ============ Fine-tune the open (manual) ============ */}
      <div className="mt-5 border-t border-border pt-4">
        <h4 className="text-sm font-semibold">Fine-tune the open yourself</h4>
        <p className="mt-1 text-xs leading-relaxed text-muted">
          Drag the handle to where the reel would start; the hook checks update live.
        </p>

        {/* Interactive trim track */}
        <div className="mt-3">
          <div
            ref={trackRef}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={endDrag}
            onPointerCancel={endDrag}
            className="relative h-14 w-full cursor-pointer touch-none select-none overflow-hidden rounded-lg bg-white/5"
          >
            {/* over-long holds (amber) */}
            {p.over_long_holds.map((h) => (
              <div
                key={`hold-${h.start}`}
                className="absolute inset-y-0 bg-mid/15"
                style={{ left: pct(h.start), width: pct(h.length) }}
                title={`${h.length}s hold (${timestamp(h.start)}–${timestamp(h.end)})`}
              />
            ))}
            {/* your cuts (thin vertical lines) */}
            {p.your_cuts.map((c) => (
              <div
                key={`cut-${c}`}
                className="absolute inset-y-0 w-px bg-text/30"
                style={{ left: pct(c) }}
                title={`your cut @ ${timestamp(c)}`}
              />
            ))}
            {/* winner first-cut target (green dashed) */}
            {p.winner_first_cut != null ? (
              <div
                className="absolute inset-y-0 border-l border-dashed border-good/70"
                style={{ left: pct(p.winner_first_cut) }}
                title={`winners cut by ~${p.winner_first_cut.toFixed(0)}s`}
              />
            ) : null}
            {/* trimmed-away region */}
            <div
              className="absolute inset-y-0 left-0 bg-black/55 backdrop-grayscale"
              style={{ width: pct(trimStart) }}
              aria-hidden
            />
            {/* playhead */}
            {currentSecond != null && currentSecond >= 0 && currentSecond <= duration ? (
              <div
                className="pointer-events-none absolute inset-y-0 w-0.5 bg-white/80"
                style={{ left: pct(currentSecond) }}
                aria-hidden
              />
            ) : null}
            {/* drag handle */}
            <div
              role="slider"
              tabIndex={0}
              aria-label="Trim start"
              aria-valuemin={0}
              aria-valuemax={handleMax}
              aria-valuenow={trimStart}
              onKeyDown={onKeyDown}
              className={`absolute inset-y-0 z-10 -ml-2 flex w-4 cursor-ew-resize items-center justify-center rounded-sm bg-accent shadow-lg outline-none ring-offset-1 ring-offset-surface focus-visible:ring-2 focus-visible:ring-accent ${
                dragging ? 'ring-2 ring-accent' : ''
              }`}
              style={{ left: pct(trimStart) }}
            >
              <span className="h-5 w-px bg-black/40" />
            </div>
          </div>
          <div className="mt-1 flex justify-between text-[11px] tabular-nums text-muted">
            <span>0:00</span>
            <span className="text-text/80">
              start at {timestamp(trimStart)}
              {trimStart > 0 ? ` · trims ${trimStart}s` : ' · no trim'}
            </span>
            <span>{timestamp(duration)}</span>
          </div>
        </div>

        {/* Live alignment scoreboard */}
        <div className="mt-4 grid gap-4 sm:grid-cols-[auto_1fr] sm:items-center">
          <div
            className={`flex items-center gap-3 rounded-xl border px-4 py-3 transition-colors ${
              allPass ? 'border-good/40 bg-good/10' : 'border-border bg-white/5'
            }`}
          >
            <div className="text-center">
              <div
                className={`text-2xl font-bold tabular-nums leading-none ${
                  allPass ? 'text-good' : 'text-text'
                }`}
              >
                {aligned}/{total}
              </div>
              <div className="mt-1 text-[11px] uppercase tracking-wide text-muted">
                aligned
              </div>
            </div>
          </div>
          <ul className={`space-y-1.5 transition-opacity ${recomputing ? 'opacity-50' : ''}`}>
            {recompute && recompute.checks.length > 0 ? (
              recompute.checks.map((c) => (
                <CheckRow key={c.label} label={c.label} pass={c.pass} />
              ))
            ) : (
              <li className="text-sm text-muted">No hook checks for this video.</li>
            )}
          </ul>
        </div>

        {/* Suggested trim CTA + reset */}
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {p.suggested_trim_start != null && p.suggested_trim_start !== trimStart ? (
            <button
              type="button"
              onClick={() => {
                setTrimStart(p.suggested_trim_start!)
                onSeek?.(p.suggested_trim_start!)
              }}
              className="rounded-lg border border-accent/40 bg-accent/10 px-3 py-1.5 text-sm font-medium text-accent transition-colors hover:bg-accent/20"
            >
              Suggested trim → {timestamp(p.suggested_trim_start)}
            </button>
          ) : null}
          {trimStart > 0 ? (
            <button
              type="button"
              onClick={() => {
                setTrimStart(0)
                onSeek?.(0)
              }}
              className="rounded-lg border border-border px-3 py-1.5 text-sm text-muted transition-colors hover:text-text"
            >
              Reset
            </button>
          ) : null}
        </div>

        {/* Static facts + suggestions */}
        <div className="mt-4 border-t border-border pt-4">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-3">
            <div>
              <dt className="text-xs text-muted">Your first cut</dt>
              <dd className="font-medium tabular-nums">
                {p.your_first_cut != null ? `${p.your_first_cut}s` : 'none'}
              </dd>
            </div>
            {p.winner_first_cut != null ? (
              <div>
                <dt className="text-xs text-muted">Winners cut by</dt>
                <dd className="font-medium tabular-nums text-good">
                  ~{p.winner_first_cut.toFixed(0)}s
                </dd>
              </div>
            ) : null}
            {p.winner_avg_shot != null ? (
              <div>
                <dt className="text-xs text-muted">Winner shot length</dt>
                <dd className="font-medium tabular-nums">~{p.winner_avg_shot}s avg</dd>
              </div>
            ) : null}
          </dl>

          {p.suggestions.length > 0 ? (
            <ul className="mt-3 space-y-1.5">
              {p.suggestions.map((s, i) => (
                <li key={`${s.type}-${s.second}-${i}`}>
                  <button
                    type="button"
                    onClick={() => onSeek?.(s.second)}
                    className="flex w-full gap-2 rounded px-1 py-0.5 text-left text-sm transition-colors hover:bg-white/5"
                  >
                    <span className="shrink-0 font-semibold tabular-nums text-mid">
                      {timestamp(s.second)}
                    </span>
                    <span className="text-muted">{s.message}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </div>
    </div>
  )
}
