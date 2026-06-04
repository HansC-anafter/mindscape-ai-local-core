import CapabilityUiHostRouteClient from './CapabilityUiHostRouteClient';

interface RenderCapabilityUiHostPageOptions {
  workspaceId: string;
  capabilityCode: string;
  surfacePath?: readonly string[];
}

export async function renderCapabilityUiHostPage({
  workspaceId,
  capabilityCode,
  surfacePath = [],
}: RenderCapabilityUiHostPageOptions) {
  return (
    <CapabilityUiHostRouteClient
      workspaceId={workspaceId}
      capabilityCode={capabilityCode}
      surfacePath={surfacePath}
    />
  );
}
