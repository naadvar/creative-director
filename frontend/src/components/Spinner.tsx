export default function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2.5 text-sm text-muted">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/15 border-t-accent" />
      {label ? <span>{label}</span> : null}
    </div>
  )
}
