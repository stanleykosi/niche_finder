'use client';

import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { ArrowIcon, PlusIcon } from '../components/Icon';
import { MetricCard } from '../components/MetricCard';
import { Shell } from '../components/Shell';
import { StatusPill } from '../components/StatusPill';
import { getHealth, getQuota, listRuns } from '../lib/api';
import { mostRecentSuccessfulRun } from '../lib/runSelection';
import { metadataSourceLabel } from '../lib/sourceProvenance';

export default function DashboardPage() {
  const runs = useQuery({ queryKey: ['runs'], queryFn: listRuns });
  const health = useQuery({ queryKey: ['health'], queryFn: getHealth });
  const quota = useQuery({ queryKey: ['quota'], queryFn: getQuota });
  const latestSuccessful = mostRecentSuccessfulRun(runs.data);
  return <Shell><div className="page-wrap">
    <div className="topline"><div><div className="eyebrow">YouTube niche intelligence / overview</div><h1>Find the signal<br/>inside the noise.</h1><p>Research repeatable formats with current demand, evidence-backed outliers, and a production path you can actually reproduce.</p></div><Link className="primary-button" href="/research/new"><PlusIcon width={17} height={17}/> New research</Link></div>
    <div className="metrics-grid"><MetricCard label="Research runs" value={runs.data?.length ?? '—'} detail="bounded investigations"/><MetricCard label="Last signal" value={latestSuccessful ? 'Ready' : '—'} detail={latestSuccessful?.seeds?.[0] ?? 'No successful run yet'} accent/><MetricCard label="Search budget" value={quota.data ? `${quota.data.remaining_search_calls}` : '—'} detail="API calls remaining"/><MetricCard label="Sources" value={health.data?.filter((item) => item.healthy).length ?? '—'} detail="healthy inputs"/></div>
    <div className="section-heading"><div><h2>Recent research</h2><p>Every result keeps its observation trail.</p></div><Link className="secondary-button" href="/research/new">Start from a seed <ArrowIcon width={16} height={16}/></Link></div>
    {runs.isLoading ? <div className="skeleton"/> : runs.isError ? <div className="error-box">The API is not reachable. Start the FastAPI control plane, then reload.</div> : runs.data?.length ? <div className="runs-list">{runs.data.map((run) => <Link href={`/runs/${run.id}`} className="run-row" key={run.id}><div><div className="run-title">{run.seeds[0] ?? 'Broad discovery'}</div><div className="run-seed">{run.requested_format.replace('_', ' ')} · {run.language} · {metadataSourceLabel(run.metadata_source, run.fixture_mode)}</div></div><StatusPill status={run.status} fixture={run.fixture_mode}/><div className="run-date">{run.completed_at ? new Date(run.completed_at).toLocaleDateString() : 'In progress'}</div><ArrowIcon width={17} height={17}/></Link>)}</div> : <div className="panel empty-panel"><div><div className="eyebrow">No research yet</div><h2>Start with one observable question.</h2><p>Give the engine a topic or format. Closed mode will walk the local fixture pipeline end to end.</p><Link className="primary-button" href="/research/new">Create first run <ArrowIcon width={16} height={16}/></Link></div></div>}
    <div className="section-heading"><div><h2>Source health</h2><p>Current runtime and provenance status.</p></div></div><div className="health-row">{health.data?.map((item) => <div className="health-chip" key={String(item.source)}><strong>{item.healthy ? '●' : '○'} {String(item.source).replace('_', ' ')}</strong> · {String(item.detail)}</div>) ?? <div className="health-chip">Loading source status…</div>}</div>
  </div></Shell>;
}
