import { redirect } from 'next/navigation';

import {
  buildPerformanceDirectionSessionPath,
  buildPerformanceDirectionStartPath,
} from '@/app/workspaces/[workspaceId]/capabilities/performance_direction/routePaths';

type PerformanceDirectionHostEntryPageProps = {
  params: {
    workspaceId: string;
  };
  searchParams?: Record<string, string | string[] | undefined>;
};

function readFirstQueryValue(value: string | string[] | undefined): string {
  if (Array.isArray(value)) {
    return String(value[0] || '').trim();
  }
  return String(value || '').trim();
}

export default function PerformanceDirectionHostEntryPage({
  params,
  searchParams,
}: PerformanceDirectionHostEntryPageProps) {
  const workspaceId = String(params.workspaceId || '').trim();
  const sessionId =
    readFirstQueryValue(searchParams?.sessionId) || readFirstQueryValue(searchParams?.session_id);

  if (sessionId) {
    redirect(buildPerformanceDirectionSessionPath(workspaceId, sessionId));
  }

  redirect(buildPerformanceDirectionStartPath(workspaceId));
}
