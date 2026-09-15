export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="state">
      <div className="spinner" />
      <p style={{ marginTop: 12 }}>{label}</p>
    </div>
  )
}

export function ErrorState({ error }: { error: unknown }) {
  const msg = error instanceof Error ? error.message : String(error)
  return (
    <div className="state state--error">
      <p>Couldn’t load this.</p>
      <p className="faint" style={{ fontSize: 12 }}>{msg}</p>
    </div>
  )
}

export function EmptyState({ children }: { children: React.ReactNode }) {
  return <div className="state">{children}</div>
}
