export function StatusPill({ status, fixture = false }: { status: string; fixture?: boolean }) {
  return <span className={`status-pill status-${status}`}><span className="status-dot"/>{status.replace('_', ' ')}{fixture ? <small> / fixture</small> : null}</span>;
}

