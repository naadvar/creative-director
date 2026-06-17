import { Link } from 'react-router-dom'
import type { PlainSummary, WatchWinner } from '../api/types'
import { formatDuration, thumbnailUrl } from '../lib/format'

function CheckIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 14 14"
      fill="none"
      className="mt-0.5 shrink-0 text-good"
    >
      <path
        d="M2.5 7.5 5.5 10.5 11.5 3.5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function ArrowIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 14 14"
      fill="none"
      className="mt-0.5 shrink-0 text-accent"
    >
      <path
        d="M2.5 7h9M7.5 3l4 4-4 4"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/** Eye glyph for the "what we noticed" observation block. */
function EyeIcon() {
  return (
    <svg
      width="13"
      height="13"
      viewBox="0 0 14 14"
      fill="none"
      className="shrink-0 text-mid"
    >
      <path
        d="M1 7s2.2-4 6-4 6 4 6 4-2.2 4-6 4-6-4-6-4Z"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="7" cy="7" r="1.6" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  )
}

/** A single clickable winning reel — same routing the example cards use:
 * navigate to that reel's own analysis page. */
function WinnerCard({ w }: { w: WatchWinner }) {
  return (
    <Link
      to={`/video/${w.video_id}`}
      className="group flex shrink-0 flex-col gap-1.5 rounded-lg border border-border bg-surface-2 p-2.5 transition-colors hover:border-accent/50"
      style={{ width: 160 }}
    >
      <div className="aspect-[9/12] overflow-hidden rounded-md bg-surface">
        <img
          src={thumbnailUrl(w.video_id)}
          alt=""
          loading="lazy"
          className="h-full w-full object-cover transition-transform group-hover:scale-105"
        />
      </div>
      <div className="min-w-0 leading-tight">
        <div className="truncate text-xs font-medium" title={w.title}>
          {w.title}
        </div>
        <div className="truncate text-[11px] text-muted" title={w.channel}>
          {w.channel}
        </div>
        {w.duration_seconds != null ? (
          <div className="mt-1 text-[11px] text-muted">
            {formatDuration(w.duration_seconds)}
          </div>
        ) : null}
      </div>
    </Link>
  )
}

export default function TheRead({ s }: { s: PlainSummary }) {
  // Proxy items are weak signals — never surface them as advice.
  const advice = s.worth_trying.filter((x) => !x.is_proxy)
  const winners = s.watch_winners ?? []
  const notes = s.craft_notes ?? []

  return (
    <div className="rounded-2xl border border-border bg-surface p-5 sm:p-6">
      <h3 className="text-xs font-semibold uppercase tracking-widest text-muted">
        The read
      </h3>
      <p className="mt-2 text-lg leading-relaxed">{s.read}</p>

      {notes.length > 0 ? (
        <div className="mt-5 rounded-xl border border-mid/30 bg-mid/10 p-4">
          <div className="flex items-center gap-2">
            <EyeIcon />
            <h4 className="text-xs font-semibold uppercase tracking-widest text-mid">
              What we noticed
            </h4>
          </div>
          <ul className="mt-3 space-y-3.5">
            {notes.map((n, i) => (
              <li key={i} className="text-sm leading-relaxed">
                <p>{n.note}</p>
                {n.evidence ? (
                  <p className="mt-1 border-l-2 border-mid/40 pl-3 text-[13px] italic leading-relaxed text-muted">
                    {n.evidence}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {advice.length > 0 ? (
        <div className="mt-5">
          <h4 className="text-sm font-semibold">
            Worth trying{' '}
            <span className="font-normal text-muted">
              — patterns winners share, not guarantees
            </span>
          </h4>
          <ul className="mt-2.5 space-y-2">
            {advice.map((x, i) => (
              <li key={i} className="flex gap-2.5 text-sm leading-relaxed">
                <ArrowIcon />
                <span>{x.text}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {s.strengths.length > 0 ? (
        <div className="mt-5">
          <h4 className="text-sm font-semibold">Already working</h4>
          <ul className="mt-2.5 space-y-2">
            {s.strengths.map((x, i) => (
              <li
                key={i}
                className="flex gap-2.5 text-sm leading-relaxed text-muted"
              >
                <CheckIcon />
                <span>{x}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {winners.length > 0 ? (
        <div className="mt-6 border-t border-border pt-5">
          <h4 className="text-sm font-semibold">
            {s.watch_winners_label ?? 'Watch these winners'}
          </h4>
          <p className="mt-0.5 text-xs text-muted">
            Real reels winning in your lane — patterns to study, not guarantees.
          </p>
          <div className="mt-3 flex gap-2.5 overflow-x-auto pb-1">
            {winners.slice(0, 3).map((w) => (
              <WinnerCard key={w.video_id} w={w} />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  )
}
