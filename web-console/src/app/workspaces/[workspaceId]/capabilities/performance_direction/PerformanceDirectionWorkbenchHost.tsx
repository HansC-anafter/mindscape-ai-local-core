'use client';

import { usePathname } from 'next/navigation';

import PerformanceDirectionStoryboardEditorPage from '@/app/capabilities/performance_direction/components/PerformanceDirectionStoryboardEditorPage';
import {
  AOLRuntimeShell,
  buildCapabilitySurfaceId,
} from '@/components/capabilities/aol-runtime-shell';
import { getApiBaseUrl } from '@/lib/api-url';

type PerformanceDirectionWorkbenchHostProps = {
  workspaceId: string;
  routeMode: 'launcher' | 'workbench';
  routeSessionId?: string;
  sessionRouteBasePath: string;
};

export default function PerformanceDirectionWorkbenchHost({
  workspaceId,
  routeMode,
  routeSessionId,
  sessionRouteBasePath,
}: PerformanceDirectionWorkbenchHostProps) {
  const pathname = usePathname();
  const apiUrl = getApiBaseUrl();

  return (
    <AOLRuntimeShell
      apiUrl={apiUrl}
      workspaceId={workspaceId}
      capabilityCode="performance_direction"
      route={pathname}
      surfaceId={buildCapabilitySurfaceId(
        'performance_direction',
        'PerformanceDirectionStoryboardEditorPage',
      )}
    >
      {(aolHost) => (
        <div
          className="h-full overflow-y-auto overflow-x-hidden bg-white dark:bg-gray-950"
          data-testid="capability-mainpage-scroll-shell"
        >
          <PerformanceDirectionStoryboardEditorPage
            workspaceId={workspaceId}
            apiUrl={apiUrl}
            routeMode={routeMode}
            routeSessionId={routeSessionId}
            sessionRouteBasePath={sessionRouteBasePath}
            aolHost={aolHost}
          />
        </div>
      )}
    </AOLRuntimeShell>
  );
}
