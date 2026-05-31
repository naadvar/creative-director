import { useState } from 'react'
import type { ReactNode } from 'react'

interface CollapsibleProps {
  title: string
  subtitle?: string
  defaultOpen?: boolean
  children: ReactNode
}

export default function Collapsible({
  title,
  subtitle,
  defaultOpen = false,
  children,
}: CollapsibleProps) {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <div className="rounded-xl border border-border bg-surface">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-3 px-5 py-3.5 text-left"
      >
        <span>
          <span className="text-sm font-medium">{title}</span>
          {subtitle ? (
            <span className="ml-2 text-xs text-muted">{subtitle}</span>
          ) : null}
        </span>
        <svg
          width="14"
          height="14"
          viewBox="0 0 14 14"
          fill="none"
          className={`shrink-0 text-muted transition-transform ${open ? 'rotate-180' : ''}`}
        >
          <path
            d="M3.5 5.25 7 8.75l3.5-3.5"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>
      {open ? (
        <div className="border-t border-border px-5 py-4">{children}</div>
      ) : null}
    </div>
  )
}
