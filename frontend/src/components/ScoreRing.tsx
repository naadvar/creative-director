interface ScoreRingProps {
  value: number // 0-100
  color: string // hex
  caption?: string
  size?: number
  stroke?: number
}

export default function ScoreRing({
  value,
  color,
  caption,
  size = 168,
  stroke = 14,
}: ScoreRingProps) {
  const pct = Math.max(0, Math.min(100, value))
  const r = (size - stroke) / 2
  const circ = 2 * Math.PI * r
  const offset = circ * (1 - pct / 100)

  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="currentColor"
          strokeWidth={stroke}
          className="text-white/8"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circ}
          strokeDashoffset={offset}
          style={{ transition: 'stroke-dashoffset 0.7s ease' }}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center">
        <div className="text-center">
          <div className="text-4xl font-bold tabular-nums" style={{ color }}>
            {Math.round(pct)}
            <span className="text-xl font-semibold">%</span>
          </div>
          {caption ? (
            <div className="mt-0.5 text-[10px] font-medium uppercase tracking-widest text-muted">
              {caption}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}
