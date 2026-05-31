import { useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, api } from '../api/client'

export default function UrlAnalyzer() {
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    const trimmed = url.trim()
    if (!trimmed || busy) return
    setBusy(true)
    setError(null)
    try {
      const res = await api.analyzeUrl(trimmed)
      navigate(`/video/${res.video_id}`)
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Something went wrong — try again.',
      )
      setBusy(false)
    }
  }

  return (
    <form
      onSubmit={onSubmit}
      className="rounded-2xl border border-border bg-surface p-5"
    >
      <label htmlFor="url" className="text-sm font-semibold">
        Analyze any Shorts URL
      </label>
      <p className="mt-0.5 text-xs text-muted">
        Paste a YouTube Shorts link or video ID. First-time analysis downloads and
        featurizes the video — expect 45–90s.
      </p>
      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
        <input
          id="url"
          type="text"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://www.youtube.com/shorts/…"
          disabled={busy}
          className="min-w-0 flex-1 rounded-lg border border-border bg-ink px-3 py-2 text-sm outline-none placeholder:text-muted focus:border-accent/60 disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={busy || url.trim().length === 0}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy ? 'Analyzing…' : 'Analyze'}
        </button>
      </div>
      {busy ? (
        <div className="mt-3 flex items-center gap-2.5 text-sm text-muted">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/15 border-t-accent" />
          Downloading, featurizing &amp; timelining — this can take 45–90s on first
          run…
        </div>
      ) : null}
      {error ? (
        <p className="mt-3 rounded-lg border border-bad/40 bg-bad/10 px-3 py-2 text-sm text-bad">
          {error}
        </p>
      ) : null}
    </form>
  )
}
