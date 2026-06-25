// TypeScript mirror of the FastAPI response schemas (api/schemas.py).
// Kept in sync by hand — the API contract is small and stable.

export type Tier = 'small' | 'mid' | 'large'
export type BenchmarkScope = 'tier' | 'pooled'
export type Fixability = 'high' | 'medium' | 'low'
export type Trajectory = 'improving' | 'stable' | 'declining'

export interface Finding {
  feature: string
  label: string
  your_value: number | null
  benchmark_value: number
  unit: string
  direction: 'above' | 'below' | 'aligned' | string
  gap_ratio: number
  confidence: string
  causal: string
  off_benchmark: boolean
  fixability: Fixability
  rank_score: number
  trajectory: Trajectory | null
}

export interface PatternMatch {
  aligned: number
  total: number
  pct: number
}

export interface Recommendation {
  feature: string
  label: string
  advice: string
  your_value: number
  winner_value: number | null
  weight: number
}

export interface VideoBreakdown {
  video_id: string
  title: string
  channel: string
  duration_seconds: number | null
  archetype: string
  archetype_n: number
  label_scheme: string | null
  tercile: number | null
  score: number | null
  tier: Tier | null
  benchmark_scope: BenchmarkScope
  findings: Finding[]
  pattern_match: PatternMatch | null
  recommendations: Recommendation[]
}

export interface Suggestion {
  text: string
  clause: string
  gap: number
  is_proxy: boolean
}

export interface WatchWinner {
  video_id: string
  title: string
  channel: string
  value: number
  benchmark_value: number
  duration_seconds: number | null
}

// An honest, grounded observation about the reel — derived from real frame
// detail, framed as something we noticed, not a fix-or-fail directive.
// Often empty ([]) when there's nothing solid to say.
export interface CraftNote {
  kind: string
  note: string
  evidence: string
}

// The Craft X-ray — the grounded craft-critic read (advice/craft_xray.py).
export interface CraftReadData {
  on_screen_text_found: string[]
  what_it_is: string
  hook: string
  payoff: string
  pacing: string
  verdict: string
  biggest_opportunity: string
  // the craft dimension the opportunity targets (hook|pacing|cut|framing|payoff|…), set by the
  // lever synthesis / vision re-read. Absent on older reads.
  opportunity_dimension?: string
  // a "m:ss" moment the opportunity points at, for tap-to-jump. Absent on older reads.
  lever_timestamp?: string
  // each blind spot is one string shaped "m:ss - observation. Fix: ..."
  blind_spots: string[]
  done_well: string[]
}

export interface CraftReadMeta {
  video_id: string
  title: string
  channel: string | null
  duration_seconds: number | null
  is_upload: boolean
}

export interface CraftReadResponse {
  available: boolean
  suppressed?: boolean
  read?: CraftReadData
  meta?: CraftReadMeta | null
}

export interface PlainSummary {
  archetype: string
  read: string
  worth_trying: Suggestion[]
  strengths: string[]
  // Honest grounded observations, surfaced above worth_trying. Often [].
  craft_notes: CraftNote[]
  watch_winners: WatchWinner[]
  // Heading for the winners row, e.g. "Winners that nail pacing". Null when there's nothing to show.
  watch_winners_label: string | null
}

export interface FrameBreakdown {
  video_id: string
  title: string
  archetype: string
  duration: number
  findings: string[]
}

export interface TimelineSecond {
  second: number
  deviation: number | null
  reason: string | null
  parts: Record<string, number>
}

export interface TimelineSummary {
  dev_mean: number
  dev_max: number
  dev_worst_rel: number
  dev_hook_mean: number
  dev_body_mean: number
  dev_front_back: number
  dev_flagged_frac: number
}

export interface Timeline {
  video_id: string
  seconds: TimelineSecond[]
  summary: TimelineSummary | null
}

export interface CorpusVideo {
  video_id: string
  title: string
  channel: string
  thumbnail_url: string | null
  duration_seconds: number | null
  published_at: string | null
  tercile: number | null
  score: number | null
  category: string | null
  category_label: string | null
}

export interface CorpusPage {
  label_scheme: string
  niche: string
  total: number
  count: number
  limit: number
  offset: number
  videos: CorpusVideo[]
}

export interface CategoryCount {
  key: string
  label: string
  count: number
}

export interface CorpusFacets {
  total: number
  categories: CategoryCount[]
}

export interface NicheInfo {
  niche: string
  label: string
  platform: 'instagram' | 'youtube' | string
  count: number
}

export interface NicheList {
  niches: NicheInfo[]
}

export interface IngestResponse {
  video_id: string
  cached: boolean
  duration: number | null
  messages: string[]
}

export interface ExampleVideo {
  video_id: string
  title: string
  channel: string
  value: number
  benchmark_value: number
  duration_seconds: number | null
}

export interface ExampleList {
  feature: string
  benchmark_value: number
  examples: ExampleVideo[]
}

// --- content category (classifier guess + creator override) ---
export interface CategoryOption {
  key: string
  label: string
}

export interface CategoryInfo {
  video_id: string
  current: string | null
  current_label: string
  confirmed: boolean
  guess: string | null
  options: CategoryOption[]
}

// --- CapCut-style cut plan ---
export interface ShotHold {
  start: number
  end: number
  length: number
}

export interface CutSuggestion {
  second: number
  type: 'first_cut' | 'long_hold' | string
  message: string
}

export interface CutPlan {
  video_id: string
  archetype: string
  duration: number
  category: string | null
  category_label: string
  benchmark_scope: 'category' | 'tier'
  your_first_cut: number | null
  winner_first_cut: number | null
  your_cuts: number[]
  your_hook_face_pct: number
  winner_hook_face_pct: number | null
  winner_avg_shot: number | null
  over_long_holds: ShotHold[]
  suggestions: CutSuggestion[]
  suggested_trim_start: number | null
}

export interface TrimCheck {
  label: string
  pass: boolean
}

// --- auto "winner cut" (virtual dead-air edit) ---
export interface CutSegment {
  start: number
  end: number
}

export interface RemovedSegment {
  start: number
  end: number
  reason: string
}

export interface AutoCut {
  video_id: string
  archetype: string
  category: string | null
  category_label: string
  benchmark_scope: 'category' | 'tier'
  original_duration: number
  new_duration: number
  removed_seconds: number
  changed: boolean
  segments: CutSegment[]
  removed: RemovedSegment[]
  winner_first_cut: number | null
  winner_avg_shot: number | null
}

export interface TrimRecompute {
  trim_start: number
  checks: TrimCheck[]
  aligned: number
  total: number
}

// --- auth + creator ---
export interface Connection {
  platform: string
  username: string | null
  account_type: string | null
  connected_at: string | null
}

export interface AuthUser {
  id: number
  display_name: string | null
  email: string | null
  connections: Connection[]
}

export interface FingerprintRecurring {
  type: string
  label: string
  count: number
}

export interface Fingerprint {
  ready: boolean
  n_reels: number
  niche?: string | null
  format?: string | null
  format_label?: string | null
  recurring?: FingerprintRecurring[]
  summary: string
}

export interface ReelCard {
  id: string
  video_id: string | null // set when already analyzable -> link straight to dashboard
  thumbnail_url: string | null
  permalink: string | null
  caption: string
  timestamp: string | null
  like_count: number | null
  comments_count: number | null
  tercile: number | null // performance grade when analyzed (0 low, 1 mid, 2 high)
  score: number | null
}

export interface MyReels {
  username: string | null
  count: number
  reels: ReelCard[]
}

// --- the creator's own uploaded reels + reads ("My reads" history) ---
export interface UploadCard {
  video_id: string
  title: string
  niche: string | null
  created_at: string | null
  duration_seconds: number | null
  thumbnail_url: string | null
  available: boolean // a grounded read exists (not suppressed/missing)
  verdict: string | null
  biggest_opportunity: string | null
  dimension: string | null
}

export interface MyUploads {
  count: number
  uploads: UploadCard[]
}

// --- upload-your-reel analysis job (POST /upload, poll GET /upload/{id}) ---
export interface UploadJobStatus {
  job_id: string
  status: 'running' | 'done' | 'error' | string
  message: string
  video_id: string
  niche: string
  error: string | null
}

// --- paste-handle analysis job (POST /analyze-handle, poll GET /analyze-handle/{id}) ---
export interface AnalyzeHandleJob {
  job_id: string
  status: 'running' | 'done' | 'error' | string
  message: string
  handle: string
  niche: string
  video_ids: string[]
  error: string | null
}
