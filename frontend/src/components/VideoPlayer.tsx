import { useEffect, useRef } from 'react'
import type { CutSegment } from '../api/types'

interface VideoPlayerProps {
  /** URL pointing to the streamed mp4 (e.g. /api/videos/{id}/file). */
  src: string
  /** Optional poster image (thumbnail) shown before playback starts. */
  poster?: string
  /**
   * Imperative seek trigger -- when this value changes the player jumps to
   * `seekTo` seconds and (best-effort) starts playing. Use a monotonically
   * increasing token from the parent so that two clicks on the same second
   * still trigger a re-seek.
   */
  seekToken?: number
  seekTo?: number
  /**
   * Edit decision list for the "winner cut" preview: a list of kept
   * [start, end) segments (seconds). When `edlNonce` changes, the player
   * plays only these segments, auto-jumping the removed gaps. A manual seek
   * (seekToken) or the user scrubbing the native control cancels EDL playback.
   */
  edl?: CutSegment[]
  edlNonce?: number
  /** Fired when EDL playback reaches the end of the last kept segment. */
  onEdlEnd?: () => void
  /**
   * Fires as playback progresses. `second` is the floored current time so
   * downstream components (e.g. the timeline strip) only re-render on
   * second-boundaries, not 4x/sec.
   */
  onTimeUpdate?: (second: number) => void
}

export default function VideoPlayer({
  src,
  poster,
  seekToken,
  seekTo,
  edl,
  edlNonce,
  onEdlEnd,
  onTimeUpdate,
}: VideoPlayerProps) {
  const ref = useRef<HTMLVideoElement>(null)
  const lastReportedSecond = useRef<number>(-1)
  // EDL playback state kept in a ref so segment-hopping doesn't re-render.
  const edlState = useRef<{ segs: CutSegment[]; idx: number; active: boolean }>({
    segs: [],
    idx: 0,
    active: false,
  })
  // True while an EDL-initiated seek is in flight, so we can tell our own seeks
  // apart from the user grabbing the scrubber.
  const edlSeeking = useRef(false)
  const rafRef = useRef<number | null>(null)

  // Frame-accurate segment hopping: a rAF loop (~16ms) watches the playhead and
  // jumps the removed gaps the instant a kept segment ends — far tighter than
  // the ~250ms `timeupdate` event, so no removed footage flashes at a cut.
  const runEdlLoop = () => {
    const tick = () => {
      const v = ref.current
      const st = edlState.current
      if (!v || !st.active) {
        rafRef.current = null
        return
      }
      const seg = st.segs[st.idx]
      if (v.currentTime >= seg.end - 0.02) {
        if (st.idx + 1 < st.segs.length) {
          st.idx += 1
          edlSeeking.current = true
          v.currentTime = st.segs[st.idx].start
        } else {
          st.active = false
          v.pause()
          onEdlEnd?.()
          rafRef.current = null
          return
        }
      }
      rafRef.current = requestAnimationFrame(tick)
    }
    if (rafRef.current == null) rafRef.current = requestAnimationFrame(tick)
  }

  // Arm EDL playback when the parent bumps edlNonce.
  useEffect(() => {
    const v = ref.current
    if (!v || !edl || edl.length === 0) return
    edlState.current = { segs: edl, idx: 0, active: true }
    edlSeeking.current = true
    v.currentTime = edl[0].start
    void v.play().catch(() => {})
    runEdlLoop()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [edlNonce])

  // Cancel the rAF loop on unmount.
  useEffect(() => {
    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current)
    }
  }, [])

  // Imperative seek when seekToken changes -- and cancel any EDL playback,
  // since an explicit jump means the user left the winner-cut preview.
  useEffect(() => {
    const v = ref.current
    if (!v || seekTo == null) return
    edlState.current.active = false
    v.currentTime = seekTo
    void v.play().catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seekToken])

  return (
    <div className="overflow-hidden rounded-2xl border border-border bg-black">
      <video
        ref={ref}
        src={src}
        controls
        poster={poster}
        playsInline
        preload="metadata"
        className="mx-auto block max-h-[48vh] w-auto max-w-full sm:max-h-[70vh]"
        onSeeked={() => {
          // Our own EDL hop seeks set the flag; anything else is the user
          // scrubbing, which exits the winner-cut preview.
          if (edlSeeking.current) {
            edlSeeking.current = false
            return
          }
          edlState.current.active = false
        }}
        onTimeUpdate={(e) => {
          // Segment hopping is handled by the rAF loop; here we only report the
          // floored second to the parent for the timeline playhead.
          if (!onTimeUpdate) return
          const sec = Math.floor(e.currentTarget.currentTime)
          if (sec !== lastReportedSecond.current) {
            lastReportedSecond.current = sec
            onTimeUpdate(sec)
          }
        }}
      />
    </div>
  )
}
