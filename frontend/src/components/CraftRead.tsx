import type { CraftReadData } from '../api/types'

function Check() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="mt-0.5 shrink-0 text-good">
      <path
        d="M2.5 7.5 5.5 10.5 11.5 3.5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/** Split a blind-spot string "m:ss - observation. Fix: ..." into its parts. */
function parseSpot(s: string): { where: string; observation: string; fix: string } {
  let where = ''
  let body = s.trim()
  const m = body.match(/^([0-9][0-9:.\s-]*?)\s*[-–—]\s*(.*)$/)
  if (m) {
    where = m[1].trim()
    body = m[2]
  }
  const fi = body.search(/\bfix:\s*/i)
  if (fi >= 0) {
    return {
      where,
      observation: body.slice(0, fi).trim().replace(/[.\s]+$/, ''),
      fix: body.slice(fi).replace(/^[^:]*:\s*/, '').trim(),
    }
  }
  return { where, observation: body, fix: '' }
}

const STRUCTURE: [string, (d: CraftReadData) => string][] = [
  ['Hook', (d) => d.hook],
  ['Payoff', (d) => d.payoff],
  ['Pacing', (d) => d.pacing],
]

export default function CraftRead({ data }: { data: CraftReadData }) {
  const spots = (data.blind_spots ?? []).map(parseSpot)
  return (
    <div className="rounded-2xl border border-border bg-surface p-5 sm:p-6">
      <h3 className="text-xs font-semibold uppercase tracking-widest text-muted">Craft read</h3>
      <p className="mt-2 text-lg leading-relaxed">{data.verdict}</p>

      {data.biggest_opportunity ? (
        <div className="mt-4 rounded-xl border border-accent/30 bg-accent/10 p-4">
          <div className="text-xs font-semibold uppercase tracking-widest text-accent">
            Biggest opportunity
          </div>
          <p className="mt-1.5 text-sm leading-relaxed">{data.biggest_opportunity}</p>
        </div>
      ) : null}

      {data.what_it_is ? (
        <p className="mt-4 text-sm leading-relaxed text-muted">{data.what_it_is}</p>
      ) : null}

      <div className="mt-4 grid gap-2.5 sm:grid-cols-3">
        {STRUCTURE.map(([k, get]) => (
          <div key={k} className="rounded-lg border border-border bg-surface-2 p-3">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">{k}</div>
            <p className="mt-1 text-[13px] leading-snug">{get(data)}</p>
          </div>
        ))}
      </div>

      {spots.length > 0 ? (
        <div className="mt-5">
          <h4 className="text-sm font-semibold">Blind spots — and how to fix them</h4>
          <ul className="mt-2.5 space-y-2.5">
            {spots.map((s, i) => (
              <li key={i} className="rounded-lg border border-border bg-surface-2 p-3">
                <div className="flex items-baseline gap-2">
                  {s.where ? (
                    <span className="shrink-0 text-[11px] font-medium text-muted">{s.where}</span>
                  ) : null}
                  <span className="text-sm leading-relaxed">{s.observation}</span>
                </div>
                {s.fix ? (
                  <div className="mt-1.5 flex gap-2 text-[13px] leading-relaxed">
                    <span className="shrink-0 font-medium text-accent">Fix</span>
                    <span>{s.fix}</span>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {data.done_well && data.done_well.length > 0 ? (
        <div className="mt-5">
          <h4 className="text-sm font-semibold">Done well</h4>
          <ul className="mt-2.5 space-y-2">
            {data.done_well.map((d, i) => (
              <li key={i} className="flex gap-2.5 text-sm leading-relaxed text-muted">
                <Check />
                <span>{d}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="mt-5 border-t border-border pt-3 text-xs text-muted">
        Read from your frames. Craft observations only — no performance or virality claims.
      </div>
    </div>
  )
}
