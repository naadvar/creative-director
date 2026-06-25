import { Link } from 'react-router-dom'

function Step({ n, title, body }: { n: number; title: string; body: string }) {
  return (
    <div className="flex gap-3.5">
      <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-grad text-xs font-bold text-white">
        {n}
      </span>
      <div>
        <div className="text-[15px] font-semibold">{title}</div>
        <div className="mt-0.5 text-sm leading-relaxed text-muted">{body}</div>
      </div>
    </div>
  )
}

export default function LandingPage() {
  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center px-1 py-12 sm:py-16">
      <div className="w-full text-center">
        <div className="glow mx-auto mb-6 grid h-14 w-14 place-items-center rounded-2xl bg-grad">
          <svg width="24" height="24" viewBox="0 0 12 12" fill="currentColor" className="text-white">
            <path d="M3 1.7v8.6a.6.6 0 0 0 .92.5l6.7-4.3a.6.6 0 0 0 0-1L3.92 1.2A.6.6 0 0 0 3 1.7Z" />
          </svg>
        </div>
        <h1 className="text-4xl font-extrabold leading-[1.05] tracking-tight sm:text-5xl">
          A <span className="text-grad">craft read</span>
          <br />
          of your Reel
        </h1>
        <p className="mx-auto mt-4 max-w-lg text-[15px] leading-relaxed text-muted sm:text-base">
          Drop in a short and the model watches it frame by frame — hook, payoff, pacing, framing,
          every text beat — then hands you the one craft fix you&apos;re too close to see. Grounded in
          your actual footage, never virality guesses.
        </p>
      </div>

      <div className="mt-8 w-full max-w-md">
        <Link
          to="/analyze"
          className="block w-full rounded-xl bg-grad px-5 py-3.5 text-center text-[15px] font-bold text-white transition-all hover:brightness-110"
        >
          Read my reel
        </Link>
        <p className="mt-2 text-center text-xs text-muted">
          Drop a reel — no account needed to start. Free.
        </p>
      </div>

      <Link to="/browse" className="mt-5 text-sm text-accent underline-offset-4 hover:underline">
        or browse example reads →
      </Link>

      <div className="mt-12 w-full space-y-5 rounded-2xl border border-border bg-surface p-6 text-left sm:p-7">
        <Step
          n={1}
          title="Drop your reel"
          body="Upload your short and pick a niche. No account hoops — just your email to save your reads."
        />
        <Step
          n={2}
          title="It watches the whole thing"
          body="A vision model reads your footage end to end: the hook, whether the payoff lands, dead time, framing, and every on-screen text beat — no thumbnails, the actual frames."
        />
        <Step
          n={3}
          title="One prioritized fix"
          body="The single highest-leverage craft change — tied to a moment in your video, with a concrete thing to try. Plus what's already working."
        />
      </div>

      <p className="mx-auto mt-8 max-w-lg text-center text-xs leading-relaxed text-muted">
        <span className="font-medium text-text/80">Craft observations, not performance predictions.</span>{' '}
        We don’t tell you a reel “will go viral” — nothing observable reliably
        predicts views. This reads the craft of the video in front of it, and
        flags what an editor would catch on a second watch.
      </p>
    </div>
  )
}
