import type {
  AuthUser,
  CorpusFacets,
  CorpusPage,
  CraftReadResponse,
  Fingerprint,
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    // credentials: 'include' so the session cookie rides along (same-origin
    // via the Vite /api proxy in dev; real cookie domain in prod).
    res = await fetch(`${BASE}${path}`, { credentials: 'include', ...init })
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
  ): Promise<UploadJobStatus> {
    const form = new FormData()
    form.append('file', file)
    form.append('niche', niche)
    form.append('caption', caption)
    if (followers != null && !Number.isNaN(followers)) {
      form.append('followers', String(followers))
    }
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

  /** Passwordless email gate — find-or-create the user, start a session. */
  emailLogin(email: string): Promise<{ user: AuthUser | null }> {
    return request<{ user: AuthUser | null }>('/auth/email', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    })
  },

  logout(): Promise<{ ok: boolean }> {
    return request<{ ok: boolean }>('/auth/logout', { method: 'POST' })
  },

  /** The creator's own uploaded reels + their reads — the "My reads" history. */
  myUploads(): Promise<MyUploads> {
    return request<MyUploads>('/me/uploads')
  },

  /** The creator's style fingerprint, built from their own uploaded reels. */
  myFingerprint(): Promise<Fingerprint> {
    return request<Fingerprint>('/me/fingerprint')
  },

  /** The creator's craft trend over their own reads (recurring vs moved-past). */
  myProgress(): Promise<Progress> {
    return request<Progress>('/me/progress')
  },
}
