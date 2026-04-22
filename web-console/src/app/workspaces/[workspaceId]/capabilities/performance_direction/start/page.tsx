import PerformanceDirectionStoryboardEditorPage from '@/app/capabilities/performance_direction/components/PerformanceDirectionStoryboardEditorPage';

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
    <div
      className="h-full overflow-y-auto overflow-x-hidden bg-white dark:bg-gray-950"
      data-testid="capability-mainpage-scroll-shell"
    >
      <PerformanceDirectionStoryboardEditorPage
        workspaceId={workspaceId}
        routeMode="launcher"
        sessionRouteBasePath={buildPerformanceDirectionSessionBasePath(workspaceId)}
      />
    </div>
  );
}
