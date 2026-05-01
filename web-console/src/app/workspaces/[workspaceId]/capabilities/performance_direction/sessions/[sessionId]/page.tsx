import PerformanceDirectionWorkbenchHost from '../../PerformanceDirectionWorkbenchHost';
import { buildPerformanceDirectionSessionBasePath } from '../../routePaths';

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

  return (
    <PerformanceDirectionWorkbenchHost
      workspaceId={workspaceId}
      routeMode="workbench"
      routeSessionId={sessionId}
      sessionRouteBasePath={buildPerformanceDirectionSessionBasePath(workspaceId)}
    />
  );
}
