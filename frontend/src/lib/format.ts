// Display helpers shared across the UI.

import type { Fixability, Tier } from '../api/types'

export interface TercileStyle {
  name: string
  text: string
  bg: string
  border: string
  dot: string
}

const TIER_LABEL: Record<Tier, string> = {
  small: 'Small',
  mid: 'Mid',
  large: 'Large',
}
const TIER_RANGE: Record<Tier, string> = {
  small: '< 100K followers',
  mid: '100K - 1M followers',
  large: '1M+ followers',
}

/** Short label for a creator size tier ("Small" / "Mid" / "Large"). */
export function tierLabel(tier: Tier | null | undefined): string {
  return tier ? TIER_LABEL[tier] : 'Unknown'
}

/** Follower-count range that defines a tier. */
export function tierRange(tier: Tier | null | undefined): string {
  return tier ? TIER_RANGE[tier] : 'size unknown'
}

export interface FixabilityStyle {
  label: string  // 2-3 word badge text
  blurb: string  // hover-tooltip / accessible description
  text: string
  bg: string
  border: string
}

const FIX_STYLE: Record<Fixability, FixabilityStyle> = {
  high: {
    label: 'quick win',
    blurb: 'Edit or copy change. Can fix in the next 10 minutes.',
    text: 'text-good',
    bg: 'bg-good/10',
    border: 'border-good/30',
  },
  medium: {
    label: 'reshoot / re-cut',
    blurb: 'Requires a re-cut or a deliberate shift on the next upload.',
    text: 'text-mid',
    bg: 'bg-mid/10',
    border: 'border-mid/30',
  },
  low: {
    label: 'structural',
    blurb: 'Changing this changes the kind of video you make. Not really actionable on this one.',
    text: 'text-muted',
    bg: 'bg-white/5',
    border: 'border-border',
  },
}

export function fixabilityStyle(fix: Fixability): FixabilityStyle {
  return FIX_STYLE[fix]
}

/** Tailwind classes + label for a performance tercile (0 low, 1 mid, 2 high). */
export function tercileStyle(tercile: number | null): TercileStyle {
  switch (tercile) {
    case 2:
      return {
        name: 'High performer',
        text: 'text-good',
        bg: 'bg-good/12',
        border: 'border-good/40',
        dot: 'bg-good',
      }
    case 1:
      return {
        name: 'Mid performer',
        text: 'text-mid',
        bg: 'bg-mid/12',
        border: 'border-mid/40',
        dot: 'bg-mid',
      }
    case 0:
      return {
        name: 'Low performer',
        text: 'text-bad',
        bg: 'bg-bad/12',
        border: 'border-bad/40',
        dot: 'bg-bad',
      }
    default:
      return {
        name: 'Unlabeled',
        text: 'text-muted',
        bg: 'bg-white/5',
        border: 'border-border',
        dot: 'bg-muted',
      }
  }
}

const ARCHETYPE_NAME: Record<string, string> = {
  talking: 'Voiceover / talking',
  demo: 'Silent / visual demo',
}

export function archetypeName(archetype: string): string {
  return ARCHETYPE_NAME[archetype] ?? archetype
}

/** Seconds -> "1:05" or "42s". */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return '—'
  if (seconds < 60) return `${seconds}s`
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

/** mm:ss timestamp for a timeline second. */
export function timestamp(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

/** Map a 0-1 deviation to a green -> amber -> red hex colour (null -> grey). */
export function deviationColor(dev: number | null): string {
  if (dev == null) return '#33333f'
  const d = Math.max(0, Math.min(1, dev / 0.8)) // saturate at 0.8 so reds are reachable
  let r: number
  let g: number
  let b: number
  if (d < 0.5) {
    const t = d / 0.5
    r = 0x27 + t * 0xca
    g = 0xae + t * 0x16
    b = 0x60 - t * 0x51
  } else {
    const t = (d - 0.5) / 0.5
    r = 0xf1 - t * 0x31
    g = 0xc4 - t * 0x8b
    b = 0x0f + t * 0x1c
  }
  const hex = (v: number) => Math.round(v).toString(16).padStart(2, '0')
  return `#${hex(r)}${hex(g)}${hex(b)}`
}

/** URL for a video's cached thumbnail (works for YT + IG via the API). */
export function thumbnailUrl(videoId: string): string {
  return `/api/videos/${encodeURIComponent(videoId)}/thumbnail`
}

/** External viewing URL — IG reels use the shortcode after the `ig_` prefix.
 * Uploaded reels (`up_`) have no external page; callers should hide the link. */
export function externalUrl(videoId: string): string {
  if (videoId.startsWith('up_')) return ''
  if (videoId.startsWith('ig_')) {
    return `https://www.instagram.com/reel/${videoId.slice(3)}/`
  }
  return `https://www.youtube.com/shorts/${videoId}`
}

/** What the source platform calls short-form video: "Reels" (IG + uploads) vs "Shorts". */
export function platformNoun(videoId: string): string {
  return videoId.startsWith('ig_') || videoId.startsWith('up_') ? 'Reels' : 'Shorts'
}

/** @deprecated — kept for callers still using the YouTube-only name. */
export function youtubeUrl(videoId: string): string {
  return externalUrl(videoId)
}

/** Round to one decimal, dropping a trailing ".0". */
export function round1(n: number): string {
  return Number(n.toFixed(1)).toString()
}
