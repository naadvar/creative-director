import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, videoFileUrl } from '../api/client'
import type { CutSegment } from '../api/types'
import { useAsync } from '../hooks/useAsync'
import { externalUrl, formatDuration, thumbnailUrl } from '../lib/format'
import CategoryPicker from '../components/CategoryPicker'
import Collapsible from '../components/Collapsible'
import CraftRead from '../components/CraftRead'
import CraftScrubber, { type CraftMark } from '../components/CraftScrubber'
import CutPlanPanel from '../components/CutPlanPanel'
import Scorecard from '../components/Scorecard'
import Spinner from '../components/Spinner'
import TheRead from '../components/TheRead'
import TimelineStrip from '../components/TimelineStrip'
import VideoPlayer from '../components/VideoPlayer'

function BackLink() {
  return (
    <Link
      to="/"
      className="inline-flex items-center gap-1.5 text-sm text-muted transition-colors hover:text-text"
    >
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
        <path
          d="M8.5 3 4.5 7l4 4"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      Back to corpus
    </Link>
  )
}

function ErrorBox({ message }: { message: string }) {
  return (
    <p className="rounded-xl border border-bad/40 bg-bad/10 px-4 py-3 text-sm text-bad">
      {message}
    </p>
  )
}

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

export default function VideoPage() {
  const { videoId } = useParams<{ videoId: string }>()
  const id = videoId ?? ''

  const breakdown = useAsync(() => api.analyze(id), [id])
  const craft = useAsync(() => api.craftRead(id), [id])
  const summary = useAsync(() => api.summary(id), [id])
  const timeline = useAsync(() => api.timeline(id), [id])

  // Bidirectional sync between the video player and the timeline strip.
  // currentSecond is updated as the player advances; clicking a timeline
  // segment increments seekToken so the player effect-jumps to seekTo.
  const [currentSecond, setCurrentSecond] = useState(0)
  const [seekTo, setSeekTo] = useState<number | undefined>(undefined)
  const [seekToken, setSeekToken] = useState(0)
  // Bumped when the creator overrides the content category, so category-aware
  // panels (the cut plan's "vs X winners") refetch against the new cohort.
  const [categoryVersion, setCategoryVersion] = useState(0)
  // The "winner cut" virtual edit: kept segments + a nonce to (re)start playback.
  const [edl, setEdl] = useState<CutSegment[] | undefined>(undefined)
  const [edlNonce, setEdlNonce] = useState(0)
  const handleSeek = (second: number) => {
    setSeekTo(second)
    setSeekToken((t) => t + 1)
  }
  const handlePlayWinnerCut = (segments: CutSegment[]) => {
    setEdl(segments)
    setEdlNonce((n) => n + 1)
  }

  const b = breakdown.data
  const marks = parseCraftMarks(craft.data?.read?.blind_spots)

  return (
    <div className="space-y-5">
      <BackLink />

      {breakdown.loading ? <Spinner label="Analyzing video…" /> : null}
      {breakdown.error ? <ErrorBox message={breakdown.error} /> : null}

      {b ? (
        <>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h1 className="text-xl font-bold leading-tight tracking-tight sm:text-2xl">
                {b.title}
              </h1>
              <div className="mt-1 flex items-center gap-x-2 text-sm text-muted">
                <span className="truncate">{b.channel}</span>
                <span aria-hidden>·</span>
                <span className="shrink-0 tabular-nums">{formatDuration(b.duration_seconds)}</span>
              </div>
            </div>
            {externalUrl(b.video_id) ? (
              <a
                href={externalUrl(b.video_id)}
                target="_blank"
                rel="noreferrer"
                className="inline-flex shrink-0 items-center gap-1 pt-1 text-xs text-muted transition-colors hover:text-text"
              >
                Original
                <svg width="11" height="11" viewBox="0 0 12 12" fill="none">
                  <path
                    d="M4.5 2.5h5v5M9.5 2.5 4 8"
                    stroke="currentColor"
                    strokeWidth="1.3"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </a>
            ) : null}
          </div>

          {/* The centerpiece: the video, with the craft read's flagged moments
              marked on the scrubber. Tap a dot (or any timestamp in the read) to
              jump there — the read annotates the creator's own footage. */}
          <div className="rounded-2xl border border-border bg-surface p-4 sm:p-5">
            <VideoPlayer
              src={videoFileUrl(b.video_id)}
              poster={thumbnailUrl(b.video_id)}
              seekToken={seekToken}
              seekTo={seekTo}
              edl={edl}
              edlNonce={edlNonce}
              onTimeUpdate={setCurrentSecond}
            />
            <div className="mt-4">
              <CraftScrubber
                durationSeconds={b.duration_seconds}
                marks={marks}
                currentSecond={currentSecond}
                onSeek={handleSeek}
              />
            </div>
          </div>

          {/* The craft read is the hero: the first analysis after the video, and
              every timestamp is tap-verifiable against their own footage. */}
          {craft.data?.available && craft.data.read ? (
            <CraftRead data={craft.data.read} onSeek={handleSeek} videoId={id} />
          ) : null}

          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted">
            <span className="text-[11px] font-semibold uppercase tracking-wider">Content type</span>
            <CategoryPicker videoId={id} onChange={() => setCategoryVersion((v) => v + 1)} />
            <span className="text-xs text-muted/70">— sets the winners it&apos;s compared to</span>
          </div>

          <CutPlanPanel
            videoId={b.video_id}
            categoryVersion={categoryVersion}
            onSeek={handleSeek}
            onPlayWinnerCut={handlePlayWinnerCut}
            currentSecond={currentSecond}
          />

          <div className="space-y-2.5">
            {/* The scalar scorecard + benchmark read — preserved, but demoted below
                the craft read so the page speaks with one honest voice. */}
            <Collapsible
              title="Scorecard & benchmark read"
              subtitle="how it compares to same-size winners — correlational, not a verdict"
            >
              <div className="space-y-4">
                <Scorecard b={b} />
                {summary.loading ? (
                  <Spinner label="Writing the read…" />
                ) : summary.error ? (
                  <ErrorBox message={summary.error} />
                ) : summary.data ? (
                  <TheRead s={summary.data} />
                ) : null}
                {timeline.data ? (
                  <TimelineStrip
                    timeline={timeline.data}
                    currentSecond={currentSecond}
                    onSeek={handleSeek}
                  />
                ) : null}
              </div>
            </Collapsible>
          </div>
        </>
      ) : null}
    </div>
  )
}
