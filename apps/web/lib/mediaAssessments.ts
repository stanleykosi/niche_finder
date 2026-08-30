export type MediaAssessmentSlice = {
  key: 'shorts' | 'long_form' | 'assessment';
  label: string;
  demand: Record<string, any>;
  idea: Record<string, any>;
  clip: Record<string, any>;
  saturation: Record<string, any>;
  momentum: Record<string, any>;
};

export type MediaNarrativeSlice = {
  key: 'shorts' | 'long_form' | 'assessment';
  label: string;
  synthesis: Record<string, any>;
  critic: Record<string, any>;
};

export type CandidateEvidenceDetails = {
  channels: Array<Record<string, any> & { assessment_label: string }>;
  supportingVideos: Array<Record<string, any> & { assessment_label: string }>;
  majorOutliers: Array<Record<string, any> & { assessment_label: string }>;
  risks: Array<{ assessment_label: string; text: string }>;
  differentiation: Array<{ assessment_label: string; text: string }>;
};

const labels = { shorts: 'Shorts', long_form: 'Long-form' } as const;

export function mediaAssessmentSlices(candidate: any): MediaAssessmentSlice[] {
  if (!candidate) return [];
  const demand = candidate.demand_assessment ?? {};
  const combined = demand.assessment_format === 'both' || Boolean(demand.media_assessments);
  if (!combined) {
    const format = String(demand.assessment_format ?? '');
    const key: MediaAssessmentSlice['key'] = format === 'shorts'
      ? 'shorts'
      : format === 'long_form'
        ? 'long_form'
        : 'assessment';
    return [{
      key,
      label: key === 'assessment' ? 'Assessment' : labels[key],
      demand,
      idea: candidate.idea_ceiling ?? {},
      clip: candidate.clip_ceiling ?? {},
      saturation: candidate.saturation_assessment ?? {},
      momentum: candidate.momentum_assessment ?? {},
    }];
  }
  return (['shorts', 'long_form'] as const).map((key) => ({
    key,
    label: labels[key],
    demand: demand.media_assessments?.[key] ?? {},
    idea: candidate.idea_ceiling?.[key] ?? {},
    clip: candidate.clip_ceiling?.[key] ?? {},
    saturation: candidate.saturation_assessment?.[key] ?? {},
    momentum: candidate.momentum_assessment?.[key] ?? {},
  }));
}

export function mediaNarrativeSlices(candidate: any): MediaNarrativeSlice[] {
  if (!candidate) return [];
  const synthesis = candidate.research_synthesis ?? {};
  const critic = candidate.critic_assessment ?? {};
  const combined = synthesis.assessment_format === 'both'
    || critic.assessment_format === 'both'
    || candidate.demand_assessment?.assessment_format === 'both';
  if (combined) {
    return (['shorts', 'long_form'] as const).map((key) => ({
      key,
      label: labels[key],
      synthesis: synthesis[key] ?? {},
      critic: critic[key] ?? {},
    }));
  }
  const format = String(candidate.demand_assessment?.assessment_format ?? '');
  const key: MediaNarrativeSlice['key'] = format === 'shorts'
    ? 'shorts'
    : format === 'long_form'
      ? 'long_form'
      : 'assessment';
  return [{
    key,
    label: key === 'assessment' ? 'Assessment' : labels[key],
    synthesis,
    critic,
  }];
}

export function candidateEvidenceDetails(candidate: any): CandidateEvidenceDetails {
  const assessments = mediaAssessmentSlices(candidate);
  const narratives = mediaNarrativeSlices(candidate);
  const channels = uniqueRecords<Record<string, any> & { assessment_label: string }>(
    assessments.flatMap((slice) => asRecords(Object.values(slice.demand.channel_performance ?? {}))
      .map((record) => ({ ...record, assessment_label: slice.label }))),
    (record) => `${record.assessment_label}:${String(record.channel_id ?? '')}`,
  );
  const supportingVideos = uniqueRecords<Record<string, any> & { assessment_label: string }>(
    assessments.flatMap((slice) => asRecords(slice.demand.supporting_videos)
      .map((record) => ({ ...record, assessment_label: slice.label }))),
    (record) => `${record.assessment_label}:${String(record.video_id ?? '')}`,
  );
  const majorOutliers = uniqueRecords<Record<string, any> & { assessment_label: string }>(
    assessments.flatMap((slice) => asRecords(slice.demand.major_outliers)
      .filter((record) => record.recency_bucket === 'current')
      .map((record) => ({ ...record, assessment_label: slice.label }))),
    (record) => `${record.assessment_label}:${String(record.video_id ?? '')}`,
  );
  const risks = narratives.flatMap((slice) => asStrings(slice.synthesis.risks)
    .map((text) => ({ assessment_label: slice.label, text })));
  const differentiation = narratives.flatMap((slice) => {
    const text = typeof slice.synthesis.differentiation === 'string'
      ? slice.synthesis.differentiation.trim()
      : '';
    return text ? [{ assessment_label: slice.label, text }] : [];
  });
  return { channels, supportingVideos, majorOutliers, risks, differentiation };
}

function asRecords(value: unknown): Record<string, any>[] {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, any> => Boolean(item) && typeof item === 'object')
    : [];
}

function asStrings(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
    : [];
}

function uniqueRecords<T>(records: T[], identity: (record: T) => string): T[] {
  const seen = new Set<string>();
  return records.filter((record) => {
    const key = identity(record);
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function gateRecords(gates: Record<string, any> | undefined): Array<[string, Record<string, any>]> {
  if (!gates) return [];
  return Object.entries(gates).filter((entry): entry is [string, Record<string, any>] => {
    const value = entry[1];
    return Boolean(value) && typeof value === 'object' && typeof value.passed === 'boolean';
  });
}

export function gateSummary(slices: MediaAssessmentSlice[]): { passed: number; total: number } {
  return slices.reduce((summary, slice) => {
    const gates = slice.demand.hard_gates ?? {};
    const records = gateRecords(gates);
    summary.passed += typeof gates.passed === 'number'
      ? gates.passed
      : records.filter(([, value]) => value.passed).length;
    summary.total += typeof gates.total === 'number' ? gates.total : records.length;
    return summary;
  }, { passed: 0, total: 0 });
}

export function conservativeMetric(
  slices: MediaAssessmentSlice[],
  section: 'demand' | 'idea' | 'clip' | 'saturation' | 'momentum',
  key: string,
): number {
  const values = slices
    .map((slice) => Number(slice[section]?.[key]))
    .filter((value) => Number.isFinite(value));
  return values.length ? Math.min(...values) : 0;
}
