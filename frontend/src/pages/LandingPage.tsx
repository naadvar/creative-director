import { Link } from 'react-router-dom'
import { INSTAGRAM_CONNECT_URL } from '../api/client'
import EmailGate from '../components/EmailGate'

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
    <div className="mx-auto flex max-w-2xl flex-col items-center px-1 py-10 sm:py-16">
      <div className="w-full text-center">
        <div className="mx-auto mb-5 grid h-12 w-12 place-items-center rounded-2xl bg-accent/15 ring-1 ring-accent/40">
          <svg width="22" height="22" viewBox="0 0 12 12" fill="currentColor" className="text-accent">
            <path d="M3 1.7v8.6a.6.6 0 0 0 .92.5l6.7-4.3a.6.6 0 0 0 0-1L3.92 1.2A.6.6 0 0 0 3 1.7Z" />
          </svg>
        </div>
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
          A craft read of your Reel
        </h1>
        <p className="mx-auto mt-3 max-w-lg text-base leading-relaxed text-muted">
          Drop in a short and the model watches it frame by frame — hook, payoff,
          pacing, on-screen text, framing — then tells you the craft blind spots
          you’re too close to notice. Grounded in your actual footage, not
          virality guesses.
        </p>
      </div>

      <div className="mt-8 w-full max-w-md">
        <EmailGate bare redirectTo="/analyze" cta="Analyze my reel" />
      </div>

      <Link
        to="/browse"
        className="mt-5 text-sm text-accent underline-offset-4 hover:underline"
      >
        or browse example reads →
      </Link>

      <div className="mt-12 w-full space-y-4 rounded-2xl border border-border bg-surface p-6 text-left">
        <Step
          n={1}
          title="Drop your reel"
          body="Upload your short and pick a niche. No account hoops — just your email to save your reads."
        />
        <Step
          n={2}
          title="It watches the whole thing"
          body="A vision model reads your footage end to end: what the reel is, where the hook lands, whether the payoff arrives, dead time, framing, and every on-screen text beat."
        />
        <Step
          n={3}
          title="Grounded blind spots"
          body="Get the 2–4 craft fixes that matter most — each tied to a moment in your video, with a concrete change to try."
        />
      </div>

      <p className="mx-auto mt-8 max-w-lg text-center text-xs leading-relaxed text-muted">
        <span className="font-medium text-text/80">Craft observations, not performance predictions.</span>{' '}
        We don’t tell you a reel “will go viral” — nothing observable reliably
        predicts views. This reads the craft of the video in front of it, and
        flags what an editor would catch on a second watch.
      </p>

      <div className="mt-8 flex flex-col items-center gap-3 text-xs text-muted">
        <a
          href={INSTAGRAM_CONNECT_URL}
          className="underline-offset-2 hover:text-text hover:underline"
        >
          Have a Creator account? Connect Instagram to read your own reels
        </a>
        {/* Dev-only: gated by API_ALLOW_DEV_LOGIN on the backend. */}
        <a
          href="/api/auth/dev-login"
          className="text-muted/50 underline-offset-2 hover:text-muted hover:underline"
        >
          Preview inside (demo data)
        </a>
      </div>
    </div>
  )
}
