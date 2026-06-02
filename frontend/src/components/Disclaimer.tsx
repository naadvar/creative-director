import { platformNoun } from '../lib/format'

export default function Disclaimer({
  className = '',
  videoId,
}: {
  className?: string
  videoId?: string
}) {
  const noun = videoId ? platformNoun(videoId) : 'posts'
  return (
    <p className={`text-xs leading-relaxed text-muted ${className}`}>
      Findings are <span className="font-medium text-text/80">correlational</span> —
      patterns winning {noun} share, not proven causes — and predate velocity-curve
      labels. Treat this as a hypothesis generator, not validated advice.
    </p>
  )
}
