import PerformanceDirectionLauncherHost from '@/app/workspaces/[workspaceId]/capabilities/performance_direction/PerformanceDirectionLauncherHost';
import { buildPerformanceDirectionSessionBasePath } from '@/app/workspaces/[workspaceId]/capabilities/performance_direction/routePaths';

type PerformanceDirectionHostStartPageProps = {
  params: {
    workspaceId: string;
  };
};

export default function PerformanceDirectionHostStartPage({
  params,
}: PerformanceDirectionHostStartPageProps) {
  const workspaceId = String(params.workspaceId || '').trim();

  return (
    <PerformanceDirectionLauncherHost
      workspaceId={workspaceId}
      sessionRouteBasePath={buildPerformanceDirectionSessionBasePath(workspaceId)}
    />
  );
}
