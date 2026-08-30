import { candidateSchema, reportSchema, runSchema, type Report, type Run } from './schemas';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers: { 'content-type': 'application/json', ...(init?.headers ?? {}) }, cache: 'no-store' });
  if (!response.ok) throw new Error(await response.text() || `Request failed (${response.status})`);
  return response.json() as Promise<T>;
}

export async function listRuns(): Promise<Run[]> { return (await request<unknown[]>('/api/research-runs')).map((value) => runSchema.parse(value)); }
export async function getRun(id: string): Promise<Run> { return runSchema.parse(await request(`/api/research-runs/${id}`)); }
export async function createRun(payload: Record<string, unknown>): Promise<Run> { return runSchema.parse(await request('/api/research-runs', { method: 'POST', body: JSON.stringify(payload) })); }
export async function getReport(id: string): Promise<Report> { return reportSchema.parse(await request(`/api/research-runs/${id}/report`)); }
export async function getCandidates(id: string) { return (await request<unknown[]>(`/api/research-runs/${id}/candidates`)).map((value) => candidateSchema.parse(value)); }
export async function getEvidence(id: string) { return request<Array<Record<string, unknown>>>(`/api/research-runs/${id}/evidence`); }
export async function getHealth() { return request<Array<Record<string, unknown>>>('/api/system/source-health'); }
export async function getQuota() { return request<Record<string, unknown>>('/api/system/quota'); }

