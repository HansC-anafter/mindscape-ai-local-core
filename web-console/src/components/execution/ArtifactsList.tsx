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
  onView,
  onDownload,
  onViewSandbox,
  sandboxId,
}: ArtifactsListProps) {
  const t = useT();

  if (artifacts.length === 0) {
    return (
      <div className="artifacts-list mb-3">
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-xs font-semibold text-gray-600 dark:text-gray-400 flex items-center gap-1">
            <span>{t('artifactsProduced')}</span>
          </h4>
        </div>
        <div className="text-xs text-gray-400 dark:text-gray-500 italic">
          {t('noArtifactsYet')}
        </div>
      </div>
    );
  }

  return (
    <div className="artifacts-list mb-3">
      <div className="flex items-center justify-between mb-2">
        <h4 className="text-xs font-semibold text-gray-600 dark:text-gray-400 flex items-center gap-1">
          <span>{t('artifactsProduced')}</span>
          <span className="text-[10px] text-gray-400 ml-1">({artifacts.length})</span>
        </h4>
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
              {onView && (
                <button
                  onClick={() => onView(artifact)}
                  className="text-[10px] text-purple-600 dark:text-purple-400 hover:underline px-1"
                >
                  {t('view')}
                </button>
              )}
              {onDownload && (
                <button
                  onClick={() => onDownload(artifact)}
                  className="text-[10px] text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300 px-1"
                >
                  {t('download')}
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      {sandboxId && onViewSandbox && (
        <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-800">
          <button
            onClick={() => onViewSandbox(sandboxId)}
            className="w-full px-3 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 flex items-center justify-center gap-2"
          >
            <span>{t('viewSandbox')}</span>
          </button>
        </div>
      )}
    </div>
  );
}

