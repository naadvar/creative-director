import { useEffect, useState } from 'react'
import { api } from '../api/client'
import Spinner from '../components/Spinner'
import VideoPage from './VideoPage'

// A curated fitness reel that reads well (grounded, a text-legibility lever with a
// timestamp, two blind spots, clean "what's working"). Used as the fallback when the
// dynamic pick can't resolve — verified present in the corpus.
const FALLBACK_ID = 'ig_DXU7n07kgfg'

// How many corpus candidates to probe before falling back. The /corpus listing
// already filters to grounded, visible reads; we probe a few to find one that also
// has enough substance (>=2 blind spots + a lever) to show off the read.
const PROBE = 5

/** Resolve the strongest fitness example read: pull a small high-tercile fitness
 * page, probe each candidate's read, and pick the first grounded one with >=2 blind
 * spots and a lever. Falls back to the curated id (and, last, whatever loads). */
async function pickExampleId(): Promise<string> {
  try {
    // High-tercile fitness first (a strong reel); the endpoint only returns reels
    // that have a visible (grounded) read.
    const page = await api.corpus({ niche: 'ig_fitness', tercile: 2, limit: 12 })
    const ids = page.videos.map((v) => v.video_id)
    // Try the curated id first if it's in the set, else scan the page.
    const ordered = [FALLBACK_ID, ...ids.filter((v) => v !== FALLBACK_ID)]
    for (const id of ordered.slice(0, PROBE + 1)) {
      try {
        const r = await api.craftRead(id)
        const read = r.available ? r.read : undefined
        if (
          read &&
          (read.blind_spots?.length ?? 0) >= 2 &&
          (read.biggest_opportunity ?? '').length > 10
        ) {
          return id
        }
      } catch {
        /* probe failed — try the next candidate */
      }
    }
  } catch {
    /* listing failed — use the curated fallback */
  }
  return FALLBACK_ID
}

/** The "See an example read first" destination: a real corpus read shown read-only,
 * before the sign-in wall. Resolves the example dynamically, then hands off to the
 * normal read page in example mode (banner + pinned "get your own" CTA). */
export default function ExamplePage() {
  const [id, setId] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    pickExampleId().then((resolved) => {
      if (!cancelled) setId(resolved)
    })
    // An anonymous visitor opened the example — the first-impression funnel signal.
    api.track('example_read_viewed')
    return () => {
      cancelled = true
    }
  }, [])

  if (!id) {
    return (
      <div className="grid min-h-[40vh] place-items-center">
        <Spinner label="Loading the example…" />
      </div>
    )
  }
  return <VideoPage example exampleId={id} />
}
