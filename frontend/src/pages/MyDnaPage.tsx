import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import type { IdeaResponse } from '../api/types'
import IdeaCard from '../components/IdeaCard'
import Spinner from '../components/Spinner'

export default function MyDnaPage() {
  const fp = useAsync(() => api.myFingerprint(), [])
  const prog = useAsync(() => api.myProgress(), [])
  const data = fp.data
  const p = prog.data

  // "Your next reel" — grounded ideation from the DNA above it. Custom state (not
  // useAsync) so "Show me another" can refresh in place without unmounting the card.
  const [idea, setIdea] = useState<IdeaResponse | null>(null)
  const [ideaBusy, setIdeaBusy] = useState(true)
  const [freshBusy, setFreshBusy] = useState(false)
  const [freshError, setFreshError] = useState<string | null>(null)
  const loadIdea = async (fresh: boolean) => {
    if (fresh) setFreshBusy(true)
    setFreshError(null)
    try {
      const r = await api.myIdea(fresh)
      setIdea(r)
    } catch (e) {
      // 429 = the honest daily cap; anything else keeps the previous idea quietly.
      if (e instanceof ApiError && e.status === 429) setFreshError(e.message)
      else if (!idea) setIdea(null)
    } finally {
      setIdeaBusy(false)
      setFreshBusy(false)
    }
  }
  useEffect(() => {
    void loadIdea(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="mx-auto max-w-2xl space-y-6 py-2">
      <div className="text-center">
        <div className="glow mx-auto mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-grad">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" className="text-white">
            <path
              d="M7 4c0 4 10 6 10 10M17 4c0 4-10 6-10 10M7 20c0-2 10-4 10-8M17 20c0-2-10-4-10-8"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
            />
          </svg>
        </div>
        <h1 className="text-2xl font-extrabold tracking-tight sm:text-3xl">
          Your <span className="text-grad">Creator DNA</span>
        </h1>
        <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-muted">
          Built only from the reels you’ve read here — your style and how your craft is trending.
        </p>
      </div>

      {fp.loading ? (
        <Spinner label="Building your DNA…" />
      ) : data?.ready ? (
        <div className="space-y-5">
          {/* Identity */}
          <div className="rounded-2xl border border-accent/30 bg-accent/[0.06] p-5 sm:p-6">
            <div className="text-xs font-semibold uppercase tracking-widest text-accent">
              {data.n_reels} reel{data.n_reels === 1 ? '' : 's'} in your DNA
            </div>
            <p className="mt-2 text-lg font-medium leading-snug">{data.summary}</p>
          </div>

          {/* The trend — the "am I improving?" signal */}
          {p?.ready ? (
            <div className="rounded-2xl border border-border bg-surface p-5">
              <h2 className="text-sm font-semibold">Your craft trend</h2>
              <p className="mt-2 text-[15px] leading-relaxed">{p.headline}</p>

              {p.improving.length > 0 || p.recurring.length > 0 ? (
                <div className="mt-4 flex flex-wrap gap-2">
                  {p.improving.map((t) => (
                    <span
                      key={`i-${t.dimension}`}
                      className="inline-flex items-center gap-1.5 rounded-full border border-good/30 bg-good/[0.08] px-3 py-1 text-[12px] text-good"
                      title={`Recurred ${t.past_count}× early, absent from your recent reads`}
                    >
                      ↑ moved past {t.label}
                    </span>
                  ))}
                  {p.recurring.map((t) => (
                    <span
                      key={`r-${t.dimension}`}
                      className="inline-flex items-center gap-1.5 rounded-full border border-accent/30 bg-accent/[0.08] px-3 py-1 text-[12px] text-accent"
                      title={`Came up in ${t.count} of your reads`}
                    >
                      {t.label} <span className="opacity-70">×{t.count}</span>
                    </span>
                  ))}
                </div>
              ) : null}
              <p className="mt-3 text-[11px] leading-relaxed text-muted">
                A factual read of the notes across your reels over time — not a claim that you fixed
                anything. You draw that conclusion.
              </p>
            </div>
          ) : null}

          {/* Your next reel — ideation grounded in the DNA above it. */}
          {ideaBusy ? (
            <div className="rounded-2xl border border-border bg-surface p-5">
              <Spinner label="Sketching your next reel…" />
            </div>
          ) : idea?.ready && idea.idea ? (
            <IdeaCard
              data={idea}
              onFresh={() => void loadIdea(true)}
              freshBusy={freshBusy}
              freshError={freshError}
            />
          ) : idea && !idea.ready ? (
            <div className="rounded-2xl border border-dashed border-border bg-surface-2/40 px-5 py-6 text-center">
              <p className="text-sm font-semibold">Your next reel</p>
              <p className="mx-auto mt-1 max-w-sm text-sm text-muted">{idea.reason}</p>
            </div>
          ) : null}

          <div className="flex flex-wrap justify-center gap-2.5 pt-1">
            <Link
              to="/analyze"
              className="rounded-xl bg-grad px-5 py-2.5 text-sm font-bold text-white transition-all hover:brightness-110"
            >
              Read another reel
            </Link>
            <Link
              to="/my-reads"
              className="rounded-xl border border-border bg-surface px-5 py-2.5 text-sm font-semibold text-muted transition-colors hover:text-text"
            >
              See all in Library
            </Link>
          </div>
        </div>
      ) : (
        <div className="rounded-2xl border border-dashed border-border bg-surface-2/40 px-6 py-12 text-center">
          <p className="text-[15px] font-semibold">Your DNA is empty — for now</p>
          <p className="mx-auto mt-1 max-w-xs text-sm text-muted">
            Read your first reel and your Creator DNA starts forming.
          </p>
          <Link
            to="/analyze"
            className="mt-5 inline-block rounded-xl bg-grad px-5 py-2.5 text-sm font-bold text-white transition-all hover:brightness-110"
          >
            Read your first reel
          </Link>
        </div>
      )}
    </div>
  )
}
