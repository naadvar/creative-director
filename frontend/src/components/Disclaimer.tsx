export default function Disclaimer({ className = '' }: { className?: string }) {
  return (
    <p className={`text-xs leading-relaxed text-muted ${className}`}>
      Findings are <span className="font-medium text-text/80">correlational</span> —
      patterns winning Shorts share, not proven causes — and predate velocity-curve
      labels. Treat this as a hypothesis generator, not validated advice.
    </p>
  )
}
