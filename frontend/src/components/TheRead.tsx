import type { PlainSummary } from '../api/types'

function CheckIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 14 14"
      fill="none"
      className="mt-0.5 shrink-0 text-good"
    >
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

function ArrowIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 14 14"
      fill="none"
      className="mt-0.5 shrink-0 text-accent"
    >
      <path
        d="M2.5 7h9M7.5 3l4 4-4 4"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export default function TheRead({ s }: { s: PlainSummary }) {
  return (
    <div className="rounded-2xl border border-border bg-surface p-5 sm:p-6">
      <h3 className="text-xs font-semibold uppercase tracking-widest text-muted">
        The read
      </h3>
      <p className="mt-2 text-lg leading-relaxed">{s.read}</p>

      {s.worth_trying.length > 0 ? (
        <div className="mt-5">
          <h4 className="text-sm font-semibold">
            Worth trying{' '}
            <span className="font-normal text-muted">
              — patterns winners share, not guarantees
            </span>
          </h4>
          <ul className="mt-2.5 space-y-2">
            {s.worth_trying.map((x, i) => (
              <li key={i} className="flex gap-2.5 text-sm leading-relaxed">
                <ArrowIcon />
                <span>
                  {x.text}
                  {x.is_proxy ? (
                    <span className="text-muted"> (weak signal)</span>
                  ) : null}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {s.strengths.length > 0 ? (
        <div className="mt-5">
          <h4 className="text-sm font-semibold">Already working</h4>
          <ul className="mt-2.5 space-y-2">
            {s.strengths.map((x, i) => (
              <li
                key={i}
                className="flex gap-2.5 text-sm leading-relaxed text-muted"
              >
                <CheckIcon />
                <span>{x}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  )
}
