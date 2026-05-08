'use client';

import dynamic from 'next/dynamic';
import { usePathname } from 'next/navigation';

import {
  AOLRuntimeShell,
} from '@/components/capabilities/aol-runtime-shell/AOLRuntimeShell';
import {
  buildCapabilitySurfaceId,
} from '@/components/capabilities/aol-runtime-shell/runtimeShellState';
import { getApiBaseUrl } from '@/lib/api-url';

type PerformanceDirectionWorkbenchHostProps = {
  workspaceId: string;
  routeMode: 'launcher' | 'workbench';
  routeSessionId?: string;
  sessionRouteBasePath: string;
};

const PerformanceDirectionStoryboardEditorPage = dynamic(
  () =>
    import('@/app/capabilities/performance_direction/components/PerformanceDirectionStoryboardEditorPage'),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full items-center justify-center bg-white dark:bg-gray-950">
        <div className="text-sm text-gray-500 dark:text-gray-400">Loading PD workbench...</div>
      </div>
    ),
  },
);

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
          className="h-full overflow-hidden bg-white dark:bg-gray-950"
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
