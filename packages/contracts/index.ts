export type RunStatus = 'queued' | 'planning' | 'discovering' | 'enriching' | 'analysing' | 'reporting' | 'complete' | 'failed' | 'cancelled';
export type RequestedFormat = 'shorts' | 'long_form' | 'both';
export type ResearchRun = { id: string; status: RunStatus; requested_format: RequestedFormat; language: string; seeds: string[]; fixture_mode: boolean; metadata_source: 'fixture_api' | 'youtube_api' | 'keyless_ytdlp' };
