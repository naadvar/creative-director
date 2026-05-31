import { tercileStyle } from '../lib/format'

export default function TercileBadge({ tercile }: { tercile: number | null }) {
  const s = tercileStyle(tercile)
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold ${s.bg} ${s.border} ${s.text}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} />
      {s.name}
    </span>
  )
}
