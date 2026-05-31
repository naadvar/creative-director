import type { FrameBreakdown } from '../api/types'

function isAligned(finding: string): boolean {
  const f = finding.toLowerCase()
  return f.includes('aligned') || f.includes('in line')
}

export default function FrameFindings({ fb }: { fb: FrameBreakdown }) {
  if (fb.findings.length === 0) {
    return <p className="text-sm text-muted">No frame-level findings.</p>
  }
  return (
    <ul className="space-y-2.5">
      {fb.findings.map((finding, i) => {
        const ok = isAligned(finding)
        return (
          <li key={i} className="flex gap-2.5 text-sm leading-relaxed">
            <span
              className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${
                ok ? 'bg-good' : 'bg-mid'
              }`}
            />
            <span className={ok ? 'text-muted' : ''}>{finding}</span>
          </li>
        )
      })}
    </ul>
  )
}
