export function metadataSourceLabel(source: string | undefined, fixture: boolean): string {
  if (fixture || source === 'fixture_api') return 'Synthetic local observations and fixture APIs';
  if (source === 'youtube_api') return 'Browser + YouTube Data API';
  if (source === 'keyless_ytdlp') return 'Browser + keyless yt-dlp metadata';
  return 'Source provenance unavailable';
}
