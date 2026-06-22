import { CAPABILITY_WORKBENCH_VIEWPORT_CLASS } from '@/components/capabilities/workbench/capabilityWorkbenchFrameClasses';

import CapabilityUiHostRouteShell from './CapabilityUiHostRouteShell';

interface RenderCapabilityUiHostPageOptions {
  workspaceId: string;
  capabilityCode: string;
  surfacePath?: readonly string[];
}

export function renderCapabilityUiHostPage({
  workspaceId,
  capabilityCode,
  surfacePath = [],
}: RenderCapabilityUiHostPageOptions) {
  return (
    <div
      className={`${CAPABILITY_WORKBENCH_VIEWPORT_CLASS} w-full min-w-0`}
      data-testid="capability-ui-host-viewport"
    >
      <div
        className="relative flex min-h-0 w-full min-w-0 flex-1 overflow-hidden"
        data-testid="capability-ui-host-frame"
      >
        <main
          className="flex min-h-0 w-full min-w-0 flex-1 overflow-hidden"
          data-testid="capability-ui-host-main"
        >
          <CapabilityUiHostRouteShell
            workspaceId={workspaceId}
            capabilityCode={capabilityCode}
            surfacePath={surfacePath}
          />
        </main>
      </div>
    </div>
  );
}
