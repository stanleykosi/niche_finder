import type { Run } from './schemas';

export function mostRecentSuccessfulRun(runs: Run[] | undefined): Run | undefined {
  return runs?.find((run) => run.status === 'complete');
}
