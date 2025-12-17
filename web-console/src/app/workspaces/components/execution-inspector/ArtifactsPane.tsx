'use client';

import React from 'react';
import { ArtifactsList } from '@/components/execution';
import type { Artifact } from './types/execution';

export interface ArtifactsPaneProps {
  artifacts: Artifact[];
  latestArtifact?: Artifact;
  sandboxId?: string;
  apiUrl: string;
  workspaceId: string;
  onView: (artifact: Artifact) => void;
  onViewSandbox?: () => void;
}

export default function ArtifactsPane({
  artifacts,
  latestArtifact,
  sandboxId,
  apiUrl,
  workspaceId,
  onView,
  onViewSandbox,
}: ArtifactsPaneProps) {
  // Don't render if there are no artifacts to save space
  if (artifacts.length === 0 && !sandboxId) {
    return null;
  }

  return (
    <div className="p-4 border-b dark:border-gray-700 overflow-y-auto flex-shrink-0 max-h-96">
      <ArtifactsList
        artifacts={artifacts}
        latestArtifact={latestArtifact}
        onView={onView}
        onViewSandbox={sandboxId ? onViewSandbox : undefined}
        sandboxId={sandboxId}
      />
    </div>
  );
}
