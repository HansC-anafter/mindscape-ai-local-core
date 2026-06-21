import React from 'react';

import { GovernedMemoryPreview } from '@/components/workspace/governance/GovernedMemoryPreview';
import { parseServerTimestamp } from '@/lib/time';

import type { Artifact, RelatedGovernedMemoryLink } from '../types/execution';
import type { Translator } from './stepDetailPanelTypes';

export function ArtifactsSection({
  apiUrl,
  artifacts,
  relatedGovernedMemory,
  workspaceId,
  t,
  onViewArtifact,
}: {
  apiUrl?: string;
  artifacts: Artifact[];
  relatedGovernedMemory?: RelatedGovernedMemoryLink | null;
  workspaceId?: string;
  t: Translator;
  onViewArtifact?: (artifact: Artifact) => void;
}) {
  return (
    <div className="mt-4">
      <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
        {t('artifacts' as any) || 'Artifacts'}
      </h4>
      {workspaceId && apiUrl && relatedGovernedMemory?.memoryItemId && (
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
      {artifacts.length === 0 ? (
        <div className="p-4 rounded border border-dashed border-default dark:border-gray-700 bg-surface-accent dark:bg-gray-800 text-center text-xs text-secondary dark:text-gray-400">
          <div>{t('noArtifacts' as any) || 'This step has not produced artifacts yet'}</div>
        </div>
      ) : (
        <div className="space-y-2">
          {artifacts.map((artifact) => (
            <button
              key={artifact.id}
              onClick={() => onViewArtifact?.(artifact)}
              className="w-full text-left p-3 rounded border border-default dark:border-gray-700 bg-surface-accent dark:bg-gray-800 hover:bg-tertiary dark:hover:bg-gray-700 transition-colors"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                  {artifact.name || artifact.id}
                </span>
                <span className="text-[10px] px-2 py-0.5 rounded bg-accent-10 dark:bg-blue-900/30 text-accent dark:text-blue-300">
                  {artifact.type || 'file'}
                </span>
              </div>
              {artifact.createdAt && (
                <div className="text-[11px] text-gray-500 dark:text-gray-400 mt-1">
                  {parseServerTimestamp(artifact.createdAt)?.toLocaleTimeString() ?? 'N/A'}
                </div>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
