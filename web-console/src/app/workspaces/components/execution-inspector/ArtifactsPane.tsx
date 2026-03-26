'use client';

import React from 'react';
import { ArtifactsList } from '@/components/execution';
import { GovernedMemoryPreview } from '@/components/workspace/governance/GovernedMemoryPreview';
import type { Artifact, RelatedGovernedMemoryLink } from './types/execution';

export interface ArtifactsPaneProps {
  artifacts: Artifact[];
  latestArtifact?: Artifact;
  sandboxId?: string;
  apiUrl: string;
  workspaceId: string;
  relatedGovernedMemory?: RelatedGovernedMemoryLink | null;
  relatedGovernedMemoryLoading?: boolean;
  onView: (artifact: Artifact) => void;
  onViewSandbox?: () => void;
}

export default function ArtifactsPane({
  artifacts,
  latestArtifact,
  sandboxId,
  apiUrl,
  workspaceId,
  relatedGovernedMemory,
  relatedGovernedMemoryLoading,
  onView,
  onViewSandbox,
}: ArtifactsPaneProps) {
  console.log('[ArtifactsPane] Rendered with props:', {
    artifactsCount: artifacts.length,
    hasOnView: !!onView,
    onViewType: typeof onView,
    onViewFunction: onView?.toString().substring(0, 100),
    sandboxId,
    hasOnViewSandbox: !!onViewSandbox,
  });

  // Don't render if there are no artifacts to save space
  if (artifacts.length === 0 && !sandboxId) {
    return null;
  }

  return (
    <div className="p-4 border-b dark:border-gray-700 overflow-y-auto flex-shrink-0 max-h-96">
      {relatedGovernedMemoryLoading && !relatedGovernedMemory ? (
        <div className="mb-3 rounded border border-default dark:border-gray-700 bg-surface-secondary dark:bg-gray-800 px-3 py-2 text-sm text-secondary dark:text-gray-300">
          Loading governed memory detail...
        </div>
      ) : null}

      {relatedGovernedMemory?.memoryItemId && (
        <GovernedMemoryPreview
          workspaceId={workspaceId}
          memoryItemId={relatedGovernedMemory.memoryItemId}
          apiUrl={apiUrl}
          lifecycleStatus={relatedGovernedMemory.lifecycleStatus}
          verificationStatus={relatedGovernedMemory.verificationStatus}
          compact
          className="mb-3"
        />
      )}

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
