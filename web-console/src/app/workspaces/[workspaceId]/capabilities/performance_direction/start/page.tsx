import PerformanceDirectionWorkbenchHost from '../PerformanceDirectionWorkbenchHost';
import { buildPerformanceDirectionSessionBasePath } from '../routePaths';

type PerformanceDirectionStartPageProps = {
  params: {
    workspaceId: string;
  };
};

export default function PerformanceDirectionStartPage({
  params,
}: PerformanceDirectionStartPageProps) {
  const workspaceId = String(params.workspaceId || '').trim();

  return (
    <PerformanceDirectionWorkbenchHost
      workspaceId={workspaceId}
      routeMode="launcher"
      sessionRouteBasePath={buildPerformanceDirectionSessionBasePath(workspaceId)}
    />
  );
}
