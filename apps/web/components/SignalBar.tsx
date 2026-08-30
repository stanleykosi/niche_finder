export function SignalBar({ value, label, tone = 'amber' }: { value: number; label: string; tone?: 'amber' | 'blue' | 'green' }) {
  const safe = Math.max(0, Math.min(1, value));
  return <div className="signal-row"><div className="signal-label"><span>{label}</span><strong>{Math.round(safe * 100)}%</strong></div><div className={`signal-track signal-${tone}`}><span style={{ width: `${safe * 100}%` }}/></div></div>;
}

