import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { CategoryOption } from '../api/types'

interface CategoryPickerProps {
  videoId: string
  /** Fires after a successful save so the parent can refetch category-aware panels. */
  onChange?: (key: string | null) => void
}

/**
 * Content-category dropdown. Shows the classifier's guess (flagged as a guess
 * until the creator confirms it) and lets them correct it. Each correction is
 * saved as a confirmed pick — which both re-benchmarks the analysis and becomes
 * a free training label.
 */
export default function CategoryPicker({ videoId, onChange }: CategoryPickerProps) {
  const [options, setOptions] = useState<CategoryOption[]>([])
  const [current, setCurrent] = useState<string | null>(null)
  const [confirmed, setConfirmed] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoaded(false)
    api
      .category(videoId)
      .then((info) => {
        if (cancelled) return
        setOptions(info.options)
        setCurrent(info.current)
        setConfirmed(info.confirmed)
        setLoaded(true)
      })
      .catch(() => {
        if (!cancelled) setLoaded(true)
      })
    return () => {
      cancelled = true
    }
  }, [videoId])

  const onSelect = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const key = e.target.value === '' ? null : e.target.value
    setCurrent(key)
    setSaving(true)
    setError(null)
    api
      .setCategory(videoId, key)
      .then((info) => {
        setConfirmed(info.confirmed)
        onChange?.(key)
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : 'could not save')
      })
      .finally(() => setSaving(false))
  }

  if (!loaded) return null

  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="text-muted">Category</span>
      <span className="relative inline-block">
        <select
          value={current ?? ''}
          onChange={onSelect}
          disabled={saving}
          aria-label="Content category"
          className="appearance-none rounded-md border border-border bg-surface-2 py-1 pl-2.5 pr-7 text-text outline-none transition-colors focus:border-accent disabled:opacity-50"
        >
          <option value="">Uncategorized</option>
          {options.map((o) => (
            <option key={o.key} value={o.key}>
              {o.label}
            </option>
          ))}
        </select>
        <svg
          className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-muted"
          width="10"
          height="10"
          viewBox="0 0 10 10"
          fill="none"
          aria-hidden
        >
          <path
            d="M2 3.5 5 6.5 8 3.5"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
      {saving ? (
        <span className="text-xs text-muted">saving…</span>
      ) : error ? (
        <span className="text-xs text-bad">{error}</span>
      ) : current && !confirmed ? (
        <span
          className="text-xs text-mid"
          title="We guessed this from your caption — set it right and we’ll compare you to the correct winners."
        >
          our guess — confirm?
        </span>
      ) : null}
    </span>
  )
}
