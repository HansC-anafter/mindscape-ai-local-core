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
    <CapabilityUiHostRouteShell
      workspaceId={workspaceId}
      capabilityCode={capabilityCode}
      surfacePath={surfacePath}
    />
  );
}
