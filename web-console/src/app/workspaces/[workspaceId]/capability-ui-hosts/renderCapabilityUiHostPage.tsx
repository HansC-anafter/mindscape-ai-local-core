import CapabilityUiHostClientLoader from './CapabilityUiHostClientLoader';
import WorkspaceSurfaceShell from './WorkspaceSurfaceShell';

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
    <WorkspaceSurfaceShell
      workspaceId={workspaceId}
      activeCapabilityCode={capabilityCode}
      surfacePath={surfacePath}
    >
      <CapabilityUiHostClientLoader
        workspaceId={workspaceId}
        capabilityCode={capabilityCode}
        surfacePath={surfacePath}
      />
    </WorkspaceSurfaceShell>
  );
}
