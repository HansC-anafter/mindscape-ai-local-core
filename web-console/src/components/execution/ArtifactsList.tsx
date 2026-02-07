'use client';

import React from 'react';
import { useT } from '@/lib/i18n';

export interface Artifact {
  id: string;
  name: string;
  type: string;  // 'docx', 'xlsx', 'pptx', etc.
  createdAt?: string;
  url?: string;
}

interface ArtifactsListProps {
  artifacts: Artifact[];
  latestArtifact?: Artifact;
  onView?: (artifact: Artifact) => void;
  onDownload?: (artifact: Artifact) => void;
  onViewSandbox?: (sandboxId: string) => void;
  sandboxId?: string;
}

const typeIcons: Record<string, string> = {
  docx: '📝',
  doc: '📝',
  xlsx: '📊',
  xls: '📊',
  pptx: '📊',
  ppt: '📊',
  pdf: '📄',
  md: '📋',
  txt: '📋',
  json: '🔧',
  default: '📁',
};

function getTypeIcon(type: string): string {
  return typeIcons[type.toLowerCase()] || typeIcons.default;
}

export default function ArtifactsList({
  artifacts,
  latestArtifact,
  onView,
  onDownload,
  onViewSandbox,
  sandboxId,
}: ArtifactsListProps) {
  const t = useT();

  // Debug logging
  console.log('[ArtifactsList] Rendered with props:', {
    artifactsCount: artifacts.length,
    hasOnView: !!onView,
    hasOnDownload: !!onDownload,
    hasOnViewSandbox: !!onViewSandbox,
    sandboxId,
    onViewType: typeof onView,
    onViewFunction: onView?.toString().substring(0, 100),
  });

  if (artifacts.length === 0) {
    // Don't render anything when there are no artifacts to save space
    return null;
  }

  return (
    <div className="artifacts-list mb-3">
      {/* Latest Artifact Highlight - Always visible when available */}
      {latestArtifact && (
        <div
          className="mb-3 p-3 bg-yellow-50 dark:bg-yellow-900/30 border-l-4 border-yellow-500 dark:border-yellow-400 rounded-r cursor-pointer hover:bg-yellow-100 dark:hover:bg-yellow-900/40 transition-colors shadow-sm"
          onClick={() => onView?.(latestArtifact)}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 flex-1 min-w-0">
              <span className="text-sm font-semibold text-yellow-700 dark:text-yellow-300 flex-shrink-0">
                🆕 {t('latestArtifact' as any) || 'Latest'} →
              </span>
              <span className="text-sm text-gray-800 dark:text-gray-200 truncate font-medium">
                {latestArtifact.name}
              </span>
            </div>
            <span className="text-xs text-yellow-600 dark:text-yellow-400 flex-shrink-0 ml-2">
              {t('clickToView' as any) || 'Click to view'}
            </span>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between mb-2">
        <h4 className="text-xs font-semibold text-gray-600 dark:text-gray-400 flex items-center gap-1">
          <span>📦 {t('stepArtifacts' as any) || 'Step Artifacts'}</span>
          <span className="text-[10px] text-gray-400 ml-1">({artifacts.length})</span>
        </h4>
        {onViewSandbox && sandboxId && (
          <button
            onClick={() => onViewSandbox(sandboxId)}
            className="text-[10px] text-accent dark:text-blue-400 hover:underline"
          >
            {t('viewInSandbox' as any) || 'View in Sandbox'} →
          </button>
        )}
      </div>

      <div className="space-y-1">
        {artifacts.map((artifact) => (
          <div
            key={artifact.id}
            className="flex items-center justify-between py-1.5 border-b border-gray-100 dark:border-gray-800 last:border-0"
          >
            <div className="flex items-center gap-2 flex-1 min-w-0">
              <span className="text-sm flex-shrink-0">{getTypeIcon(artifact.type)}</span>
              <span className="text-xs text-gray-700 dark:text-gray-300 truncate">
                {artifact.name}
              </span>
            </div>
            <div className="flex items-center gap-1 flex-shrink-0">
              {(() => {
                console.log('[ArtifactsList] Rendering buttons for artifact:', {
                  artifactId: artifact.id,
                  artifactName: artifact.name,
                  hasOnView: !!onView,
                  onViewValue: onView,
                });
                return null;
              })()}
              {onView ? (
                <button
                  onClick={() => {
                    console.log('[ArtifactsList] View button clicked for artifact:', artifact);
                    onView(artifact);
                  }}
                  className="text-[10px] text-purple-600 dark:text-purple-400 hover:underline px-1"
                >
                  {t('view' as any) || 'View'}
                </button>
              ) : (
                <span className="text-[10px] text-red-500">NO ONVIEW</span>
              )}
              {onDownload && (
                <button
                  onClick={() => onDownload(artifact)}
                  className="text-[10px] text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300 px-1"
                >
                  {t('download' as any)}
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      {sandboxId && onViewSandbox && (
        <div className="mt-3 pt-3 border-t border-default dark:border-gray-800">
          <button
            onClick={() => onViewSandbox(sandboxId)}
            className="w-full px-3 py-2 text-sm bg-accent dark:bg-blue-600 text-white rounded hover:bg-accent/90 dark:hover:bg-blue-700 flex items-center justify-center gap-2"
          >
            <span>{t('viewSandbox' as any)}</span>
          </button>
        </div>
      )}
    </div>
  );
}

