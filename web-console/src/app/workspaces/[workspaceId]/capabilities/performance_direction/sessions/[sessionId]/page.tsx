import PerformanceDirectionStoryboardEditorPage from '@/app/capabilities/performance_direction/components/PerformanceDirectionStoryboardEditorPage';

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
    <div
      className="h-full overflow-y-auto overflow-x-hidden bg-white dark:bg-gray-950"
      data-testid="capability-mainpage-scroll-shell"
    >
      <PerformanceDirectionStoryboardEditorPage
        workspaceId={workspaceId}
        routeMode="workbench"
        routeSessionId={sessionId}
        sessionRouteBasePath={buildPerformanceDirectionSessionBasePath(workspaceId)}
      />
    </div>
  );
}
