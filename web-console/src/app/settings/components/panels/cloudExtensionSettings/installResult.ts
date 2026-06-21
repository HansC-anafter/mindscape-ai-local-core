import type { InstallDefaultPackJob, InstallDefaultPacksResult } from './types';

function getPackCode(job: InstallDefaultPackJob): string | null {
  if (job.pack_code) {
    return job.pack_code;
  }
  if (job.code) {
    return job.code;
  }
  return job.pack_ref?.split(':')[1]?.split('@')[0] || null;
}

export function buildInstallDefaultPacksAcceptedMessage(result: InstallDefaultPacksResult): string {
  const jobs = result.jobs || [];
  const jobCount = jobs.length;
  const packCodes = Array.from(new Set(jobs.map(getPackCode).filter(Boolean)));

  if (jobCount > 0) {
    const packList = packCodes.length > 0 ? `: ${packCodes.join(', ')}` : '';
    return `Queued ${jobCount} pack install job${jobCount > 1 ? 's' : ''}${packList}. Check install job status for completion.`;
  }

  if (result.accepted) {
    return 'Install request accepted. Check install job status for completion.';
  }

  return 'Install request submitted. Check install job status for completion.';
}
