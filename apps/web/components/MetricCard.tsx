export function MetricCard({ label, value, detail, accent = false }: { label: string; value: string | number; detail: string; accent?: boolean }) {
  return <article className={`metric-card${accent ? ' metric-accent' : ''}`}><span className="eyebrow">{label}</span><strong>{value}</strong><span className="metric-detail">{detail}</span></article>;
}

