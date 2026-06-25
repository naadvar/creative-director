import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import Spinner from '../components/Spinner'

export default function MyDnaPage() {
  const fp = useAsync(() => api.myFingerprint(), [])
  const data = fp.data

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
          Built only from the reels you’ve read here — your style and the craft notes that
          keep coming up. It sharpens every time you read another reel.
        </p>
      </div>

      {fp.loading ? (
        <Spinner label="Building your DNA…" />
      ) : fp.error ? (
        <p className="rounded-xl border border-bad/40 bg-bad/10 px-4 py-3 text-sm text-bad">
          {fp.error}
        </p>
      ) : data?.ready ? (
        <div className="space-y-5">
          <div className="rounded-2xl border border-accent/30 bg-accent/[0.06] p-5 sm:p-6">
            <div className="text-xs font-semibold uppercase tracking-widest text-accent">
              {data.n_reels} reel{data.n_reels === 1 ? '' : 's'} in your DNA
            </div>
            <p className="mt-2 text-lg font-medium leading-snug">{data.summary}</p>
          </div>

          {data.recurring && data.recurring.length > 0 ? (
            <div className="rounded-2xl border border-border bg-surface p-5">
              <h2 className="text-sm font-semibold">Patterns that recur in your reels</h2>
              <ul className="mt-3 space-y-2.5">
                {data.recurring.map((r) => (
                  <li key={r.type} className="flex items-center gap-3">
                    <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-accent/15 text-xs font-bold tabular-nums text-accent">
                      ×{r.count}
                    </span>
                    <span className="text-sm leading-snug">{r.label}</span>
                  </li>
                ))}
              </ul>
              <p className="mt-4 text-[11px] leading-relaxed text-muted">
                These are craft tendencies across your uploads — knowing them is half the fix.
              </p>
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed border-border bg-surface-2/40 p-5 text-center text-sm text-muted">
              Read a few more reels and we’ll surface the craft patterns that recur in your work.
            </div>
          )}

          <div className="flex flex-wrap justify-center gap-2.5">
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
              My reads
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
