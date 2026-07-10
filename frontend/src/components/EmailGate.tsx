import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, ApiError, isNativeApp } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import { useAppleSignIn } from '../hooks/useAppleSignIn'

interface Props {
  /** Where to send the user after they sign in. Defaults to the upload page. */
  redirectTo?: string
  /** Headline above the form. */
  heading?: string
  /** Sub-line under the headline. */
  sub?: string
  /** Submit button label. */
  cta?: string
  /** Compact variant for embedding in a hero (no card chrome). */
  bare?: boolean
  /** If set, called after sign-in instead of navigating (e.g. continue an upload in place). */
  onAuthed?: () => void
  /** Show the quiet "See an example read first" link. On for the sign-in-wall
   * surfaces (the #1 first-impression fix), off for the deferred upload gate. */
  exampleLink?: boolean
}

// Pragmatic format check: exactly one @, a dot in the domain, no spaces. Not
// RFC-perfect — just enough to catch typos before we create an orphan account
// (there's no email verification, so this + the confirm step are the only net).
function validFormat(email: string): boolean {
  const e = email.trim()
  if (/\s/.test(e)) return false
  const at = e.indexOf('@')
  if (at <= 0 || at !== e.lastIndexOf('@')) return false
  const domain = e.slice(at + 1)
  return domain.includes('.') && !domain.startsWith('.') && !domain.endsWith('.')
}

// Common domain typos -> the intended domain. Keyed on the (lowercased) domain the
// user typed; a hit becomes a tappable "Did you mean …?" chip.
const DOMAIN_TYPOS: Record<string, string> = {
  'gmial.com': 'gmail.com',
  'gamil.com': 'gmail.com',
  'gmal.com': 'gmail.com',
  'gmail.co': 'gmail.com',
  'hotmial.com': 'hotmail.com',
  'hotmal.com': 'hotmail.com',
  'yaho.com': 'yahoo.com',
  'yahooo.com': 'yahoo.com',
  'outlok.com': 'outlook.com',
  'icloud.co': 'icloud.com',
}

/** If the domain looks like a known typo, return the corrected full email. */
function suggestEmail(email: string): string | null {
  const e = email.trim()
  const at = e.lastIndexOf('@')
  if (at <= 0) return null
  const local = e.slice(0, at)
  const domain = e.slice(at + 1).toLowerCase()
  const fixed = DOMAIN_TYPOS[domain]
  return fixed ? `${local}@${fixed}` : null
}

/** Passwordless email gate: one field, no password. Submitting find-or-creates
 * the account, starts a session, and continues to `redirectTo`. */
export default function EmailGate({
  redirectTo = '/analyze',
  heading = 'Analyze your reel',
  sub = 'Enter your email to get a grounded craft read of your own short.',
  cta = 'Continue',
  bare = false,
  onAuthed,
  exampleLink = false,
}: Props) {
  const { refresh } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  // A brand-new email is confirmed inline before we commit — a typo'd address would
  // otherwise create an orphan account with no recovery. Holds the just-created email.
  const [confirming, setConfirming] = useState<string | null>(null)
  // Native-only one-tap Apple sign-in; honors the same redirect/onAuthed as email.
  const { signInWithApple, busy: appleBusy, error: appleErr } = useAppleSignIn(
    redirectTo,
    onAuthed,
  )

  const suggestion = suggestEmail(email)

  // Called after a successful login. For a returning user it continues straight
  // through; for a NEW account it pauses on an inline confirm (Edit / Continue) so a
  // typo is caught before the (already-created) orphan account is used.
  async function finishAuth(newUser: boolean, typedEmail: string) {
    if (newUser) {
      setConfirming(typedEmail)
      return
    }
    await refresh()
    if (onAuthed) onAuthed()
    else navigate(redirectTo)
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (busy) return
    // Client-side format guard — reject obvious junk before hitting the API.
    if (!validFormat(email)) {
      setErr('That doesn’t look like a valid email — check for typos.')
      return
    }
    setBusy(true)
    setErr(null)
    try {
      const r = await api.emailLogin(email)
      await finishAuth(!!r.new_user, email.trim())
    } catch (e) {
      setErr(
        e instanceof ApiError && e.status === 422
          ? 'That doesn’t look like a valid email.'
          : e instanceof ApiError
            ? e.message
            : 'Something went wrong — try again.',
      )
    } finally {
      setBusy(false)
    }
  }

  // The new-account confirm continues into the app (the session already exists).
  async function confirmContinue() {
    setConfirming(null)
    await refresh()
    if (onAuthed) onAuthed()
    else navigate(redirectTo)
  }

  // New-account confirm: replaces the form so a typo'd address is caught before the
  // (already-created) account is actually used. Edit goes back to the field.
  const confirmPanel = confirming ? (
    <div className="w-full">
      <p className="text-sm leading-relaxed">
        Signing up as <span className="font-semibold break-all">{confirming}</span>. Right?
      </p>
      <div className="mt-3 flex gap-2">
        <button
          type="button"
          onClick={() => setConfirming(null)}
          className="shrink-0 rounded-lg border border-border bg-surface px-4 py-2.5 text-sm font-semibold text-muted transition-colors hover:text-text"
        >
          Edit
        </button>
        <button
          type="button"
          onClick={() => void confirmContinue()}
          className="flex-1 rounded-lg bg-grad px-5 py-2.5 text-sm font-bold text-white transition-all hover:brightness-110"
        >
          Continue
        </button>
      </div>
      <p className="mt-2 text-xs text-muted">
        No password, no email verification — so double-check the spelling.
      </p>
    </div>
  ) : null

  const form = (
    <form onSubmit={onSubmit} className="w-full">
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          type="email"
          inputMode="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => {
            setEmail(e.target.value)
            if (err) setErr(null)
          }}
          placeholder="you@email.com"
          className="min-w-0 flex-1 rounded-lg border border-border bg-ink px-3.5 py-2.5 text-sm text-text placeholder:text-muted/70 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
        />
        <button
          type="submit"
          disabled={busy}
          className="shrink-0 rounded-lg bg-grad px-5 py-2.5 text-sm font-bold text-white transition-all hover:brightness-110 disabled:opacity-60"
        >
          {busy ? 'One sec…' : cta}
        </button>
      </div>
      {/* Domain-typo catch: one tap swaps in the intended address. */}
      {suggestion ? (
        <button
          type="button"
          onClick={() => {
            setEmail(suggestion)
            setErr(null)
          }}
          className="mt-2 rounded-full border border-accent/30 bg-accent/10 px-3 py-1 text-xs font-medium text-accent transition-colors hover:bg-accent/20"
        >
          Did you mean <span className="font-semibold">{suggestion}</span>?
        </button>
      ) : null}
      {err ? <p className="mt-2 text-xs text-bad">{err}</p> : null}
      <p className="mt-2 text-xs text-muted">
        No password. We use your email to save your reads — no spam.
      </p>
      {exampleLink ? (
        <p className="mt-3 text-center text-xs">
          <Link to="/example" className="text-accent underline-offset-4 hover:underline">
            See an example read first
          </Link>
        </p>
      ) : null}
    </form>
  )

  // One-tap Sign in with Apple — native app only (web keeps email-only).
  const nativeBlock = isNativeApp() ? (
    <div className="mb-3">
      <button
        type="button"
        onClick={() => void signInWithApple()}
        disabled={appleBusy || busy}
        className="flex w-full items-center justify-center gap-2 rounded-lg bg-black px-5 py-2.5 text-sm font-bold text-white transition-all hover:brightness-125 disabled:opacity-60"
      >
        <svg width="13" height="16" viewBox="0 0 384 512" fill="currentColor" aria-hidden="true">
          <path d="M318.7 268.7c-.2-36.7 16.4-64.4 50-84.8-18.8-26.9-47.2-41.7-84.7-44.6-35.5-2.8-74.3 20.7-88.5 20.7-15 0-49.4-19.7-76.4-19.7C63.3 141.2 4 184.8 4 273.5q0 39.3 14.4 81.2c12.8 36.7 59 126.7 107.2 125.2 25.2-.6 43-17.9 75.8-17.9 31.8 0 48.3 17.9 76.4 17.9 48.6-.7 90.4-82.5 102.6-119.3-65.2-30.7-61.7-90-61.7-91.9zm-56.6-164.2c27.3-32.4 24.8-61.9 24-72.5-24.1 1.4-52 16.4-67.9 34.9-17.5 19.8-27.8 44.3-25.6 71.9 26.1 2 49.9-11.4 69.5-34.3z" />
        </svg>
        {appleBusy ? 'One sec…' : 'Sign in with Apple'}
      </button>
      {appleErr ? <p className="mt-2 text-xs text-bad">{appleErr}</p> : null}
      <div className="my-3 flex items-center gap-3 text-xs text-muted">
        <span className="h-px flex-1 bg-border" /> or use email{' '}
        <span className="h-px flex-1 bg-border" />
      </div>
    </div>
  ) : null

  if (bare)
    return (
      <>
        {confirming ? (
          confirmPanel
        ) : (
          <>
            {nativeBlock}
            {form}
          </>
        )}
      </>
    )

  return (
    <div className="mx-auto w-full max-w-md rounded-2xl border border-border bg-surface p-6">
      <h2 className="text-lg font-semibold tracking-tight">{heading}</h2>
      <p className="mb-4 mt-1 text-sm text-muted">{sub}</p>
      {confirming ? (
        confirmPanel
      ) : (
        <>
          {nativeBlock}
          {form}
        </>
      )}
    </div>
  )
}
