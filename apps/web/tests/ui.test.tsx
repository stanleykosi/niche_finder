import { describe, expect, it } from 'vitest';
import { candidateSchema, runSchema } from '../lib/schemas';
import { candidateEvidenceDetails, conservativeMetric, gateRecords, gateSummary, mediaAssessmentSlices, mediaNarrativeSlices } from '../lib/mediaAssessments';
import { mostRecentSuccessfulRun } from '../lib/runSelection';
import { metadataSourceLabel } from '../lib/sourceProvenance';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

describe('frontend contracts', () => {
  it('accepts a fixture run and keeps the fixture label', () => {
    const run = runSchema.parse({ id: 'run-1', status: 'complete', requested_format: 'both', language: 'English', seeds: ['paper bridge'], started_at: '2026-08-10T10:00:00Z', completed_at: '2026-08-10T10:05:00Z', failure_reason: null, fixture_mode: true });
    expect(run.fixture_mode).toBe(true);
    expect(run.completed_at).toBe('2026-08-10T10:05:00Z');
  });
  it('keeps evidence ids on candidate cards', () => {
    const candidate = candidateSchema.parse({ id: 'candidate-1', rank: 1, broad_market: 'Education', niche: 'Visual tests', sub_niche: 'Paper bridges', repeatable_format: 'proof', primary_viral_mechanism: 'reveal', confidence: .9, verdict: 'Start now', evidence_ids: ['evidence-1'], shorts_assessment: {}, longform_assessment: {}, idea_ceiling: {}, clip_ceiling: {}, saturation_assessment: {}, demand_assessment: {}, momentum_assessment: {} });
    expect(candidate.evidence_ids).toEqual(['evidence-1']);
  });
  it('polls active runs and stops at every terminal status', () => {
    const source = readFileSync(join(process.cwd(), 'app/runs/[id]/page.tsx'), 'utf8');
    expect(source).toContain("new Set(['complete', 'failed', 'cancelled'])");
    expect(source).toContain('refetchInterval:');
    expect(source).toContain('Status updates appear automatically.');
  });
  it('labels winner-loser ratios with the actual outlier-multiple metric', () => {
    const source = readFileSync(join(process.cwd(), 'app/runs/[id]/page.tsx'), 'utf8');
    expect(source).toContain('× outlier multiple');
    expect(source).toContain('winner_performance_value');
    expect(source).not.toContain('performance_ratio}× views');
  });
  it('advertises only the supported MVP language', () => {
    const source = readFileSync(join(process.cwd(), 'app/research/new/page.tsx'), 'utf8');
    expect(source).toContain('<option>English</option>');
    expect(source).not.toMatch(/<option>(Spanish|French|Portuguese)<\/option>/);
  });
  it('exposes broad discovery, recency, and production constraints as explicit controls', () => {
    const source = readFileSync(join(process.cwd(), 'app/research/new/page.tsx'), 'utf8');
    expect(source).toContain('Broad discovery enabled');
    expect(source).toContain('id="recency"');
    expect(source).toContain('Production constraints');
    expect(source).toContain('production_constraints: constraints');
    expect(source).toContain('broad_discovery: broad');
  });
  it('labels keyless metadata separately from the YouTube Data API', () => {
    expect(metadataSourceLabel('keyless_ytdlp', false)).toBe('Browser + keyless yt-dlp metadata');
    expect(metadataSourceLabel('youtube_api', false)).toBe('Browser + YouTube Data API');
    expect(metadataSourceLabel('fixture_api', true)).toContain('fixture APIs');
  });
  it('normalizes combined-media reports into two render-safe assessment slices', () => {
    const gate = (passed: boolean) => ({ passed, observed: passed ? 3 : 1, comparison: 'at_least', required: 3, unit: 'channels' });
    const candidate = {
      demand_assessment: {
        assessment_format: 'both',
        media_assessments: {
          shorts: { score: .9, recent_outliers: 4, hard_gates: { channels: gate(true), ideas: gate(true), passed: 2, total: 2 } },
          long_form: { score: .6, recent_outliers: 2, hard_gates: { channels: gate(false), ideas: gate(true), passed: 1, total: 2 } },
        },
        hard_gates: { shorts: {}, long_form: {}, all_passed: false },
      },
      idea_ceiling: { assessment_format: 'both', shorts: { validated_count: 14 }, long_form: { validated_count: 10 } },
      clip_ceiling: { assessment_format: 'both', shorts: { validated_count: 12, asset_coverage: .8 }, long_form: { validated_count: 10, asset_coverage: .7 } },
      saturation_assessment: { assessment_format: 'both', shorts: { risk_score: .2 }, long_form: { risk_score: .4 } },
      momentum_assessment: { assessment_format: 'both', shorts: { score: .8 }, long_form: { score: .5 } },
    };
    const slices = mediaAssessmentSlices(candidate);
    expect(slices.map((slice) => slice.label)).toEqual(['Shorts', 'Long-form']);
    expect(gateSummary(slices)).toEqual({ passed: 3, total: 4 });
    expect(gateRecords(candidate.demand_assessment.hard_gates)).toEqual([]);
    expect(conservativeMetric(slices, 'clip', 'asset_coverage')).toBe(.7);
  });
  it('preserves each combined-media thesis, critic result, and candidate action plan', () => {
    const candidate = {
      demand_assessment: { assessment_format: 'both' },
      research_synthesis: {
        assessment_format: 'both',
        shorts: {
          repeatability_thesis: 'Short visual proofs can repeat.',
          first_test: ['Publish three Shorts.'],
          continue_criteria: ['Two exceed baseline.'],
          reject_criteria: ['No proof retains viewers.'],
        },
        long_form: {
          repeatability_thesis: 'Long builds need a deeper arc.',
          first_test: ['Publish one eight-minute build.'],
          continue_criteria: ['Half of viewers reach the reveal.'],
          reject_criteria: ['The reveal loses viewers.'],
        },
      },
      critic_assessment: {
        assessment_format: 'both',
        shorts: { blocking_issues: ['Shorts footage is too narrow.'], challenges: ['Novelty may fade.'] },
        long_form: { blocking_issues: ['No long-form control pair.'], challenges: ['Production is costly.'] },
      },
    };
    const slices = mediaNarrativeSlices(candidate);
    expect(slices.map((slice) => slice.label)).toEqual(['Shorts', 'Long-form']);
    expect(slices[0].synthesis.first_test).toEqual(['Publish three Shorts.']);
    expect(slices[0].critic.blocking_issues).toEqual(['Shorts footage is too narrow.']);
    expect(slices[1].synthesis.first_test).toEqual(['Publish one eight-minute build.']);
    expect(slices[1].critic.blocking_issues).toEqual(['No long-form control pair.']);
  });
  it('normalizes supporting channels, videos, major outliers, risks, and differentiation', () => {
    const candidate = {
      demand_assessment: {
        assessment_format: 'both',
        media_assessments: {
          shorts: {
            channel_performance: { 'channel-a': { channel_id: 'channel-a', uploads_analyzed: 3 } },
            supporting_videos: [{ video_id: 'short-1', title: 'Short proof' }],
            major_outliers: [
              { video_id: 'short-1', title: 'Short proof', outlier_multiple: 6, recency_bucket: 'current' },
              { video_id: 'short-supporting', title: 'Older proof', outlier_multiple: 8, recency_bucket: 'supporting' },
            ],
          },
          long_form: {
            channel_performance: { 'channel-b': { channel_id: 'channel-b', uploads_analyzed: 4 } },
            supporting_videos: [{ video_id: 'long-1', title: 'Long proof' }],
            major_outliers: [],
          },
        },
      },
      research_synthesis: {
        assessment_format: 'both',
        shorts: { risks: ['Novelty may fade.'], differentiation: 'Show the proof first.' },
        long_form: { risks: ['Build cost is high.'], differentiation: 'Explain the failed attempts.' },
      },
      critic_assessment: { assessment_format: 'both', shorts: {}, long_form: {} },
    };
    const details = candidateEvidenceDetails(candidate);
    expect(details.channels.map((item) => item.channel_id)).toEqual(['channel-a', 'channel-b']);
    expect(details.supportingVideos.map((item) => item.video_id)).toEqual(['short-1', 'long-1']);
    expect(details.majorOutliers.map((item) => item.video_id)).toEqual(['short-1']);
    expect(details.risks.map((item) => item.text)).toEqual(['Novelty may fade.', 'Build cost is high.']);
    expect(details.differentiation.map((item) => item.text)).toEqual([
      'Show the proof first.',
      'Explain the failed attempts.',
    ]);
  });
  it('selects the latest completed run independently from the latest run', () => {
    const runs = [
      runSchema.parse({ id: 'queued', status: 'queued', requested_format: 'both', language: 'English', seeds: ['new'], fixture_mode: true }),
      runSchema.parse({ id: 'failed', status: 'failed', requested_format: 'both', language: 'English', seeds: ['failed'], fixture_mode: true }),
      runSchema.parse({ id: 'complete', status: 'complete', requested_format: 'both', language: 'English', seeds: ['last signal'], fixture_mode: true }),
    ];
    expect(mostRecentSuccessfulRun(runs)?.id).toBe('complete');
  });
  it('uses selected-candidate actions and overview links for niche details', () => {
    const detail = readFileSync(join(process.cwd(), 'app/runs/[id]/niches/[candidateId]/page.tsx'), 'utf8');
    const overview = readFileSync(join(process.cwd(), 'app/runs/[id]/page.tsx'), 'utf8');
    expect(detail).toContain('Candidate-specific action plan');
    expect(detail).toContain('slice.synthesis.first_test');
    expect(detail).not.toContain('report.data?.action_plan');
    expect(detail).toContain('href={`/runs/${id}?tab=Evidence`}');
    expect(detail).toContain('Supporting evidence');
    expect(detail).toContain('Major outliers');
    expect(detail).toContain('Risks and differentiation');
    expect(overview).toContain('searchParams: Promise<{ tab?: string | string[] }>');
    expect(overview).toContain("tabs.includes(requestedTab)");
    expect(overview).toContain('candidate={candidate} runId={runId}');
    expect(overview).toContain('href={`/runs/${runId}/niches/${candidate.id}`}');
  });
});
