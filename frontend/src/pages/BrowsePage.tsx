import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { CategoryCount, CorpusVideo, NicheInfo } from '../api/types'
import Spinner from '../components/Spinner'
import VideoCard from '../components/VideoCard'

const PAGE = 60

const FILTERS: { label: string; value: number | null }[] = [
  { label: 'All', value: null },
  { label: 'High', value: 2 },
  { label: 'Mid', value: 1 },
  { label: 'Low', value: 0 },
]

function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}

/** Short chip label: "Gym weights / bodybuilding" -> "Gym weights". */
function chipLabel(label: string): string {
  return label.split('/')[0].trim()
}

/** Disambiguate same-named niches across platforms ("Fitness" vs "Fitness · YT"). */
function nicheLabel(n: NicheInfo): string {
  return n.platform === 'youtube' ? `${n.label} · YT` : n.label
}

export default function BrowsePage() {
  const [niches, setNiches] = useState<NicheInfo[]>([])
  const [niche, setNiche] = useState<string | null>(null)
  const [tercile, setTercile] = useState<number | null>(null)
  const [category, setCategory] = useState<string | null>(null)
  const [q, setQ] = useState('')
  const [qDebounced, setQDebounced] = useState('')
  const [facets, setFacets] = useState<CategoryCount[]>([])
  const [videos, setVideos] = useState<CorpusVideo[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Niches (fetched once) — default to the largest.
  useEffect(() => {
    api
      .niches()
      .then((r) => {
        setNiches(r.niches)
        if (r.niches.length) setNiche(r.niches[0].niche)
        else setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  // Category chips track the selected niche.
  useEffect(() => {
    if (!niche) return
    api
      .corpusCategories(niche)
      .then((f) => setFacets(f.categories))
      .catch(() => setFacets([]))
  }, [niche])

  // Debounce the search box so we don't query on every keystroke.
  useEffect(() => {
    const t = setTimeout(() => setQDebounced(q.trim()), 300)
    return () => clearTimeout(t)
  }, [q])

  useEffect(() => {
    if (!niche) return
    let cancelled = false
    setLoading(true)
    setError(null)
    setVideos([])
    api
      .corpus({
        niche,
        tercile: tercile ?? undefined,
        category: category ?? undefined,
        q: qDebounced || undefined,
        limit: PAGE,
        offset: 0,
      })
      .then((page) => {
        if (cancelled) return
        setVideos(page.videos)
        setTotal(page.total)
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(errMsg(e))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [niche, tercile, category, qDebounced])

  async function loadMore() {
    setLoadingMore(true)
    try {
      const page = await api.corpus({
        niche: niche ?? undefined,
        tercile: tercile ?? undefined,
        category: category ?? undefined,
        q: qDebounced || undefined,
        limit: PAGE,
        offset: videos.length,
      })
      setVideos((prev) => [...prev, ...page.videos])
      setTotal(page.total)
    } catch (e) {
      setError(errMsg(e))
    } finally {
      setLoadingMore(false)
    }
  }

  // Switching niche resets the niche-specific category filter.
  const pickNiche = (n: string) => {
    setNiche(n)
    setCategory(null)
  }

  const chip = (active: boolean) =>
    `rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
      active
        ? 'border-accent/50 bg-accent/15 text-accent'
        : 'border-border text-muted hover:text-text'
    }`

  const selected = niches.find((n) => n.niche === niche)
  const selectedLabel = selected ? selected.label.toLowerCase() : 'creator'

  return (
    <div className="space-y-5">
      {/* Niche switcher — the top-level selector */}
      {niches.length > 0 ? (
        <div className="flex flex-wrap items-center gap-1 rounded-lg border border-border bg-surface p-1">
          {niches.map((n) => (
            <button
              key={n.niche}
              type="button"
              onClick={() => pickNiche(n.niche)}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                niche === n.niche ? 'bg-accent text-white' : 'text-muted hover:text-text'
              }`}
            >
              {nicheLabel(n)}{' '}
              <span className="opacity-60">{n.count.toLocaleString()}</span>
            </button>
          ))}
        </div>
      ) : null}

      <div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-lg font-semibold">Browse the corpus</h1>
            <p className="text-sm text-muted">
              {loading
                ? 'Loading…'
                : `${total.toLocaleString()} analyzable ${selectedLabel} reels`}
            </p>
          </div>
          <div className="flex gap-1 rounded-lg border border-border bg-surface p-1">
            {FILTERS.map((f) => (
              <button
                key={f.label}
                type="button"
                onClick={() => setTercile(f.value)}
                className={`rounded-md px-3 py-1 text-sm font-medium transition-colors ${
                  tercile === f.value
                    ? 'bg-accent text-white'
                    : 'text-muted hover:text-text'
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        {/* search + category chips */}
        <div className="mt-4 space-y-3">
          <div className="relative max-w-sm">
            <svg
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted"
              width="14"
              height="14"
              viewBox="0 0 14 14"
              fill="none"
              aria-hidden
            >
              <circle cx="6" cy="6" r="4.2" stroke="currentColor" strokeWidth="1.5" />
              <path d="M9.2 9.2 12 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            <input
              type="search"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search captions…"
              className="w-full rounded-lg border border-border bg-surface py-2 pl-9 pr-3 text-sm outline-none transition-colors focus:border-accent"
            />
          </div>

          {facets.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              <button type="button" onClick={() => setCategory(null)} className={chip(category === null)}>
                All
              </button>
              {facets.map((f) => (
                <button
                  key={f.key}
                  type="button"
                  onClick={() => setCategory(category === f.key ? null : f.key)}
                  className={chip(category === f.key)}
                  title={f.label}
                >
                  {chipLabel(f.label)}{' '}
                  <span className="opacity-60">{f.count}</span>
                </button>
              ))}
            </div>
          ) : null}
        </div>

        {error ? (
          <p className="mt-4 rounded-lg border border-bad/40 bg-bad/10 px-3 py-2 text-sm text-bad">
            {error}
          </p>
        ) : null}

        {loading ? (
          <div className="mt-6">
            <Spinner label="Loading corpus…" />
          </div>
        ) : videos.length === 0 ? (
          !error ? (
            <p className="mt-6 text-sm text-muted">No reels match these filters.</p>
          ) : null
        ) : (
          <>
            <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
              {videos.map((v) => (
                <VideoCard key={v.video_id} v={v} />
              ))}
            </div>
            {videos.length < total ? (
              <div className="mt-6 flex justify-center">
                <button
                  type="button"
                  onClick={loadMore}
                  disabled={loadingMore}
                  className="rounded-lg border border-border bg-surface px-5 py-2 text-sm font-medium transition-colors hover:border-accent/50 disabled:opacity-50"
                >
                  {loadingMore
                    ? 'Loading…'
                    : `Load more (${videos.length} of ${total.toLocaleString()})`}
                </button>
              </div>
            ) : null}
          </>
        )}
      </div>
    </div>
  )
}
