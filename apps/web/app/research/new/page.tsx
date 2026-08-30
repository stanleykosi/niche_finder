'use client';

import { FormEvent, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowIcon } from '../../../components/Icon';
import { Shell } from '../../../components/Shell';
import { createRun } from '../../../lib/api';

const supportedLanguage = 'English';
const productionOptions = [
  ['faceless', 'Faceless narration/captions'],
  ['low-editing', 'Low editing complexity'],
  ['stock-or-archive-footage', 'Stock/archive footage preferred'],
] as const;

export default function NewResearchPage() {
  const router = useRouter();
  const [format, setFormat] = useState('both');
  const [seed, setSeed] = useState('');
  const [region, setRegion] = useState('US');
  const [deep, setDeep] = useState(false);
  const [broad, setBroad] = useState(false);
  const [recency, setRecency] = useState(90);
  const [constraints, setConstraints] = useState<string[]>(['faceless']);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const marketSweep = broad && !seed.trim();

  function toggleConstraint(value: string, checked: boolean) {
    setConstraints((current) => checked
      ? Array.from(new Set([...current, value]))
      : current.filter((item) => item !== value));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError('');
    setBusy(true);
    const seeds = seed.split(',').map((value) => value.trim()).filter(Boolean);
    if (!broad && seeds.length === 0) {
      setError('Add a seed topic or enable broad discovery.');
      setBusy(false);
      return;
    }
    const limits = broad
      ? {
          max_queries: marketSweep ? (deep ? 20 : 12) : (deep ? 10 : 5),
          max_results_per_query: deep ? 10 : 8,
          max_channels: deep ? 50 : 30,
          max_videos: deep ? 100 : 80,
          max_expansion_depth: 1,
          deep_research: deep,
        }
      : { max_queries: deep ? 5 : 2, max_results_per_query: deep ? 20 : 12, max_channels: deep ? 10 : 6, max_videos: deep ? 50 : 30, max_expansion_depth: 1, deep_research: deep };
    try {
      const run = await createRun({
        requested_format: format,
        language: supportedLanguage,
        regions: [region],
        seeds,
        broad_discovery: broad,
        recency_days: recency,
        production_constraints: constraints,
        minimum_idea_ceiling: 10,
        minimum_clip_coverage: .7,
        minimum_successful_channels: 3,
        minimum_recent_outliers: 3,
        minimum_outlier_channels: 2,
        minimum_winner_loser_pairs: 3,
        maximum_saturation: .75,
        limits,
      });
      router.push(`/runs/${run.id}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Research could not start.');
      setBusy(false);
    }
  }

  return <Shell><div className="page-wrap">
    <div className="topline"><div>
      <div className="eyebrow">New investigation</div>
      <h1>What should we<br/>look at next?</h1>
      <p>Set a bounded research question. The engine will gather browser context, structured metadata, and a report with evidence links.</p>
    </div></div>
    <form className="panel form-panel" onSubmit={submit}>
      <div className="form-grid">
        <div className="field full">
          <label htmlFor="seed-topic">Seed topic or repeatable format (optional)</label>
          <input id="seed-topic" value={seed} onChange={(event) => setSeed(event.target.value)} placeholder="e.g. everyday visual experiments, ranking formats"/>
          <small>{marketSweep ? `Broad discovery will compare ${deep ? 20 : 12} concrete markets—not run a generic niche query.` : broad ? 'These seeds will anchor a broader bounded discovery scan.' : 'Use commas for multiple focused seeds.'}</small>
        </div>
        <div className="field">
          <label>Content shape</label>
          <div className="radio-group">{[['shorts', 'Shorts'], ['long_form', 'Long-form'], ['both', 'Both']].map(([value, label]) => <label className="radio-card" key={value}>
            <input type="radio" name="format" value={value} checked={format === value} onChange={(event) => setFormat(event.target.value)}/>
            <span>{label}</span>
          </label>)}</div>
        </div>
        <div className="field">
          <label htmlFor="language">Target language</label>
          <select id="language" value={supportedLanguage} disabled aria-describedby="language-support"><option>English</option></select>
          <small id="language-support">English is the supported MVP research language.</small>
        </div>
        <div className="field">
          <label htmlFor="region">Target region</label>
          <select id="region" value={region} onChange={(event) => setRegion(event.target.value)}><option>US</option><option>GB</option><option>NG</option><option>CA</option><option>AU</option></select>
        </div>
        <div className="field">
          <label>Discovery scope</label>
          <label className="radio-card"><input type="checkbox" checked={broad} onChange={(event) => setBroad(event.target.checked)}/><span>{broad ? 'Broad discovery enabled' : 'Focused seed validation'}</span></label>
          <small>Broad discovery can be anchored by seeds; focused validation requires at least one seed.</small>
        </div>
        <div className="field">
          <label htmlFor="recency">Discovery recency</label>
          <select id="recency" value={recency} onChange={(event) => setRecency(Number(event.target.value))}>
            <option value={45}>45 days</option><option value={90}>90 days</option><option value={180}>180 days</option><option value={365}>365 days</option>
          </select>
          <small>Decision cohorts remain bounded to the canonical 45/90-day evidence windows.</small>
        </div>
        <div className="field">
          <label>Research depth</label>
          <label className="radio-card"><input type="checkbox" checked={deep} onChange={(event) => setDeep(event.target.checked)}/><span>{deep ? 'Deep bounded scan' : 'Fast signal scan'}</span></label>
          <small>{marketSweep ? (deep ? 'Compare 20 markets, up to 100 videos, and 50 channels.' : 'Compare 12 markets, up to 80 videos, and 30 channels.') : (deep ? 'Up to 5 queries, 50 videos, and 10 channels.' : 'Up to 2 queries, 30 videos, and 6 channels.')}</small>
        </div>
        <div className="field full">
          <label>Production constraints</label>
          <div className="radio-group">{productionOptions.map(([value, label]) => <label className="radio-card" key={value}>
            <input type="checkbox" checked={constraints.includes(value)} onChange={(event) => toggleConstraint(value, event.target.checked)}/>
            <span>{label}</span>
          </label>)}</div>
          <small>Constraints are reported on ideas and production plans; they never hide demand evidence or weaken recommendation gates.</small>
        </div>
      </div>
      {error ? <div className="error-box" role="alert" style={{marginTop: 20}}>{error}</div> : null}
      <div className="form-actions">
        <button type="button" className="secondary-button" onClick={() => router.back()}>Cancel</button>
        <button type="submit" className="primary-button" disabled={busy}>{busy ? 'Building evidence…' : <>Run research <ArrowIcon width={16} height={16}/></>}</button>
      </div>
    </form>
  </div></Shell>;
}
