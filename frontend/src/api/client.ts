import type {
  AnalyzeHandleJob,
  AuthUser,
  UploadJobStatus,
  AutoCut,
  CategoryInfo,
  CorpusFacets,
  CorpusPage,
  CraftReadResponse,
  CutPlan,
  NicheList,
  ExampleList,
  FrameBreakdown,
  IngestResponse,
  MyReels,
  PlainSummary,
  Timeline,
  TrimRecompute,
  VideoBreakdown,
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
    throw new ApiError(0, 'Cannot reach the API — is the backend running on :8000?')
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

  analyze(id: string): Promise<VideoBreakdown> {
    return request<VideoBreakdown>(`/videos/${encodeURIComponent(id)}/analyze`)
  },

  summary(id: string): Promise<PlainSummary> {
    return request<PlainSummary>(`/videos/${encodeURIComponent(id)}/summary`)
  },

  /** The Craft X-ray read (grounded craft critic). {available:false} when not generated. */
  craftRead(id: string): Promise<CraftReadResponse> {
    return request<CraftReadResponse>(`/videos/${encodeURIComponent(id)}/craft-read`)
  },

  frame(id: string): Promise<FrameBreakdown> {
    return request<FrameBreakdown>(`/videos/${encodeURIComponent(id)}/frame`)
  },

  timeline(id: string): Promise<Timeline> {
    return request<Timeline>(`/videos/${encodeURIComponent(id)}/timeline`)
  },

  examples(id: string, feature: string): Promise<ExampleList> {
    return request<ExampleList>(
      `/videos/${encodeURIComponent(id)}/examples/${encodeURIComponent(feature)}`,
    )
  },

  /** Full CapCut-style cut plan (cuts, over-long holds, suggested intro trim). */
  cutplan(id: string): Promise<CutPlan> {
    return request<CutPlan>(`/videos/${encodeURIComponent(id)}/cutplan`)
  },

  /** Live recompute: which hook checks pass if the reel started at `trimStart`. */
  cutplanTrim(id: string, trimStart: number): Promise<TrimRecompute> {
    return request<TrimRecompute>(
      `/videos/${encodeURIComponent(id)}/cutplan?trim_start=${trimStart}`,
    )
  },

  /** Auto "winner cut" — kept segments (dead air removed) for virtual playback. */
  autocut(id: string): Promise<AutoCut> {
    return request<AutoCut>(`/videos/${encodeURIComponent(id)}/autocut`)
  },

  /** Current content category (creator-confirmed or classifier guess) + options. */
  category(id: string): Promise<CategoryInfo> {
    return request<CategoryInfo>(`/videos/${encodeURIComponent(id)}/category`)
  },

  /** Creator override: set (or clear with null) the content category. */
  setCategory(id: string, category: string | null): Promise<CategoryInfo> {
    return request<CategoryInfo>(`/videos/${encodeURIComponent(id)}/category`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ category }),
    })
  },

  /** Upload your own reel for analysis (multipart). Poll uploadStatus until done. */
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

  analyzeUrl(url: string, force = false): Promise<IngestResponse> {
    return request<IngestResponse>('/analyze-url', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, force }),
    })
  },

  /** Start scraping + featurising a creator's recent reels (background job). */
  analyzeHandle(handle: string, niche: string, maxReels = 6): Promise<AnalyzeHandleJob> {
    return request<AnalyzeHandleJob>('/analyze-handle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ handle, niche, max_reels: maxReels }),
    })
  },

  /** Poll a paste-handle job until status === 'done'. */
  analyzeHandleStatus(jobId: string): Promise<AnalyzeHandleJob> {
    return request<AnalyzeHandleJob>(`/analyze-handle/${encodeURIComponent(jobId)}`)
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

  myReels(): Promise<MyReels> {
    return request<MyReels>('/me/reels')
  },

  analyzeOwnReel(id: string): Promise<{ video_id: string }> {
    return request<{ video_id: string }>(
      `/me/reels/${encodeURIComponent(id)}/analyze`,
      { method: 'POST' },
    )
  },
}

/** Full-page redirect to start Instagram OAuth (not an XHR — the browser must
 * navigate so the OAuth cookies/redirects work). */
export const INSTAGRAM_CONNECT_URL = `${BASE}/auth/instagram/start`
