import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, videoFileUrl } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import { formatDuration, thumbnailUrl } from '../lib/format'
import CraftRead from '../components/CraftRead'
import CraftScrubber, { type CraftMark } from '../components/CraftScrubber'
import ShareCard from '../components/ShareCard'
import Spinner from '../components/Spinner'
import VideoPlayer from '../components/VideoPlayer'

/** Pull "m:ss" + observation out of each craft-read blind spot so they can be
 * placed as markers on the scrubber. */
function parseCraftMarks(blindSpots: string[] | undefined): CraftMark[] {
  const out: CraftMark[] = []
  for (const s of blindSpots ?? []) {
    const m = s.match(/^\s*(\d{1,2}):(\d{2})/)
    if (!m) continue
    const second = parseInt(m[1], 10) * 60 + parseInt(m[2], 10)
    let label = s.replace(/^\s*\d{1,2}:\d{2}\s*[-–—]?\s*/, '')
    const fi = label.search(/\bfix:/i)
    if (fi >= 0) label = label.slice(0, fi)
    out.push({ second, label: label.trim().replace(/[.\s]+$/, '') })
  }
  return out
}

function ShareIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
      <path
        d="M11 5.5 8 2.5 5 5.5M8 2.5v8M3.5 9v3.5A1 1 0 0 0 4.5 13.5h7a1 1 0 0 0 1-1V9"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/** A read of one reel: the video with its flagged moments, the craft read, share,
 * and a clear next step — never a dead end. */
export default function VideoPage() {
  const { videoId } = useParams<{ videoId: string }>()
  const id = videoId ?? ''
  const craft = useAsync(() => api.craftRead(id), [id])
  // Only an upload has a creator DNA worth nudging toward.
  const fp = useAsync(() => (id.startsWith('up') ? api.myFingerprint() : Promise.resolve(null)), [id])

  const [currentSecond, setCurrentSecond] = useState(0)
  const [seekTo, setSeekTo] = useState<number | undefined>(undefined)
  const [seekToken, setSeekToken] = useState(0)
  const [showShare, setShowShare] = useState(false)
  const handleSeek = (second: number) => {
    setSeekTo(second)
    setSeekToken((t) => t + 1)
  }

  const meta = craft.data?.meta ?? null
  const read = craft.data?.available ? craft.data.read : undefined
  const isUpload = meta?.is_upload ?? id.startsWith('up')
  const marks = parseCraftMarks(read?.blind_spots)
  const duration = meta?.duration_seconds ?? null

  return (
    <div className="space-y-5">
      {craft.loading ? <Spinner label="Loading your read…" /> : null}
      {craft.error ? (
        <p className="rounded-xl border border-bad/40 bg-bad/10 px-4 py-3 text-sm text-bad">
          {craft.error}
        </p>
      ) : null}

      {!craft.loading && !craft.error ? (
        <>
          <div className="min-w-0">
            <h1 className="text-xl font-bold leading-tight tracking-tight sm:text-2xl">
              {meta?.title ?? 'Reel'}
            </h1>
            <div className="mt-1 flex items-center gap-x-2 text-sm text-muted">
              {meta?.channel ? (
                <>
                  <span className="truncate">{meta.channel}</span>
                  <span aria-hidden>·</span>
                </>
              ) : null}
              <span className="shrink-0 tabular-nums">{formatDuration(duration)}</span>
            </div>
          </div>

          {/* The video, with the craft read's flagged moments marked on the
              scrubber — tap a dot (or any timestamp in the read) to jump there. */}
          <div className="rounded-2xl border border-border bg-surface p-4 sm:p-5">
            <VideoPlayer
              src={videoFileUrl(id)}
              poster={thumbnailUrl(id)}
              seekToken={seekToken}
              seekTo={seekTo}
              onTimeUpdate={setCurrentSecond}
            />
            {marks.length > 0 ? (
              <div className="mt-4">
                <CraftScrubber
                  durationSeconds={duration}
                  marks={marks}
                  currentSecond={currentSecond}
                  onSeek={handleSeek}
                />
              </div>
            ) : null}
          </div>

          {isUpload ? (
            <div className="flex flex-wrap items-center justify-center gap-x-2 gap-y-1 rounded-2xl border border-accent/30 bg-accent/[0.07] px-4 py-3 text-center text-sm">
              <span className="font-semibold">✨ Your craft read is ready</span>
              {fp.data && fp.data.ready && fp.data.n_reels < 3 ? (
                <span className="text-muted">
                  · {fp.data.n_reels} of 3 read — {3 - fp.data.n_reels} more unlocks your{' '}
                  <Link to="/my-dna" className="text-accent hover:underline">
                    Creator DNA
                  </Link>
                </span>
              ) : null}
            </div>
          ) : null}

          {read ? (
            <CraftRead data={read} onSeek={handleSeek} videoId={id} />
          ) : (
            <p className="rounded-xl border border-border bg-surface px-4 py-3 text-sm text-muted">
              {craft.data?.suppressed
                ? 'No grounded read for this one — the model wasn’t confident enough to critique it honestly.'
                : 'The read for this reel isn’t ready yet.'}
            </p>
          )}

          {/* Next step — never a dead end. */}
          <div className="flex flex-wrap items-center gap-2.5 pt-1">
            {read ? (
              <button
                type="button"
                onClick={() => setShowShare(true)}
                className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface px-4 py-2.5 text-sm font-semibold text-muted transition-colors hover:border-accent/50 hover:text-text"
              >
                <ShareIcon />
                Share this read
              </button>
            ) : null}
            {isUpload ? (
              <>
                <Link
                  to="/analyze"
                  className="rounded-xl bg-grad px-4 py-2.5 text-sm font-bold text-white transition-all hover:brightness-110"
                >
                  Read another reel
                </Link>
                <Link
                  to="/my-reads"
                  className="rounded-xl border border-border bg-surface px-4 py-2.5 text-sm font-semibold text-muted transition-colors hover:text-text"
                >
                  My reads
                </Link>
                <Link
                  to="/my-dna"
                  className="rounded-xl border border-border bg-surface px-4 py-2.5 text-sm font-semibold text-muted transition-colors hover:text-text"
                >
                  My Creator DNA
                </Link>
              </>
            ) : (
              <Link
                to="/browse"
                className="rounded-xl border border-border bg-surface px-4 py-2.5 text-sm font-semibold text-muted transition-colors hover:text-text"
              >
                Browse more examples
              </Link>
            )}
          </div>

          {showShare && read && meta ? (
            <ShareCard
              read={read}
              title={meta.title}
              durationLabel={formatDuration(duration)}
              onClose={() => setShowShare(false)}
            />
          ) : null}
        </>
      ) : null}
    </div>
  )
}
