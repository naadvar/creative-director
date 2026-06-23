export interface CraftMark {
  second: number
  label: string
}

/** A slim bar under the video that places a tappable marker at each craft-read
 * flagged moment — so the read literally annotates the creator's own timeline.
 * Honest by construction: the marks ARE the craft read's blind spots, not a
 * winner-deviation prediction. */
export default function CraftScrubber({
  durationSeconds,
  marks,
  currentSecond,
  onSeek,
}: {
  durationSeconds: number | null | undefined
  marks: CraftMark[]
  currentSecond?: number
  onSeek?: (second: number) => void
}) {
  const dur = Math.max(1, durationSeconds || 0)
  const pct = (s: number) => `${Math.min(100, Math.max(0, (s / dur) * 100))}%`
  const fmt = (s: number) =>
    `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`

  return (
    <div>
      <div className="mb-2 text-xs text-muted">
        {marks.length > 0
          ? `${marks.length} flagged moment${marks.length > 1 ? 's' : ''} — tap a dot to jump`
          : 'Nothing flagged on the timeline — clean read.'}
      </div>
      <div className="relative h-2.5 w-full rounded-full bg-surface-2">
        {currentSecond != null ? (
          <div
            className="absolute inset-y-0 left-0 rounded-full bg-white/15"
            style={{ width: pct(currentSecond) }}
            aria-hidden
          />
        ) : null}
        {marks.map((m, i) => (
          <button
            key={i}
            type="button"
            onClick={() => onSeek?.(m.second)}
            title={`${fmt(m.second)} — ${m.label}`}
            aria-label={`Jump to ${fmt(m.second)}: ${m.label}`}
            className="absolute top-1/2 h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-ink bg-accent shadow transition-transform hover:scale-125"
            style={{ left: pct(m.second) }}
          />
        ))}
        {currentSecond != null ? (
          <div
            className="pointer-events-none absolute -top-1 -bottom-1 w-0.5 bg-white shadow-[0_0_4px_rgba(255,255,255,0.8)]"
            style={{ left: pct(currentSecond) }}
            aria-hidden
          />
        ) : null}
      </div>
      <div className="mt-1 flex justify-between text-[11px] tabular-nums text-muted">
        <span>0:00</span>
        <span>{fmt(dur)}</span>
      </div>
    </div>
  )
}
