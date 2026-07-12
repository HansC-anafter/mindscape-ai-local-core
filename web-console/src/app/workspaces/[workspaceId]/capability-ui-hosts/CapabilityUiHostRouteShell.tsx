'use client';

import dynamic from 'next/dynamic';
import React from 'react';

interface CapabilityUiHostRouteShellProps {
  workspaceId: string;
  capabilityCode: string;
  surfacePath?: readonly string[];
  remoteSurfaceMode?: boolean;
}

function CapabilityUiHostRouteShellLoadingState() {
  return (
    <div className="flex h-full w-full min-w-0 items-center justify-center">
      <div className="text-sm text-gray-500 dark:text-gray-400">Loading capability UI...</div>
    </div>
  );
}

const CapabilityUiHostRouteClient = dynamic(() => import('./CapabilityUiHostRouteClient'), {
  ssr: false,
  loading: CapabilityUiHostRouteShellLoadingState,
});

export default function CapabilityUiHostRouteShell({
  workspaceId,
  capabilityCode,
  surfacePath = [],
  remoteSurfaceMode = false,
}: CapabilityUiHostRouteShellProps) {
  return (
    <CapabilityUiHostRouteClient
      workspaceId={workspaceId}
      capabilityCode={capabilityCode}
      surfacePath={surfacePath}
      remoteSurfaceMode={remoteSurfaceMode}
    />
  );
}
