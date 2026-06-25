import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { Fingerprint } from '../api/types'
import CreatorFingerprint from '../components/CreatorFingerprint'
import EmailGate from '../components/EmailGate'
import { useAuth } from '../hooks/useAuth'

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

function UploadIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 22 22" fill="none" className="text-white">
      <path
        d="M11 14.5V5m0 0L7.5 8.5M11 5l3.5 3.5M5 15.5v1A1.5 1.5 0 0 0 6.5 18h9a1.5 1.5 0 0 0 1.5-1.5v-1"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function FilmIcon() {
  return (
    <svg width="30" height="30" viewBox="0 0 30 30" fill="none" className="text-white">
      <rect x="5" y="6" width="20" height="18" rx="3" stroke="currentColor" strokeWidth="1.8" />
      <path
        d="M5 11h20M5 19h20M10 6v18M20 6v18"
        stroke="currentColor"
        strokeWidth="1.4"
        opacity="0.85"
      />
    </svg>
  )
}

const STAGES = ['Uploading', 'Reading every frame', 'Writing the read', 'Fact-checking it', 'Final touches']

function stageIndex(message: string): number {
  const m = message.toLowerCase()
  if (m.includes('timeline') || m.includes('ready') || m.includes('final')) return 4
  if (m.includes('fact-check') || m.includes('grounding')) return 3
  if (m.includes('writing') || m.includes('craft read')) return 2
  if (m.includes('frame') || m.includes('reading')) return 1
  return 0
}

function StepDot({ state }: { state: 'done' | 'active' | 'todo' }) {
  if (state === 'done') {
    return (
      <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-grad">
        <svg width="11" height="11" viewBox="0 0 11 11" fill="none" className="text-white">
          <path
            d="M2.5 5.8 4.5 7.8 8.5 3.2"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
    )
  }
  if (state === 'active') {
    return <span className="h-5 w-5 shrink-0 rounded-full border-2 border-accent animate-pulse-glow" />
  }
  return <span className="h-5 w-5 shrink-0 rounded-full border border-border" />
}

/** Full-screen takeover for the ~2–3 min analysis — the wait is a moment to delight,
 * not a tiny spinner. Shows the live stage, a scanning bar, and an animated stepper. */
function AnalyzingView({ message, fileName }: { message: string; fileName?: string }) {
  const idx = stageIndex(message)
  return (
    <div className="mx-auto max-w-md pt-8 sm:pt-12">
      <div className="animate-rise glow rounded-3xl border border-border bg-surface p-7 text-center sm:p-9">
        <div className="mx-auto grid h-20 w-20 place-items-center rounded-2xl bg-grad animate-pulse-glow">
          <FilmIcon />
        </div>
        <h2 className="mt-6 text-2xl font-bold tracking-tight">Reading your reel</h2>
        {fileName ? <p className="mt-1 truncate text-sm text-muted">{fileName}</p> : null}

        <div className="mt-6 h-1.5 overflow-hidden rounded-full bg-surface-2">
          <div className="h-full w-full bg-grad animate-scan" />
        </div>

        <p className="mt-5 text-[15px] font-medium">{message || 'working…'}</p>

        <div className="mx-auto mt-6 max-w-[15rem] space-y-3 text-left">
          {STAGES.map((s, i) => (
            <div key={s} className="flex items-center gap-3">
              <StepDot state={i < idx ? 'done' : i === idx ? 'active' : 'todo'} />
              <span className={`text-sm ${i <= idx ? 'text-text' : 'text-muted'}`}>{s}</span>
            </div>
          ))}
        </div>

        <p className="mt-7 text-xs leading-relaxed text-muted">
          Watching every frame, not just the thumbnail — keep this tab open.
        </p>
      </div>
    </div>
  )
}

/** Home: upload a reel -> full craft read vs the niche's winners. */
export default function UploadPage() {
  const navigate = useNavigate()
  const { user } = useAuth()
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
  const [fingerprint, setFingerprint] = useState<Fingerprint | null>(null)
  const [gating, setGating] = useState(false)
  const cancelled = useRef(false)

  useEffect(() => {
    api
      .niches()
      .then((r) =>
        setCorpusTotal(
          r.niches.filter((n) => n.platform === 'instagram').reduce((sum, n) => sum + n.count, 0),
        ),
      )
      .catch(() => {})
    api.myFingerprint().then(setFingerprint).catch(() => {})
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

  // Gate is deferred to here: pick a file freely, sign in only at "Read my reel".
  const submit = () => {
    if (!file || phase !== 'idle') return
    if (!user) {
      setGating(true)
      return
    }
    void doUpload()
  }

  const doUpload = async () => {
    if (!file || phase !== 'idle') return
    setError(null)
    cancelled.current = false
    setPhase('uploading')
    setMessage('uploading your reel…')
    try {
      const job = await api.upload(file, niche, caption, followers ? parseInt(followers, 10) : undefined)
      setPhase('analyzing')
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

  if (phase !== 'idle') {
    return <AnalyzingView message={message} fileName={file?.name} />
  }

  return (
    <div className="mx-auto max-w-2xl space-y-7">
      <div className="space-y-3 pt-6 text-center">
        <h1 className="text-4xl font-extrabold leading-[1.04] tracking-tight sm:text-5xl">
          Get a <span className="text-grad">craft read</span>
          <br />
          of your reel
        </h1>
        <p className="mx-auto max-w-xl text-[15px] leading-relaxed text-muted">
          Drop a reel — even an unposted draft — and the model watches it frame by frame: hook,
          payoff, pacing, framing, every text beat. Then it hands you the one craft fix you&apos;re
          too close to see.
          {corpusTotal ? (
            <>
              {' '}
              Trained on <span className="font-semibold text-text">{corpusTotal.toLocaleString()}</span>{' '}
              analyzed reels.
            </>
          ) : null}
        </p>
      </div>

      {fingerprint?.ready ? <CreatorFingerprint fp={fingerprint} /> : null}

      <div className="space-y-5 rounded-2xl border border-border bg-surface p-5 sm:p-6">
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
          className={`flex w-full flex-col items-center justify-center gap-3.5 rounded-2xl border-2 border-dashed px-4 py-12 text-center transition-all ${
            dragging
              ? 'scale-[1.01] border-accent bg-accent/10'
              : file
                ? 'border-good/50 bg-good/[0.06]'
                : 'border-border bg-surface-2/40 hover:border-accent/60 hover:bg-surface-2'
          }`}
        >
          <div
            className={`grid h-14 w-14 place-items-center rounded-2xl transition-transform ${
              file ? 'bg-good' : 'bg-grad'
            } ${dragging ? 'scale-110' : ''}`}
          >
            {file ? (
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" className="text-white">
                <path
                  d="M5 12.5 10 17.5 19 7"
                  stroke="currentColor"
                  strokeWidth="2.2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            ) : (
              <UploadIcon />
            )}
          </div>
          {file ? (
            <>
              <span className="text-[15px] font-semibold">{file.name}</span>
              <span className="text-xs text-muted">{fmtSize(file.size)} · tap to swap it</span>
            </>
          ) : (
            <>
              <span className="text-[15px] font-semibold">Drop your reel here, or tap to choose</span>
              <span className="text-xs text-muted">mp4 / mov · up to 3 min · stays private, never published</span>
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

        <div>
          <div className="mb-2 text-xs font-semibold uppercase tracking-widest text-muted">Your niche</div>
          <div className="flex flex-wrap gap-2">
            {NICHES.map((n) => (
              <button
                key={n.key}
                type="button"
                onClick={() => setNiche(n.key)}
                className={`rounded-full border px-4 py-1.5 text-sm font-medium transition-all ${
                  niche === n.key
                    ? 'border-accent/50 bg-accent/15 text-text'
                    : 'border-border bg-surface-2 text-muted hover:text-text'
                }`}
              >
                {n.label}
              </button>
            ))}
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-[1fr_180px]">
          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-widest text-muted">
              Caption{' '}
              <span className="font-normal normal-case tracking-normal">(optional)</span>
            </div>
            <textarea
              value={caption}
              onChange={(e) => setCaption(e.target.value)}
              rows={2}
              placeholder="Paste the caption you'd post with it…"
              className="w-full resize-none rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm outline-none transition-colors placeholder:text-muted/60 focus:border-accent"
            />
          </div>
          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-widest text-muted">
              Followers <span className="font-normal normal-case tracking-normal">(optional)</span>
            </div>
            <input
              value={followers}
              onChange={(e) => setFollowers(e.target.value.replace(/[^0-9]/g, ''))}
              inputMode="numeric"
              placeholder="e.g. 12000"
              className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm outline-none transition-colors placeholder:text-muted/60 focus:border-accent"
            />
          </div>
        </div>

        <button
          type="button"
          onClick={() => void submit()}
          disabled={!file}
          className="w-full rounded-xl bg-grad px-4 py-3.5 text-[15px] font-bold text-white transition-all hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40 disabled:grayscale"
        >
          {file ? 'Read my reel' : 'Choose a reel to read'}
        </button>

        {error ? (
          <p className="rounded-xl border border-bad/40 bg-bad/10 px-4 py-3 text-sm text-bad">{error}</p>
        ) : null}
      </div>

      <p className="text-center text-xs leading-relaxed text-muted">
        Analyzed on the spot, never shared or published. A craft read of your footage — no
        performance or virality predictions.
      </p>

      {/* Deferred email gate — only appears at the moment of value (the submit tap). */}
      {gating ? (
        <div
          className="fixed inset-0 z-40 grid place-items-center bg-ink/70 p-4 backdrop-blur-sm"
          onClick={() => setGating(false)}
        >
          <div className="w-full max-w-md" onClick={(e) => e.stopPropagation()}>
            <EmailGate
              heading="Save your read"
              sub="Drop your email so your read lands in your library — no password, no spam."
              cta="Read my reel"
              onAuthed={() => {
                setGating(false)
                void doUpload()
              }}
            />
          </div>
        </div>
      ) : null}
    </div>
  )
}
