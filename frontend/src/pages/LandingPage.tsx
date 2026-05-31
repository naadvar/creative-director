import { INSTAGRAM_CONNECT_URL } from '../api/client'

function InstagramGlyph() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <rect x="2.5" y="2.5" width="19" height="19" rx="5.5" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="12" cy="12" r="4.2" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="17.4" cy="6.6" r="1.3" fill="currentColor" />
    </svg>
  )
}

function Step({ n, title, body }: { n: number; title: string; body: string }) {
  return (
    <div className="flex gap-3">
      <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-accent/15 text-xs font-semibold text-accent ring-1 ring-accent/30">
        {n}
      </span>
      <div>
        <div className="text-sm font-medium">{title}</div>
        <div className="mt-0.5 text-sm text-muted">{body}</div>
      </div>
    </div>
  )
}

export default function LandingPage() {
  return (
    <div className="mx-auto flex min-h-screen max-w-5xl flex-col items-center justify-center px-5 py-16">
      <div className="w-full max-w-xl text-center">
        <div className="mx-auto mb-5 grid h-12 w-12 place-items-center rounded-2xl bg-accent/15 ring-1 ring-accent/40">
          <svg width="22" height="22" viewBox="0 0 12 12" fill="currentColor" className="text-accent">
            <path d="M3 1.7v8.6a.6.6 0 0 0 .92.5l6.7-4.3a.6.6 0 0 0 0-1L3.92 1.2A.6.6 0 0 0 3 1.7Z" />
          </svg>
        </div>
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
          Your creative director for Reels
        </h1>
        <p className="mx-auto mt-3 max-w-md text-base leading-relaxed text-muted">
          Connect your Instagram and get a clear read on each Reel — how it
          compares to what's working for creators your size, and the few
          highest-leverage things to try next.
        </p>

        <div className="mt-8">
          <a
            href={INSTAGRAM_CONNECT_URL}
            className="inline-flex items-center gap-2.5 rounded-xl bg-accent px-5 py-3 text-sm font-semibold text-ink transition-transform hover:scale-[1.02] active:scale-100"
          >
            <InstagramGlyph />
            Connect Instagram
          </a>
          <p className="mt-3 text-xs text-muted">
            Requires an Instagram <span className="font-medium">Creator or Business</span> account.
            We only read your own content — never post, never DM.
          </p>
        </div>

        <div className="mt-12 space-y-4 rounded-2xl border border-border bg-surface p-6 text-left">
          <Step n={1} title="Connect" body="Authorize read-only access to your Reels. Takes 20 seconds." />
          <Step n={2} title="Analyze" body="Pick a Reel — we break down the hook, pacing, and framing against winning Reels in your niche and follower tier." />
          <Step n={3} title="Act" body="Get the 2–3 most fixable gaps, ranked by impact — plus real example Reels that nailed each one." />
        </div>

        <p className="mx-auto mt-8 max-w-md text-xs leading-relaxed text-muted">
          Advice is <span className="font-medium">correlational</span> — patterns
          that winning Reels share, not guarantees. A reel that misses on every
          measure can still be a hit; treat this as a sharp second opinion, not gospel.
        </p>

        {/* Dev-only: preview the authed app with demo (corpus) data, no OAuth.
            Backend 404s this when API_ALLOW_DEV_LOGIN=false. Remove before launch. */}
        <a
          href="/api/auth/dev-login"
          className="mt-10 inline-block text-xs text-muted/60 underline-offset-2 hover:text-muted hover:underline"
        >
          Preview inside (demo data)
        </a>
      </div>
    </div>
  )
}
