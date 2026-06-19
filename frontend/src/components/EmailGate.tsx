import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'

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
}

/** Passwordless email gate: one field, no password. Submitting find-or-creates
 * the account, starts a session, and continues to `redirectTo`. */
export default function EmailGate({
  redirectTo = '/analyze',
  heading = 'Analyze your reel',
  sub = 'Enter your email to get a grounded craft read of your own short.',
  cta = 'Continue',
  bare = false,
}: Props) {
  const { refresh } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    setErr(null)
    try {
      await api.emailLogin(email)
      await refresh()
      navigate(redirectTo)
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

  const form = (
    <form onSubmit={onSubmit} className="w-full">
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          type="email"
          inputMode="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@email.com"
          className="min-w-0 flex-1 rounded-lg border border-border bg-ink px-3.5 py-2.5 text-sm text-text placeholder:text-muted/70 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
        />
        <button
          type="submit"
          disabled={busy}
          className="shrink-0 rounded-lg bg-accent px-5 py-2.5 text-sm font-semibold text-ink transition-opacity hover:opacity-90 disabled:opacity-60"
        >
          {busy ? 'One sec…' : cta}
        </button>
      </div>
      {err ? <p className="mt-2 text-xs text-bad">{err}</p> : null}
      <p className="mt-2 text-xs text-muted">
        No password. We use your email to save your reads — no spam.
      </p>
    </form>
  )

  if (bare) return form

  return (
    <div className="mx-auto w-full max-w-md rounded-2xl border border-border bg-surface p-6">
      <h2 className="text-lg font-semibold tracking-tight">{heading}</h2>
      <p className="mb-4 mt-1 text-sm text-muted">{sub}</p>
      {form}
    </div>
  )
}
