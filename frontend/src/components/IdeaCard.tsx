import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, mediaUrl } from '../api/client'
import type { IdeaResponse } from '../api/types'

/** One "Ideas from your DNA" concept — grounded reel ideation. Every citation links
 * to the creator's own read (the trust affordance: they can verify the grounding in
 * one tap), and the stat lines under the guardrail are server-computed from real
 * data, never model-authored. */
export default function IdeaCard({
  data,
  onFresh,
  freshBusy,
  freshError,
}: {
  data: IdeaResponse
  onFresh: () => void
  freshBusy: boolean
  freshError: string | null
}) {
  const idea = data.idea
  const [fb, setFb] = useState<string | null>(data.feedback ?? null)
  if (!idea) return null

  function vote(rating: 'helpful' | 'not_for_me') {
    setFb(rating) // optimistic — a lost vote isn't worth an error state
    if (data.idea_id) api.ideaFeedback(data.idea_id, rating).catch(() => {})
  }

  return (
    <div className="space-y-4 rounded-2xl border border-accent/30 bg-accent/[0.05] p-5">
      <div>
        <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-accent">
          Your next reel
        </div>
        <h3 className="mt-1.5 text-lg font-bold leading-snug">{idea.concept}</h3>
        <p className="mt-1.5 text-sm leading-relaxed text-muted">{idea.premise}</p>
        {data.caveat ? (
          <p className="mt-2 rounded-lg border border-border bg-surface-2/60 px-3 py-1.5 text-xs text-muted">
            {data.caveat}
          </p>
        ) : null}
      </div>

      {/* Why this is yours — citations to the creator's OWN reels, tappable. */}
      {data.citations && data.citations.length > 0 ? (
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-widest text-muted">
            Why this is yours
          </h4>
          <div className="mt-2 space-y-1.5">
            {idea.grounded_in.map((g, i) => {
              const c = data.citations?.find((x) => x.video_id === g.video_id)
              return (
                <Link
                  key={i}
                  to={`/video/${g.video_id}`}
                  className="flex items-center gap-2.5 rounded-xl border border-border bg-surface px-3 py-2 transition-colors hover:border-accent/50"
                >
                  {c ? (
                    <img
                      src={mediaUrl(c.thumbnail_url)}
                      alt=""
                      loading="lazy"
                      onError={(e) => {
                        e.currentTarget.onerror = null
                        e.currentTarget.style.visibility = 'hidden'
                      }}
                      className="h-12 w-8 shrink-0 rounded object-cover"
                    />
                  ) : null}
                  <span className="min-w-0 text-[13px] leading-snug text-muted">
                    <span className="font-medium text-text">{c?.title ?? 'Your reel'}</span>
                    {' — '}
                    {g.why}
                  </span>
                </Link>
              )
            })}
          </div>
        </div>
      ) : null}

      {/* The beat sheet — a shootable plan, not a vibe. */}
      <div>
        <h4 className="text-xs font-semibold uppercase tracking-widest text-muted">Beat sheet</h4>
        <ol className="mt-2 space-y-2">
          {idea.beat_sheet.map((b, i) => (
            <li key={i} className="flex gap-2.5 text-sm leading-relaxed">
              <span className="shrink-0 tabular-nums text-xs font-semibold text-accent">
                {b.time}
              </span>
              <span>
                <span className="font-medium">{b.beat}.</span>{' '}
                <span className="text-muted">{b.direction}</span>
              </span>
            </li>
          ))}
        </ol>
      </div>

      {/* The guardrail — their recurring gap, pre-empted at plan time. */}
      <div className="rounded-xl border border-good/30 bg-good/[0.06] p-3.5">
        <div className="text-[11px] font-semibold uppercase tracking-widest text-good">
          Planned so your usual note can’t recur
        </div>
        <p className="mt-1.5 text-sm leading-relaxed">{idea.gap_guardrail.plan}</p>
        {data.gap_stat_line ? (
          <p className="mt-2 text-[11px] leading-relaxed text-muted">
            {data.gap_stat_line}
            {data.digest_line ? ` ${data.digest_line}` : ''}
          </p>
        ) : null}
      </div>

      {idea.shoot_notes ? (
        <p className="text-xs text-muted">🎥 {idea.shoot_notes}</p>
      ) : null}

      <div className="flex flex-wrap items-center gap-2.5 pt-1">
        <Link
          to={`/analyze?idea=${data.idea_id}`}
          className="rounded-xl bg-grad px-5 py-2.5 text-sm font-bold text-white transition-all hover:brightness-110"
        >
          Plan this next
        </Link>
        <button
          type="button"
          onClick={onFresh}
          disabled={freshBusy}
          className="rounded-xl border border-border bg-surface px-5 py-2.5 text-sm font-semibold text-muted transition-colors hover:text-text disabled:opacity-50"
        >
          {freshBusy ? 'Sketching…' : 'Show me another'}
        </button>
      </div>
      {freshError ? <p className="text-xs text-muted">{freshError}</p> : null}

      <div className="flex items-center gap-2 border-t border-accent/15 pt-2.5 text-[12px]">
        {fb ? (
          <span className="text-muted">
            {fb === 'helpful' ? 'Glad it sparks something. 🙌' : 'Noted — that tunes future ideas.'}
          </span>
        ) : (
          <>
            <span className="text-muted">Useful direction?</span>
            <button
              type="button"
              onClick={() => vote('helpful')}
              className="rounded-full border border-border bg-surface px-2.5 py-0.5 font-medium text-muted transition-colors hover:text-text"
            >
              👍 Helpful
            </button>
            <button
              type="button"
              onClick={() => vote('not_for_me')}
              className="rounded-full border border-border bg-surface px-2.5 py-0.5 font-medium text-muted transition-colors hover:text-text"
            >
              👎 Not for me
            </button>
          </>
        )}
      </div>
    </div>
  )
}
