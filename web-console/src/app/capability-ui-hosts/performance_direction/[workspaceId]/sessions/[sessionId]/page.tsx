import PerformanceDirectionWorkbenchHost from '@/app/workspaces/[workspaceId]/capabilities/performance_direction/PerformanceDirectionWorkbenchHost';
import { buildPerformanceDirectionSessionBasePath } from '@/app/workspaces/[workspaceId]/capabilities/performance_direction/routePaths';

type PerformanceDirectionHostSessionPageProps = {
  params: {
    workspaceId: string;
    sessionId: string;
  };
};

export default function PerformanceDirectionHostSessionPage({
  params,
}: PerformanceDirectionHostSessionPageProps) {
  const workspaceId = String(params.workspaceId || '').trim();
  const sessionId = String(params.sessionId || '').trim();

  return (
    <PerformanceDirectionWorkbenchHost
      workspaceId={workspaceId}
      routeMode="workbench"
      routeSessionId={sessionId}
      sessionRouteBasePath={buildPerformanceDirectionSessionBasePath(workspaceId)}
    />
  );
}
