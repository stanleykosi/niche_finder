import { z } from 'zod';

export const runSchema = z.object({
  id: z.string(), status: z.string(), requested_format: z.string(), language: z.string(), seeds: z.array(z.string()),
  started_at: z.string().nullable().default(null), completed_at: z.string().nullable().default(null),
  failure_reason: z.string().nullable().default(null), fixture_mode: z.boolean().default(false),
  metadata_source: z.enum(['fixture_api', 'youtube_api', 'keyless_ytdlp']).default('keyless_ytdlp')
});
export const candidateSchema = z.object({
  id: z.string(), rank: z.number(), broad_market: z.string(), niche: z.string(), sub_niche: z.string(), repeatable_format: z.string(), primary_viral_mechanism: z.string(), confidence: z.number(), verdict: z.string(), evidence_ids: z.array(z.string()),
  shorts_assessment: z.record(z.any()), longform_assessment: z.record(z.any()), bridge_assessment: z.record(z.any()).default({}), idea_ceiling: z.record(z.any()), clip_ceiling: z.record(z.any()), saturation_assessment: z.record(z.any()), demand_assessment: z.record(z.any()), momentum_assessment: z.record(z.any()),
  research_synthesis: z.record(z.any()).default({}), critic_assessment: z.record(z.any()).default({})
});
export const reportSchema = z.object({ research_run_id: z.string(), generated_at: z.string(), why_now: z.string(), evidence_summary: z.record(z.any()), candidates: z.array(candidateSchema), viral_mechanisms: z.array(z.record(z.any())), winner_loser_comparisons: z.array(z.record(z.any())), research_synthesis: z.record(z.any()).default({}), action_plan: z.record(z.any()), fixture_mode: z.boolean(), metadata_source: z.enum(['fixture_api', 'youtube_api', 'keyless_ytdlp']).default('keyless_ytdlp') });
export type Run = z.infer<typeof runSchema>;
export type Candidate = z.infer<typeof candidateSchema>;
export type Report = z.infer<typeof reportSchema>;
