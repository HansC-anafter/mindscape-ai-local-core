'use client';

import CapabilityUiHostClientLoader from './CapabilityUiHostClientLoader';

interface CapabilityUiHostRouteClientProps {
  workspaceId: string;
  capabilityCode: string;
  surfacePath?: readonly string[];
}

export default function CapabilityUiHostRouteClient({
  workspaceId,
  capabilityCode,
  surfacePath = [],
}: CapabilityUiHostRouteClientProps) {
  return (
    <CapabilityUiHostClientLoader
      workspaceId={workspaceId}
      capabilityCode={capabilityCode}
      surfacePath={surfacePath}
    />
  );
}
