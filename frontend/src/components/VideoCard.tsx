import { Link } from 'react-router-dom'
import type { CorpusVideo } from '../api/types'
import { formatDuration, tercileStyle, thumbnailUrl } from '../lib/format'

export default function VideoCard({ v }: { v: CorpusVideo }) {
  const s = tercileStyle(v.tercile)
  return (
    <Link
      to={`/video/${v.video_id}`}
      className="group overflow-hidden rounded-xl border border-border bg-surface transition-colors hover:border-accent/50"
    >
      <div className="relative aspect-video bg-ink">
        <img
          src={v.thumbnail_url ?? thumbnailUrl(v.video_id)}
          alt=""
          loading="lazy"
          onError={(e) => {
            e.currentTarget.onerror = null
            e.currentTarget.src = thumbnailUrl(v.video_id)
          }}
          className="h-full w-full object-cover opacity-90 transition-opacity group-hover:opacity-100"
        />
        <span className="absolute bottom-1.5 right-1.5 rounded bg-black/75 px-1.5 py-0.5 text-[11px] font-medium tabular-nums">
          {formatDuration(v.duration_seconds)}
        </span>
      </div>
      <div className="p-3">
        <p className="line-clamp-2 min-h-[2.5rem] text-sm font-medium leading-tight">
          {v.title}
        </p>
        <div className="mt-2 flex items-center justify-between gap-2">
          <span className="truncate text-xs text-muted">{v.channel}</span>
          {v.tercile != null ? (
            <span
              className={`shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${s.bg} ${s.text}`}
            >
              {s.name.split(' ')[0]}
            </span>
          ) : null}
        </div>
      </div>
    </Link>
  )
}
