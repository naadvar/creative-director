import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import Spinner from '../components/Spinner'

const NICHES = [
  { key: 'ig_fitness', label: 'Fitness' },
  { key: 'ig_food', label: 'Food' },
  { key: 'ig_travel', label: 'Travel' },
  { key: 'ig_fashion', label: 'Fashion' },
]

const MAX_BYTES = 200 * 1024 * 1024

function fmtSize(bytes: number): string {
  return bytes < 1024 * 1024
    ? `${Math.round(bytes / 1024)} KB`
    : `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/** Home: upload a reel -> full analysis vs the niche's winners. */
export default function UploadPage() {
  const navigate = useNavigate()
  const inputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [niche, setNiche] = useState<string>('ig_fitness')
  const [caption, setCaption] = useState('')
  const [followers, setFollowers] = useState('')
  const [dragging, setDragging] = useState(false)
  const [phase, setPhase] = useState<'idle' | 'uploading' | 'analyzing'>('idle')
  const [message, setMessage] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [corpusTotal, setCorpusTotal] = useState<number | null>(null)
  const cancelled = useRef(false)

  useEffect(() => {
    api
      .niches()
      .then((r) =>
        setCorpusTotal(
          r.niches
            .filter((n) => n.platform === 'instagram')
            .reduce((sum, n) => sum + n.count, 0),
        ),
      )
      .catch(() => {})
    return () => {
      cancelled.current = true
    }
  }, [])

  const pick = (f: File | undefined | null) => {
    setError(null)
    if (!f) return
    if (f.size > MAX_BYTES) {
      setError('That file is over 200 MB — export a smaller cut (short-form only).')
      return
    }
    setFile(f)
  }

  const submit = async () => {
    if (!file || phase !== 'idle') return
    setError(null)
    setPhase('uploading')
    setMessage('uploading your reel…')
    try {
      const job = await api.upload(
        file,
        niche,
        caption,
        followers ? parseInt(followers, 10) : undefined,
      )
      setPhase('analyzing')
      // Poll until done — extraction takes ~2-3 minutes.
      for (;;) {
        await new Promise((r) => setTimeout(r, 3000))
        if (cancelled.current) return
        const st = await api.uploadStatus(job.job_id)
        setMessage(st.message)
        if (st.status === 'done') {
          navigate(`/video/${st.video_id}`)
          return
        }
        if (st.status === 'error') {
          throw new Error(st.error ?? 'analysis failed')
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'upload failed')
      setPhase('idle')
    }
  }

  const busy = phase !== 'idle'

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div className="space-y-2 pt-4 text-center">
        <h1 className="text-2xl font-semibold leading-tight sm:text-3xl">
          Get a craft read of your reel
        </h1>
        <p className="mx-auto max-w-xl text-sm leading-relaxed text-muted">
          Upload a reel — even a draft you haven&apos;t posted — and the model
          watches it frame by frame: the hook, the payoff, pacing, framing, and
          every on-screen text beat, then flags the craft blind spots you&apos;re
          too close to notice.
          {corpusTotal ? (
            <>
              {' '}
              Drawing on <span className="text-text">{corpusTotal.toLocaleString()}</span>{' '}
              analyzed reels.
            </>
          ) : null}
        </p>
      </div>

      <div className="space-y-4 rounded-2xl border border-border bg-surface p-5 sm:p-6">
        {/* Drop zone */}
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault()
            setDragging(false)
            pick(e.dataTransfer.files?.[0])
          }}
          disabled={busy}
          className={`flex w-full flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-4 py-10 text-center transition-colors disabled:opacity-60 ${
            dragging
              ? 'border-accent bg-accent/10'
              : file
                ? 'border-good/50 bg-good/5'
                : 'border-border bg-surface-2 hover:border-accent/60'
          }`}
        >
          {file ? (
            <>
              <span className="text-sm font-semibold">{file.name}</span>
              <span className="text-xs text-muted">
                {fmtSize(file.size)} · click to swap it
              </span>
            </>
          ) : (
            <>
              <span className="text-sm font-semibold">
                Drop your reel here, or tap to choose
              </span>
              <span className="text-xs text-muted">
                mp4 / mov · up to 3 minutes · stays private, never published
              </span>
            </>
          )}
          <input
            ref={inputRef}
            type="file"
            accept="video/mp4,video/quicktime"
            aria-label="Choose a reel video file"
            className="sr-only"
            onChange={(e) => pick(e.target.files?.[0])}
          />
        </button>

        {/* Niche picker */}
        <div>
          <div className="mb-1.5 text-xs font-semibold uppercase tracking-widest text-muted">
            Your niche
          </div>
          <div className="flex flex-wrap gap-2">
            {NICHES.map((n) => (
              <button
                key={n.key}
                type="button"
                disabled={busy}
                onClick={() => setNiche(n.key)}
                className={`rounded-full border px-4 py-1.5 text-sm transition-colors disabled:opacity-60 ${
                  niche === n.key
                    ? 'border-accent bg-accent/15 text-text'
                    : 'border-border bg-surface-2 text-muted hover:text-text'
                }`}
              >
                {n.label}
              </button>
            ))}
          </div>
        </div>

        {/* Caption + followers */}
        <div className="grid gap-3 sm:grid-cols-[1fr_180px]">
          <div>
            <div className="mb-1.5 text-xs font-semibold uppercase tracking-widest text-muted">
              Caption <span className="font-normal normal-case">(optional — emoji &amp; hashtags affect the read)</span>
            </div>
            <textarea
              value={caption}
              onChange={(e) => setCaption(e.target.value)}
              disabled={busy}
              rows={2}
              placeholder="Paste the caption you'd post with it…"
              className="w-full resize-none rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm outline-none transition-colors placeholder:text-muted/60 focus:border-accent disabled:opacity-60"
            />
          </div>
          <div>
            <div className="mb-1.5 text-xs font-semibold uppercase tracking-widest text-muted">
              Followers <span className="font-normal normal-case">(optional)</span>
            </div>
            <input
              value={followers}
              onChange={(e) => setFollowers(e.target.value.replace(/[^0-9]/g, ''))}
              disabled={busy}
              inputMode="numeric"
              placeholder="e.g. 12000"
              className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm outline-none transition-colors placeholder:text-muted/60 focus:border-accent disabled:opacity-60"
            />
            <div className="mt-1 text-[11px] leading-snug text-muted">
              compares you to similar-size creators
            </div>
          </div>
        </div>

        {/* Submit / progress */}
        {busy ? (
          <div className="flex items-center gap-3 rounded-xl border border-accent/30 bg-accent/5 px-4 py-3">
            <Spinner label="" />
            <div className="min-w-0">
              <div className="text-sm font-semibold">{message || 'working…'}</div>
              <div className="text-xs text-muted">
                full analysis takes ~2–3 minutes — keep this tab open
              </div>
            </div>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => void submit()}
            disabled={!file}
            className="w-full rounded-xl bg-accent px-4 py-3 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {file ? 'Analyze my reel' : 'Choose a reel to analyze'}
          </button>
        )}

        {error ? (
          <p className="rounded-xl border border-bad/40 bg-bad/10 px-4 py-3 text-sm text-bad">
            {error}
          </p>
        ) : null}
      </div>

      <p className="text-center text-xs leading-relaxed text-muted">
        Your video is analyzed on the spot and never shared or published.
        Comparisons are correlational — patterns winners share, not guarantees.
      </p>
    </div>
  )
}
