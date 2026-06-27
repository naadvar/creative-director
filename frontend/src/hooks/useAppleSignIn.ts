import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { SignInWithApple } from '@capacitor-community/apple-sign-in'
import { api, ApiError } from '../api/client'
import { useAuth } from './useAuth'

/**
 * Native Sign in with Apple. Triggers the system sheet, exchanges the returned
 * identity token with our API (which verifies it against Apple's public keys),
 * then continues exactly like the email gate: call `onDone` if provided, else
 * navigate to `redirectTo`. Only meaningful inside the native app — the button
 * that calls this is gated behind isNativeApp().
 */
export function useAppleSignIn(redirectTo = '/analyze', onDone?: () => void) {
  const { refresh } = useAuth()
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function signInWithApple() {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      const res = await SignInWithApple.authorize({
        // clientId/redirectURI are required by the plugin's web implementation;
        // on native iOS they're effectively unused (the system uses the app's
        // own bundle id), but the call rejects without them.
        clientId: 'com.creativedirector.app',
        redirectURI: 'https://creative-director-api-production.up.railway.app/auth/apple',
        scopes: 'name email',
      })
      const token = res.response?.identityToken
      if (!token) throw new Error('No identity token from Apple')
      await api.appleLogin(token, {
        givenName: res.response.givenName ?? undefined,
        familyName: res.response.familyName ?? undefined,
      })
      await refresh()
      if (onDone) onDone()
      else navigate(redirectTo)
    } catch (e: unknown) {
      // User cancelled the system sheet — not an error worth showing.
      const code = String((e as { code?: string })?.code ?? '')
      const msg = String((e as Error)?.message ?? '').toLowerCase()
      if (code === '1001' || msg.includes('cancel')) {
        // silent no-op
      } else {
        setError(
          e instanceof ApiError
            ? e.message
            : 'Sign in with Apple failed — try email instead.',
        )
      }
    } finally {
      setBusy(false)
    }
  }

  return { signInWithApple, busy, error }
}
