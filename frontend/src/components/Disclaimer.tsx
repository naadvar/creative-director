export default function Disclaimer({ className = '' }: { className?: string }) {
  return (
    <p className={`text-xs leading-relaxed text-muted ${className}`}>
      A <span className="font-medium text-text/80">craft read</span> of the video in
      front of it — read frame by frame, grounded in what’s actually on screen. It flags
      what an editor would catch on a second watch. No performance or virality claims —
      nothing observable reliably predicts views.
    </p>
  )
}
