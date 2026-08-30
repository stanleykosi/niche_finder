'use client';

import Link from 'next/link';
import { use } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ArrowIcon } from '../../../../../components/Icon';
import { Shell } from '../../../../../components/Shell';
import { SignalBar } from '../../../../../components/SignalBar';
import { getReport } from '../../../../../lib/api';
import {
  candidateEvidenceDetails,
  conservativeMetric,
  gateSummary,
  mediaAssessmentSlices,
  mediaNarrativeSlices,
  type MediaNarrativeSlice,
} from '../../../../../lib/mediaAssessments';

export default function NicheDetailPage({ params }: { params: Promise<{ id: string; candidateId: string }> }) {
  const { id, candidateId } = use(params);
  const report = useQuery({ queryKey: ['report', id], queryFn: () => getReport(id) });
  if (report.isLoading) return <Shell><div className="page-wrap"><div className="skeleton"/></div></Shell>;
  if (report.isError) return <Shell><div className="page-wrap"><div className="error-box">This report could not be loaded.</div></div></Shell>;

  const candidate = report.data?.candidates.find((item) => item.id === candidateId);
  if (!candidate) return <Shell><div className="page-wrap"><div className="error-box">Niche opportunity not found in this report.</div></div></Shell>;

  const assessmentSlices = mediaAssessmentSlices(candidate);
  const narrativeSlices = mediaNarrativeSlices(candidate);
  const evidenceDetails = candidateEvidenceDetails(candidate);
  const gates = gateSummary(assessmentSlices);
  const demandScore = candidate.demand_assessment.score ?? conservativeMetric(assessmentSlices, 'demand', 'score');
  const validatedIdeas = candidate.clip_ceiling.validated_count ?? conservativeMetric(assessmentSlices, 'clip', 'validated_count');
  const clipCoverage = candidate.clip_ceiling.asset_coverage ?? conservativeMetric(assessmentSlices, 'clip', 'asset_coverage');
  const recommendationSummary = candidate.bridge_assessment?.reason
    ?? narrativeSlices.map((slice) => slice.synthesis.executive_summary).filter(Boolean).join(' ')
    ?? 'The decision is evidence-gated.';

  return <Shell><div className="page-wrap">
    <div className="detail-header"><div><div className="eyebrow">Opportunity 0{candidate.rank} · {candidate.broad_market}</div><h1>{candidate.niche}</h1><p>{candidate.sub_niche} · {candidate.repeatable_format}</p></div><Link href={`/runs/${id}`} className="secondary-button"><ArrowIcon width={16} height={16} style={{transform:'rotate(180deg)'}}/> Back to run</Link></div>
    <div className="detail-columns">
      <div className="stack">
        <section className="panel"><div className="eyebrow">Recommendation · {gates.passed}/{gates.total} gates</div><h2 style={{marginTop:8}}>{candidate.verdict}</h2><p className="panel-copy" style={{marginTop:8}}>{recommendationSummary || 'The decision is evidence-gated.'} Confidence after critic review: {Math.round(candidate.confidence * 100)}%.</p><div className="signal-group"><SignalBar label="Demand" value={demandScore} tone="blue"/><SignalBar label="Validated ideas" value={Math.min(1, validatedIdeas / 10)} tone="amber"/><SignalBar label="Clip coverage" value={clipCoverage} tone="green"/></div></section>
        <SupportingEvidencePanel details={evidenceDetails}/>
        <MajorOutliersPanel outliers={evidenceDetails.majorOutliers}/>
        {narrativeSlices.map((slice) => <NarrativePanel key={slice.key} slice={slice} fallbackMechanism={candidate.primary_viral_mechanism}/>)}
        {narrativeSlices.map((slice) => <CriticPanel key={slice.key} slice={slice}/>)}
      </div>
      <div className="stack">
        <section className="panel"><div className="eyebrow">Candidate-specific action plan</div><h2 style={{marginTop:8}}>Run the smallest useful test.</h2><div className="stack" style={{marginTop:14}}>{narrativeSlices.map((slice) => <CandidateActionPlan key={slice.key} slice={slice}/>)}</div></section>
        <RiskAndDifferentiationPanel details={evidenceDetails}/>
        <section className="panel"><div className="eyebrow">Evidence references</div><h2 style={{marginTop:8}}>{candidate.evidence_ids.length} attached records</h2><p className="panel-copy" style={{marginTop:8}}>Every AI statement is validated against this run&apos;s evidence ledger. Unknown citations cannot support a positive recommendation.</p><Link href={`/runs/${id}?tab=Evidence`} className="secondary-button" style={{marginTop:16}}>View evidence <ArrowIcon width={16} height={16}/></Link></section>
      </div>
    </div>
  </div></Shell>;
}

function SupportingEvidencePanel({ details }: { details: ReturnType<typeof candidateEvidenceDetails> }) {
  return <section className="panel"><div className="eyebrow">Supporting evidence</div><h2 style={{marginTop:8}}>{details.channels.length} channel cohort{details.channels.length === 1 ? '' : 's'} · {details.supportingVideos.length} observed video{details.supportingVideos.length === 1 ? '' : 's'}</h2><div className="evidence-list">{details.channels.map((channel) => <div className="evidence-item" key={`${channel.assessment_label}:${channel.channel_id}`}><strong>{channel.assessment_label} · {channel.channel_id}</strong><p>{formatCount(channel.uploads_analyzed)} uploads analyzed · {channel.successful ? 'repeatable success observed' : 'success gate not established'} · {Math.round(Number(channel.outlier_frequency ?? 0) * 100)}% outlier frequency</p></div>)}{details.supportingVideos.map((video) => <div className="evidence-item" key={`${video.assessment_label}:${video.video_id}`}><strong>{video.assessment_label} · {video.title ?? video.video_id}</strong><p>{formatMultiple(video.outlier_multiple)} same-channel baseline · {formatCount(video.view_count)} lifetime views · {String(video.recency_bucket ?? 'unknown')} evidence</p>{video.canonical_url ? <a href={String(video.canonical_url)} target="_blank" rel="noreferrer" className="secondary-button" style={{marginTop:10}}>Open source video <ArrowIcon width={14} height={14}/></a> : null}</div>)}{!details.channels.length && !details.supportingVideos.length ? <div className="evidence-item"><strong>No supporting records were persisted.</strong><p>This opportunity cannot be independently inspected from the candidate payload.</p></div> : null}</div></section>;
}

function MajorOutliersPanel({ outliers }: { outliers: ReturnType<typeof candidateEvidenceDetails>['majorOutliers'] }) {
  return <section className="panel"><div className="eyebrow">Major outliers</div><h2 style={{marginTop:8}}>{outliers.length ? `${outliers.length} current major outlier${outliers.length === 1 ? '' : 's'}` : 'No current major outlier observed'}</h2><div className="evidence-list">{outliers.map((video) => <div className="evidence-item" key={`${video.assessment_label}:${video.video_id}`}><strong>{video.assessment_label} · {formatMultiple(video.outlier_multiple)} baseline</strong><p>{video.title ?? video.video_id} · channel {video.channel_id} · {formatCount(video.views_per_day)} views/day</p></div>)}{!outliers.length ? <div className="evidence-item"><strong>Major-outlier evidence is absent.</strong><p>The recommendation must rely on the separately reported current-outlier and repeatability gates.</p></div> : null}</div></section>;
}

function RiskAndDifferentiationPanel({ details }: { details: ReturnType<typeof candidateEvidenceDetails> }) {
  return <section className="panel"><div className="eyebrow">Risks and differentiation</div><h2 style={{marginTop:8}}>Know what could break the thesis.</h2><div className="evidence-list">{details.risks.map((risk) => <div className="evidence-item" key={`risk:${risk.assessment_label}:${risk.text}`}><strong>{risk.assessment_label} risk</strong><p>{risk.text}</p></div>)}{details.differentiation.map((item) => <div className="evidence-item" key={`differentiate:${item.assessment_label}:${item.text}`}><strong>{item.assessment_label} differentiation</strong><p>{item.text}</p></div>)}{!details.risks.length && !details.differentiation.length ? <div className="evidence-item"><strong>No narrative risk or differentiation was supplied.</strong><p>Treat the thesis as incomplete until these are established.</p></div> : null}</div></section>;
}

function NarrativePanel({ slice, fallbackMechanism }: { slice: MediaNarrativeSlice; fallbackMechanism: string }) {
  const synthesis = slice.synthesis;
  return <section className="panel"><div className="eyebrow">{slice.label} / coherent mechanism thesis</div><h2 style={{marginTop:8}}>{synthesis.mechanism_thesis ?? fallbackMechanism}</h2><p className="panel-copy" style={{marginTop:10}}>{synthesis.executive_summary ?? 'This media cohort retains its own evidence and conclusion.'}</p><p className="panel-copy" style={{marginTop:10}}><strong>Repeatability:</strong> {synthesis.repeatability_thesis ?? 'Not established for this media cohort.'}</p><p className="panel-copy" style={{marginTop:10}}><strong>Production:</strong> {synthesis.production_thesis ?? 'Not established for this media cohort.'}</p></section>;
}

function CriticPanel({ slice }: { slice: MediaNarrativeSlice }) {
  const blocking = asTextList(slice.critic.blocking_issues);
  const challenges = asTextList(slice.critic.challenges);
  return <section className="panel"><div className="eyebrow">{slice.label} / independent critic</div><h2 style={{marginTop:8}}>{blocking.length ? `${blocking.length} unresolved blocking issue${blocking.length === 1 ? '' : 's'}` : 'No blocking issue for this cohort'}</h2><div className="evidence-list">{blocking.map((issue) => <div className="evidence-item" key={`block-${issue}`}><strong>BLOCKING</strong><p>{issue}</p></div>)}{challenges.map((challenge) => <div className="evidence-item" key={`challenge-${challenge}`}><strong>Challenge</strong><p>{challenge}</p></div>)}</div></section>;
}

function CandidateActionPlan({ slice }: { slice: MediaNarrativeSlice }) {
  const firstTests = asTextList(slice.synthesis.first_test);
  const continueCriteria = asTextList(slice.synthesis.continue_criteria);
  const rejectCriteria = asTextList(slice.synthesis.reject_criteria);
  return <div><div className="eyebrow">{slice.label}</div><div className="evidence-list"><ActionRecord label="First test" values={firstTests}/><ActionRecord label="Continue if" values={continueCriteria}/><ActionRecord label="Reject if" values={rejectCriteria}/></div></div>;
}

function ActionRecord({ label, values }: { label: string; values: string[] }) {
  return <div className="evidence-item"><strong>{label}</strong>{values.length ? <ul>{values.map((value) => <li key={value}>{value}</li>)}</ul> : <p>No candidate-specific criterion was supplied.</p>}</div>;
}

function asTextList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string' && item.length > 0) : [];
}

function formatCount(value: unknown): string {
  const number = Number(value);
  return Number.isFinite(number) ? Math.round(number).toLocaleString() : 'unknown';
}

function formatMultiple(value: unknown): string {
  const number = Number(value);
  return Number.isFinite(number) ? `${number.toFixed(1)}×` : 'unknown';
}
