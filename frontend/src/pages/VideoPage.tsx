import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, videoFileUrl } from '../api/client'
import type { CutSegment } from '../api/types'
import { useAsync } from '../hooks/useAsync'
import { archetypeName, externalUrl, formatDuration, thumbnailUrl } from '../lib/format'
import CategoryPicker from '../components/CategoryPicker'
import Collapsible from '../components/Collapsible'
import CutPlanPanel from '../components/CutPlanPanel'
import Disclaimer from '../components/Disclaimer'
import FindingsTable from '../components/FindingsTable'
import FrameFindings from '../components/FrameFindings'
import Scorecard from '../components/Scorecard'
import Spinner from '../components/Spinner'
import TercileBadge from '../components/TercileBadge'
import TheRead from '../components/TheRead'
import TimelineStrip from '../components/TimelineStrip'
import VideoPlayer from '../components/VideoPlayer'
import WinnerMoves from '../components/WinnerMoves'

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

export default function VideoPage() {
  const { videoId } = useParams<{ videoId: string }>()
  const id = videoId ?? ''

  const breakdown = useAsync(() => api.analyze(id), [id])
  const summary = useAsync(() => api.summary(id), [id])
  const frame = useAsync(() => api.frame(id), [id])
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

  return (
    <div className="space-y-5">
      <BackLink />

      {breakdown.loading ? <Spinner label="Analyzing video…" /> : null}
      {breakdown.error ? <ErrorBox message={breakdown.error} /> : null}

      {b ? (
        <>
          <div className="flex gap-4">
            <a
              href={externalUrl(b.video_id)}
              target="_blank"
              rel="noreferrer"
              className="hidden shrink-0 sm:block"
            >
              <img
                src={thumbnailUrl(b.video_id)}
                alt=""
                className="h-[68px] w-[120px] rounded-lg object-cover"
              />
            </a>
            <div className="min-w-0">
              <h1 className="text-xl font-semibold leading-tight">{b.title}</h1>
              <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted">
                <span>{b.channel}</span>
                <span aria-hidden>·</span>
                <span>{formatDuration(b.duration_seconds)}</span>
                <span aria-hidden>·</span>
                <span>{archetypeName(b.archetype)}</span>
                <TercileBadge tercile={b.tercile} />
                <span aria-hidden>·</span>
                <CategoryPicker
                  videoId={id}
                  onChange={() => setCategoryVersion((v) => v + 1)}
                />
              </div>
            </div>
          </div>

          {/* The centerpiece: video + synchronized scrubbable timeline.
              Click any timeline segment to jump the video; the playhead
              indicator on the strip tracks playback. */}
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
              {timeline.loading ? (
                <Spinner label="Loading timeline…" />
              ) : timeline.error ? (
                <ErrorBox message={timeline.error} />
              ) : timeline.data ? (
                <TimelineStrip
                  timeline={timeline.data}
                  currentSecond={currentSecond}
                  onSeek={handleSeek}
                />
              ) : null}
            </div>
          </div>

          <CutPlanPanel
            videoId={b.video_id}
            categoryVersion={categoryVersion}
            onSeek={handleSeek}
            onPlayWinnerCut={handlePlayWinnerCut}
            currentSecond={currentSecond}
          />

          <Scorecard b={b} />

          <WinnerMoves b={b} />

          {summary.loading ? (
            <div className="rounded-2xl border border-border bg-surface p-6">
              <Spinner label="Writing the read…" />
            </div>
          ) : summary.error ? (
            <ErrorBox message={summary.error} />
          ) : summary.data ? (
            <TheRead s={summary.data} />
          ) : null}

          <div className="space-y-2.5">
            <Collapsible
              title="Feature comparison"
              subtitle="this video vs winning Shorts"
            >
              <FindingsTable videoId={b.video_id} findings={b.findings} />
            </Collapsible>

            <Collapsible title="Hook & pacing" subtitle="frame-level breakdown">
              {frame.loading ? (
                <Spinner label="Loading…" />
              ) : frame.error ? (
                <ErrorBox message={frame.error} />
              ) : frame.data ? (
                <FrameFindings fb={frame.data} />
              ) : null}
            </Collapsible>
          </div>

          <Disclaimer className="pt-1" />
        </>
      ) : null}
    </div>
  )
}
