import type { Timeline, TimelineSecond } from '../api/types'
import { deviationColor, platformNoun, timestamp } from '../lib/format'

interface Cluster {
  start: number
  end: number
  peakDev: number
  reason: string
}

/** Group consecutive flagged seconds into ranges; return the worst few. */
function clusterFlagged(seconds: TimelineSecond[], max = 3): Cluster[] {
  const flagged = seconds.filter((d) => d.reason)
  if (flagged.length === 0) return []
  const groups: TimelineSecond[][] = [[flagged[0]]]
  for (const d of flagged.slice(1)) {
    const last = groups[groups.length - 1]
    if (d.second - last[last.length - 1].second <= 2) last.push(d)
    else groups.push([d])
  }
  return groups
    .map((g): Cluster => {
      const peak = g.reduce((a, b) =>
        (b.deviation ?? 0) > (a.deviation ?? 0) ? b : a,
      )
      return {
        start: g[0].second,
        end: g[g.length - 1].second,
        peakDev: peak.deviation ?? 0,
        reason: peak.reason ?? '',
      }
    })
    .sort((a, b) => b.peakDev - a.peakDev)
    .slice(0, max)
}

interface TimelineStripProps {
  timeline: Timeline
  /**
   * Current playhead position (floor seconds). When provided, a white vertical
   * marker is drawn over the strip and the current segment is highlighted.
   */
  currentSecond?: number
  /**
   * If provided, segments become clickable and call this with the second.
   * The cluster list also becomes clickable, jumping to the peak second of
   * the cluster.
   */
  onSeek?: (second: number) => void
}

export default function TimelineStrip({
  timeline,
  currentSecond,
  onSeek,
}: TimelineStripProps) {
  const secs = timeline.seconds
  const hasData = secs.some((d) => d.deviation != null)
  const platform = platformNoun(timeline.video_id)

  if (!hasData) {
    return (
      <p className="text-sm text-muted">
        No per-second timeline for this video yet — it may not be timelined, or it
        is music-only with no comparable cohort.
      </p>
    )
  }

  const clusters = clusterFlagged(secs)
  const end = secs[secs.length - 1].second
  const interactive = Boolean(onSeek)

  return (
    <div>
      <p className="mb-3 text-xs leading-relaxed text-muted">
        Where this video diverges from winning {platform} of its archetype, second by
        second — greener tracks winners, redder diverges.{' '}
        {interactive ? (
          <span className="text-text/80">
            Click any segment to jump the video there.
          </span>
        ) : (
          <span className="text-text/80">
            A prediction from niche patterns, not measured audience retention.
          </span>
        )}
      </p>

      <div className="relative">
        <div className="flex h-9 w-full gap-px overflow-hidden rounded-md">
          {secs.map((d) => {
            const isCurrent = currentSecond != null && d.second === currentSecond
            const color = deviationColor(d.deviation)
            const title = `${timestamp(d.second)} · deviation ${
              d.deviation == null ? 'n/a' : d.deviation.toFixed(2)
            }${d.reason ? ` · ${d.reason}` : ''}`
            const className = `flex-1 transition-[filter] ${
              interactive ? 'cursor-pointer hover:brightness-125' : ''
            } ${isCurrent ? 'brightness-150 ring-2 ring-white' : ''}`

            if (interactive) {
              return (
                <button
                  key={d.second}
                  type="button"
                  onClick={() => onSeek!(d.second)}
                  className={className}
                  style={{ backgroundColor: color }}
                  title={title}
                  aria-label={title}
                />
              )
            }
            return (
              <div
                key={d.second}
                className={className}
                style={{ backgroundColor: color }}
                title={title}
              />
            )
          })}
        </div>
        {currentSecond != null && currentSecond >= 0 && currentSecond <= end ? (
          <div
            className="pointer-events-none absolute -top-1 bottom-[-4px] w-0.5 bg-white shadow-[0_0_4px_rgba(255,255,255,0.8)]"
            style={{ left: `${((currentSecond + 0.5) / (end + 1)) * 100}%` }}
            aria-hidden
          />
        ) : null}
      </div>
      <div className="mt-1 flex justify-between text-[11px] tabular-nums text-muted">
        <span>0:00</span>
        <span>{timestamp(Math.floor(end / 2))}</span>
        <span>{timestamp(end)}</span>
      </div>

      <div className="mt-4">
        {clusters.length > 0 ? (
          <>
            <h5 className="text-sm font-semibold">Predicted weak spots</h5>
            <ul className="mt-2 space-y-1.5">
              {clusters.map((c) => {
                const label =
                  c.start === c.end
                    ? timestamp(c.start)
                    : `${timestamp(c.start)}–${timestamp(c.end)}`
                const content = (
                  <>
                    <span className="shrink-0 font-semibold tabular-nums text-mid">
                      {label}
                    </span>
                    <span className="text-muted">{c.reason}</span>
                  </>
                )
                if (interactive) {
                  return (
                    <li key={c.start}>
                      <button
                        type="button"
                        onClick={() => onSeek!(c.start)}
                        className="flex w-full gap-2 rounded px-1 py-0.5 text-left text-sm transition-colors hover:bg-white/5"
                      >
                        {content}
                      </button>
                    </li>
                  )
                }
                return (
                  <li key={c.start} className="flex gap-2 text-sm">
                    {content}
                  </li>
                )
              })}
            </ul>
          </>
        ) : (
          <p className="text-sm text-good">
            No stretch crosses the weak-spot threshold — framing and pacing track
            winning {platform} throughout.
          </p>
        )}
      </div>
    </div>
  )
}
