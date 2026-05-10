import { redirect } from 'next/navigation';

import { buildPerformanceDirectionSessionPath } from '../../routePaths';

type PerformanceDirectionSessionPageProps = {
  params: {
    workspaceId: string;
    sessionId: string;
  };
};

export default function PerformanceDirectionSessionPage({
  params,
}: PerformanceDirectionSessionPageProps) {
  const workspaceId = String(params.workspaceId || '').trim();
  const sessionId = String(params.sessionId || '').trim();

  redirect(buildPerformanceDirectionSessionPath(workspaceId, sessionId));
}
