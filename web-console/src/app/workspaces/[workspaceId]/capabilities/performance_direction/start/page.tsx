import PerformanceDirectionLauncherHost from '../PerformanceDirectionLauncherHost';
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
    <PerformanceDirectionLauncherHost
      workspaceId={workspaceId}
      sessionRouteBasePath={buildPerformanceDirectionSessionBasePath(workspaceId)}
    />
  );
}
