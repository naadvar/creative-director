import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { ApiError } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import { useInstagram } from '../hooks/useAuth'
import type { ReelCard } from '../api/types'
import { tercileStyle } from '../lib/format'
import Spinner from '../components/Spinner'

const GRADE_LABEL: Record<number, string> = { 2: 'High', 1: 'Mid', 0: 'Low' }

function ReelTile({
  reel,
  onAnalyze,
  busy,
}: {
  reel: ReelCard
  onAnalyze: (id: string) => void
  busy: boolean
}) {
  return (
    <div className="group overflow-hidden rounded-xl border border-border bg-surface">
      <div className="relative aspect-[9/16] bg-surface-2">
        {reel.thumbnail_url ? (
          <img
            src={reel.thumbnail_url}
            alt=""
            loading="lazy"
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="grid h-full place-items-center text-xs text-muted">no thumbnail</div>
        )}
        {reel.tercile != null ? (
          (() => {
            const st = tercileStyle(reel.tercile)
            return (
              <div
                className={`absolute left-2 top-2 flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] font-semibold backdrop-blur-sm ${st.bg} ${st.text} ${st.border}`}
                title={st.name}
              >
                <span className={`h-1.5 w-1.5 rounded-full ${st.dot}`} />
                {GRADE_LABEL[reel.tercile] ?? '—'}
              </div>
            )
          })()
        ) : null}
        <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 to-transparent p-2.5 text-[11px] text-white/90">
          {reel.like_count != null ? `♥ ${reel.like_count.toLocaleString()}` : ''}
          {reel.comments_count != null ? `   💬 ${reel.comments_count.toLocaleString()}` : ''}
        </div>
      </div>
      <div className="p-3">
        <p className="line-clamp-2 h-9 text-xs text-muted" title={reel.caption}>
          {reel.caption || '—'}
        </p>
        <div className="mt-2 flex items-center gap-2">
          {reel.video_id ? (
            <Link
              to={`/video/${reel.video_id}`}
              className="flex-1 rounded-lg bg-accent px-3 py-1.5 text-center text-xs font-semibold text-ink transition-transform hover:scale-[1.02]"
            >
              View analysis
            </Link>
          ) : (
            <button
              type="button"
              disabled={busy}
              onClick={() => onAnalyze(reel.id)}
              className="flex-1 rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-ink transition-transform hover:scale-[1.02] disabled:opacity-50"
            >
              {busy ? 'Analyzing…' : 'Analyze'}
            </button>
          )}
          {reel.permalink ? (
            <a
              href={reel.permalink}
              target="_blank"
              rel="noreferrer"
              className="rounded-lg border border-border px-2.5 py-1.5 text-xs text-muted hover:text-text"
            >
              View
            </a>
          ) : null}
        </div>
      </div>
    </div>
  )
}

export default function MyReelsPage() {
  const { connected, username } = useInstagram()
  const reels = useAsync(() => api.myReels(), [connected])
  const navigate = useNavigate()
  const [busyId, setBusyId] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)

  async function analyze(id: string) {
    setBusyId(id)
    setErr(null)
    try {
      const { video_id } = await api.analyzeOwnReel(id)
      navigate(`/video/${video_id}`)
    } catch (e) {
      setErr(
        e instanceof ApiError ? e.message : 'Analysis failed — please try again.',
      )
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold">Your Reels</h1>
        <p className="mt-1 text-sm text-muted">
          {username ? `@${username}` : 'Connected'} · pick a Reel to get its read.
        </p>
      </div>

      {err ? (
        <p className="rounded-xl border border-bad/40 bg-bad/10 px-4 py-3 text-sm text-bad">
          {err}
        </p>
      ) : null}

      {reels.loading ? (
        <Spinner label="Loading your Reels…" />
      ) : reels.error ? (
        <p className="rounded-xl border border-bad/40 bg-bad/10 px-4 py-3 text-sm text-bad">
          {reels.error}
        </p>
      ) : reels.data && reels.data.reels.length > 0 ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {reels.data.reels.map((r) => (
            <ReelTile key={r.id} reel={r} onAnalyze={analyze} busy={busyId === r.id} />
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted">
          No Reels found on this account yet.
        </p>
      )}
    </div>
  )
}
