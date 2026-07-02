import type {
  AuthUser,
  CorpusFacets,
  CorpusPage,
  CraftReadResponse,
  Fingerprint,
  IdeaResponse,
  MyUploads,
  NicheList,
  Progress,
  UploadJobStatus,
} from './types'

// Defaults to the Vite dev proxy (see vite.config.ts); override with VITE_API_BASE.
const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '/api'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
    this.name = 'ApiError'
  }
}

// Bearer token for the native (Capacitor) app, where the session cookie can't ride
// cross-origin to the API. Stored on login, sent on every request. The web app also
// gets the cookie, so the token is belt-and-suspenders there.
const TOKEN_KEY = 'cd_auth_token'
// Only the native (Capacitor) app needs the token — the web keeps using the httponly
// cookie (no token in localStorage there, so no XSS-stealable credential on web).
export function isNativeApp(): boolean {
  return !!(globalThis as { Capacitor?: { isNativePlatform?: () => boolean } }).Capacitor?.isNativePlatform?.()
}
export function authToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}
export function setAuthToken(t: string | null): void {
  try {
    if (t) localStorage.setItem(TOKEN_KEY, t)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* storage unavailable — fall back to cookie-only (web) */
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  const tok = authToken()
  if (tok) headers.set('Authorization', `Bearer ${tok}`)
  let res: Response
  try {
    // credentials: 'include' so the session cookie rides along (web); the Bearer
    // header carries auth for the native app.
    res = await fetch(`${BASE}${path}`, { credentials: 'include', ...init, headers })
  } catch {
    throw new ApiError(0, 'Cannot reach the API — is the backend running?')
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = (await res.json()) as { detail?: unknown }
      if (body?.detail) {
        detail =
          typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
      }
    } catch {
      /* response had no JSON body — keep the status-line detail */
    }
    throw new ApiError(res.status, detail)
  }
  return (await res.json()) as T
}

interface CorpusParams {
  tercile?: number
  niche?: string
  category?: string
  q?: string
  limit?: number
  offset?: number
}

/** Browser-loadable URL for the archived mp4 (streams from the FastAPI backend). */
export function videoFileUrl(id: string): string {
  return `${BASE}/videos/${encodeURIComponent(id)}/file`
}

/** Resolve a backend-relative media path (e.g. "/api/videos/{id}/thumbnail") to a
 * loadable URL. These go straight into <img>/<video> src and bypass request(), so
 * in the native app — where there's no Vercel "/api" proxy — the "/api" prefix must
 * be rewritten to the real API origin (BASE). On web, BASE is "/api", so unchanged. */
export function mediaUrl(path: string | null | undefined): string {
  if (!path) return ''
  return path.startsWith('/api/') ? `${BASE}${path.slice(4)}` : path
}

export const api = {
  // --- example corpus (browse) ---
  corpus(params: CorpusParams = {}): Promise<CorpusPage> {
    const qp = new URLSearchParams()
    if (params.tercile !== undefined) qp.set('tercile', String(params.tercile))
    if (params.niche) qp.set('niche', params.niche)
    if (params.category) qp.set('category', params.category)
    if (params.q) qp.set('q', params.q)
    if (params.limit !== undefined) qp.set('limit', String(params.limit))
    if (params.offset !== undefined) qp.set('offset', String(params.offset))
    const qs = qp.toString()
    return request<CorpusPage>(`/corpus${qs ? `?${qs}` : ''}`)
  },

  corpusCategories(niche?: string): Promise<CorpusFacets> {
    const qs = niche ? `?niche=${encodeURIComponent(niche)}` : ''
    return request<CorpusFacets>(`/corpus/categories${qs}`)
  },

  niches(): Promise<NicheList> {
    return request<NicheList>('/niches')
  },

  // --- the craft read (grounded craft critic) ---
  /** The Craft X-ray read + lightweight video meta. {available:false} when not generated. */
  craftRead(id: string): Promise<CraftReadResponse> {
    return request<CraftReadResponse>(`/videos/${encodeURIComponent(id)}/craft-read`)
  },

  /** Record helpful / not-useful / not-in-reel feedback on a craft-read note. */
  noteFeedback(videoId: string, note: string, reason?: string): Promise<{ ok: boolean }> {
    return request<{ ok: boolean }>(`/videos/${encodeURIComponent(videoId)}/note-feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ note, reason }),
    })
  },

  // --- upload your own reel (POST /upload, poll GET /upload/{id}) ---
  upload(
    file: File,
    niche: string,
    caption: string,
    followers?: number,
    priorVideoId?: string,
    ideaId?: string,
  ): Promise<UploadJobStatus> {
    const form = new FormData()
    form.append('file', file)
    form.append('niche', niche)
    form.append('caption', caption)
    if (followers != null && !Number.isNaN(followers)) {
      form.append('followers', String(followers))
    }
    // Set when this upload re-checks a prior reel's fix → backend computes the verdict.
    if (priorVideoId) form.append('prior_video_id', priorVideoId)
    // Set when this upload shoots a generated DNA idea → joins idea → read for later.
    if (ideaId) form.append('idea_id', ideaId)
    // No Content-Type header — the browser sets the multipart boundary itself.
    return request<UploadJobStatus>('/upload', { method: 'POST', body: form })
  },

  uploadStatus(jobId: string): Promise<UploadJobStatus> {
    return request<UploadJobStatus>(`/upload/${encodeURIComponent(jobId)}`)
  },

  // --- auth + creator ---
  me(): Promise<{ user: AuthUser | null }> {
    return request<{ user: AuthUser | null }>('/auth/me')
  },

  /** Passwordless email gate — find-or-create the user, start a session. Stores the
   * bearer token (used by the native app; harmless on web). */
  emailLogin(email: string): Promise<{ user: AuthUser | null }> {
    return request<{ user: AuthUser | null; token?: string }>('/auth/email', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    }).then((r) => {
      if (r.token && isNativeApp()) setAuthToken(r.token) // web stays cookie-only
      return r
    })
  },

  /** Native Sign in with Apple — verify the Apple identity token server-side and
   * find-or-create the user by their Apple id. Native-only; web is unaffected.
   * Same response shape as emailLogin, including the bearer token for the app. */
  appleLogin(
    identityToken: string,
    opts?: { givenName?: string; familyName?: string },
  ): Promise<{ user: AuthUser | null }> {
    return request<{ user: AuthUser | null; token?: string }>('/auth/apple', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        identityToken,
        givenName: opts?.givenName,
        familyName: opts?.familyName,
      }),
    }).then((r) => {
      if (r.token && isNativeApp()) setAuthToken(r.token) // web stays cookie-only
      return r
    })
  },

  logout(): Promise<{ ok: boolean }> {
    setAuthToken(null)
    return request<{ ok: boolean }>('/auth/logout', { method: 'POST' })
  },

  /** The creator's own uploaded reels + their reads — the "My reads" history. */
  myUploads(): Promise<MyUploads> {
    return request<MyUploads>('/me/uploads')
  },

  /** Delete one of the creator's own uploaded reels (removes it from Library,
   * DNA and Growth, and frees its stored files). */
  deleteUpload(videoId: string): Promise<{ ok: boolean }> {
    return request<{ ok: boolean }>(`/me/uploads/${encodeURIComponent(videoId)}`, {
      method: 'DELETE',
    })
  },

  /** The creator's style fingerprint, built from their own uploaded reels. */
  myFingerprint(): Promise<Fingerprint> {
    return request<Fingerprint>('/me/fingerprint')
  },

  /** The creator's craft trend over their own reads (recurring vs moved-past). */
  myProgress(): Promise<Progress> {
    return request<Progress>('/me/progress')
  },

  /** One grounded idea for the creator's next reel, built from their own reads.
   * fresh=true regenerates (daily-capped — a 429 carries the honest message). */
  myIdea(fresh = false): Promise<IdeaResponse> {
    return request<IdeaResponse>(`/me/idea${fresh ? '?fresh=1' : ''}`)
  },

  /** One-tap quality signal on a generated idea. */
  ideaFeedback(ideaId: string, rating: 'helpful' | 'not_for_me'): Promise<{ ok: boolean }> {
    return request<{ ok: boolean }>(`/me/idea/${encodeURIComponent(ideaId)}/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rating }),
    })
  },
}
