import { useState, type MouseEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, mediaUrl } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import type { UploadCard } from '../api/types'
import CreatorFingerprint from '../components/CreatorFingerprint'
import Spinner from '../components/Spinner'

function fmtDate(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function ReadTile({ u, onDeleted }: { u: UploadCard; onDeleted: (id: string) => void }) {
  const [busy, setBusy] = useState(false)

  async function del(e: MouseEvent) {
    // The tile is a Link — don't navigate when deleting.
    e.preventDefault()
    e.stopPropagation()
    if (busy) return
    if (!window.confirm('Delete this read? It’s removed from your Library, DNA and Growth.')) {
      return
    }
    setBusy(true)
    try {
      await api.deleteUpload(u.video_id)
      onDeleted(u.video_id)
    } catch {
      setBusy(false)
      window.alert('Couldn’t delete that — please try again.')
    }
  }

  return (
    <Link
      to={`/video/${u.video_id}`}
      className="group overflow-hidden rounded-2xl border border-border bg-surface transition-colors hover:border-accent/50"
    >
      <div className="relative aspect-[9/16] bg-surface-2">
        {u.thumbnail_url ? (
          <img
            src={mediaUrl(u.thumbnail_url)}
            alt=""
            loading="lazy"
            onError={(e) => {
              // Hide a broken thumbnail so the dark placeholder shows instead of "?".
              e.currentTarget.onerror = null
              e.currentTarget.style.visibility = 'hidden'
            }}
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
          />
        ) : (
          <div className="grid h-full place-items-center text-xs text-muted">no preview</div>
        )}
        <button
          type="button"
          onClick={del}
          disabled={busy}
          aria-label="Delete this read"
          className="absolute right-1.5 top-1.5 z-10 grid h-7 w-7 place-items-center rounded-full bg-black/55 text-white/90 backdrop-blur-sm transition hover:bg-black/80 active:scale-95 disabled:opacity-50"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m2 0v14a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V6" />
          </svg>
        </button>
        <div className="absolute inset-x-0 bottom-0 flex items-center justify-between bg-gradient-to-t from-black/75 to-transparent p-2.5 text-[11px] text-white/90">
          <span className="tabular-nums">{fmtDate(u.created_at)}</span>
          {u.dimension ? (
            <span className="rounded-full bg-white/15 px-2 py-0.5 font-medium capitalize backdrop-blur-sm">
              {u.dimension}
            </span>
          ) : null}
        </div>
      </div>
      <div className="p-3">
        <p className="line-clamp-1 text-[13px] font-semibold">{u.title}</p>
        {u.available && u.biggest_opportunity ? (
          <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted">
            <span className="font-medium text-accent">Fix: </span>
            {u.biggest_opportunity}
          </p>
        ) : (
          <p className="mt-1 text-xs text-muted/70">
            {u.available ? 'Read ready' : 'No grounded read'}
          </p>
        )}
      </div>
    </Link>
  )
}

export default function MyUploadsPage() {
  // Bump to refetch after a delete (so the grid + fingerprint update).
  const [reload, setReload] = useState(0)
  const uploads = useAsync(() => api.myUploads(), [reload])
  const fp = useAsync(() => api.myFingerprint(), [reload])
  const list = uploads.data?.uploads ?? []
  const onDeleted = () => setReload((n) => n + 1)

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight sm:text-3xl">Your reads</h1>
          <p className="mt-1 text-sm text-muted">
            Every reel you’ve read here — watch your craft sharpen over time.
          </p>
        </div>
        <Link
          to="/analyze"
          className="rounded-xl bg-grad px-4 py-2.5 text-sm font-bold text-white transition-all hover:brightness-110"
        >
          Read another reel
        </Link>
      </div>

      {fp.data?.ready ? <CreatorFingerprint fp={fp.data} /> : null}

      {uploads.loading ? (
        <Spinner label="Loading your reads…" />
      ) : uploads.error ? (
        <p className="rounded-xl border border-bad/40 bg-bad/10 px-4 py-3 text-sm text-bad">
          {uploads.error}
        </p>
      ) : list.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border bg-surface-2/40 px-6 py-14 text-center">
          <div className="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-grad">
            <svg width="22" height="22" viewBox="0 0 22 22" fill="none" className="text-white">
              <path
                d="M11 14.5V5m0 0L7.5 8.5M11 5l3.5 3.5M5 15.5v1A1.5 1.5 0 0 0 6.5 18h9a1.5 1.5 0 0 0 1.5-1.5v-1"
                stroke="currentColor"
                strokeWidth="1.7"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
          <p className="text-[15px] font-semibold">No reads yet</p>
          <p className="mx-auto mt-1 max-w-xs text-sm text-muted">
            Drop your first reel and get a craft read — it’ll show up here.
          </p>
          <Link
            to="/analyze"
            className="mt-5 inline-block rounded-xl bg-grad px-5 py-2.5 text-sm font-bold text-white transition-all hover:brightness-110"
          >
            Read your first reel
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {list.map((u) => (
            <ReadTile key={u.video_id} u={u} onDeleted={onDeleted} />
          ))}
        </div>
      )}
    </div>
  )
}
