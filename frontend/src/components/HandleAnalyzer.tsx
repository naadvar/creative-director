import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, api } from '../api/client'
import { thumbnailUrl } from '../lib/format'
import type { AnalyzeHandleJob, NicheInfo } from '../api/types'

const POLL_MS = 3000

/** Paste an Instagram handle -> scrape recent reels (Apify) -> featurize ->
 * grade. The backend job is async, so we poll until it's done. */
export default function HandleAnalyzer() {
  const [handle, setHandle] = useState('')
  const [niches, setNiches] = useState<NicheInfo[]>([])
  const [niche, setNiche] = useState('ig_fitness')
  const [job, setJob] = useState<AnalyzeHandleJob | null>(null)
  const [error, setError] = useState<string | null>(null)
  const timer = useRef<number | null>(null)

  // Niche dropdown — IG niches only (those have analyzable benchmarks).
  useEffect(() => {
    api
      .niches()
      .then((r) => {
        const ig = r.niches.filter((n) => n.platform === 'instagram')
        setNiches(ig)
        if (ig.length) setNiche(ig[0].niche)
      })
      .catch(() => {})
  }, [])

  // Poll while a job is running.
  useEffect(() => {
    if (!job || job.status !== 'running') return
    timer.current = window.setTimeout(async () => {
      try {
        setJob(await api.analyzeHandleStatus(job.job_id))
      } catch (e) {
        setError(e instanceof ApiError ? e.message : 'Lost track of the job — try again.')
        setJob(null)
      }
    }, POLL_MS)
    return () => {
      if (timer.current) window.clearTimeout(timer.current)
    }
  }, [job])

  const busy = job?.status === 'running'

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    const h = handle.trim()
    if (!h || busy) return
    setError(null)
    try {
      setJob(await api.analyzeHandle(h, niche, 6))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not start — try again.')
    }
  }

  return (
    <form onSubmit={onSubmit} className="rounded-2xl border border-accent/30 bg-surface p-5">
      <label htmlFor="handle" className="text-sm font-semibold">
        Analyze your Instagram reels
      </label>
      <p className="mt-0.5 text-xs text-muted">
        Paste your handle — we pull your recent reels and grade them against top performers in
        your niche. First run scrapes + featurizes, so it takes a couple of minutes.
      </p>
      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
        <div className="flex min-w-0 flex-1 items-center rounded-lg border border-border bg-ink focus-within:border-accent/60">
          <span className="pl-3 text-sm text-muted">@</span>
          <input
            id="handle"
            type="text"
            value={handle}
            onChange={(e) => setHandle(e.target.value)}
            placeholder="yourhandle"
            disabled={busy}
            className="min-w-0 flex-1 bg-transparent px-2 py-2 text-sm outline-none placeholder:text-muted disabled:opacity-60"
          />
        </div>
        <select
          value={niche}
          onChange={(e) => setNiche(e.target.value)}
          disabled={busy}
          className="rounded-lg border border-border bg-ink px-2 py-2 text-sm outline-none focus:border-accent/60 disabled:opacity-60"
        >
          {niches.map((n) => (
            <option key={n.niche} value={n.niche}>
              {n.label}
            </option>
          ))}
        </select>
        <button
          type="submit"
          disabled={busy || handle.trim().length === 0}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy ? 'Analyzing…' : 'Analyze'}
        </button>
      </div>

      {busy ? (
        <div className="mt-3 flex items-center gap-2.5 text-sm text-muted">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/15 border-t-accent" />
          {job?.message || 'Working…'}
        </div>
      ) : null}

      {job?.status === 'error' ? (
        <p className="mt-3 rounded-lg border border-bad/40 bg-bad/10 px-3 py-2 text-sm text-bad">
          {job.error || 'Analysis failed.'}
        </p>
      ) : null}
      {error ? (
        <p className="mt-3 rounded-lg border border-bad/40 bg-bad/10 px-3 py-2 text-sm text-bad">
          {error}
        </p>
      ) : null}

      {job?.status === 'done' ? (
        job.video_ids.length ? (
          <div className="mt-4">
            <p className="text-sm font-medium">{job.message}</p>
            <div className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-6">
              {job.video_ids.map((id) => (
                <Link
                  key={id}
                  to={`/video/${id}`}
                  className="group overflow-hidden rounded-lg border border-border bg-ink transition-colors hover:border-accent/50"
                >
                  <div className="aspect-[9/16] bg-ink">
                    <img
                      src={thumbnailUrl(id)}
                      alt=""
                      loading="lazy"
                      onError={(e) => {
                        e.currentTarget.onerror = null
                        e.currentTarget.style.visibility = 'hidden'
                      }}
                      className="h-full w-full object-cover opacity-90 transition-opacity group-hover:opacity-100"
                    />
                  </div>
                  <span className="block px-2 py-1.5 text-center text-[11px] font-medium text-accent">
                    View analysis
                  </span>
                </Link>
              ))}
            </div>
          </div>
        ) : (
          <p className="mt-3 text-sm text-muted">No analyzable reels came back for that handle.</p>
        )
      ) : null}
    </form>
  )
}
