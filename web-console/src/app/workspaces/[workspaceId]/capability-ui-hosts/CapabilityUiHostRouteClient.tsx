'use client';

import React from 'react';

interface CapabilityUiHostRouteClientProps {
  workspaceId: string;
  capabilityCode: string;
  surfacePath?: readonly string[];
}

function CapabilityUiHostRouteClientLoadingState() {
  return (
    <div className="flex h-full items-center justify-center">
      <div className="text-sm text-gray-500 dark:text-gray-400">Loading capability UI...</div>
    </div>
  );
}

const CapabilityUiHostClientLoader = React.lazy(() => import('./CapabilityUiHostClientLoader'));

export default function CapabilityUiHostRouteClient({
  workspaceId,
  capabilityCode,
  surfacePath = [],
}: CapabilityUiHostRouteClientProps) {
  return (
    <React.Suspense fallback={<CapabilityUiHostRouteClientLoadingState />}>
      <CapabilityUiHostClientLoader
        workspaceId={workspaceId}
        capabilityCode={capabilityCode}
        surfacePath={surfacePath}
      />
    </React.Suspense>
  );
}
