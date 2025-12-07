'use client';

import React from 'react';
import { LocalFilesystemManagerContent } from './LocalFilesystemManagerContent';

export interface LocalFilesystemManagerProps {
  onClose: () => void;
  onSuccess: () => void;
  workspaceId?: string;
  apiUrl?: string;
  workspaceTitle?: string;
  workspaceMode?: boolean;
  initialStorageBasePath?: string;
  initialArtifactsDir?: string;
  initialPlaybookStorageConfig?: Record<string, { base_path?: string; artifacts_dir?: string }>;
  embedded?: boolean;
}

export function LocalFilesystemManager({
  onClose,
  onSuccess,
  workspaceId,
  apiUrl,
  workspaceMode = false,
  workspaceTitle,
  initialStorageBasePath,
  initialArtifactsDir,
  initialPlaybookStorageConfig,
  embedded = false,
}: LocalFilesystemManagerProps) {
  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl p-6 max-w-2xl w-full max-h-[90vh] overflow-y-auto relative">
        <LocalFilesystemManagerContent
          onClose={onClose}
          onSuccess={onSuccess}
          workspaceId={workspaceId}
          apiUrl={apiUrl}
          workspaceMode={workspaceMode}
          workspaceTitle={workspaceTitle}
          initialStorageBasePath={initialStorageBasePath}
          initialArtifactsDir={initialArtifactsDir}
          initialPlaybookStorageConfig={initialPlaybookStorageConfig}
          showHeader={true}
        />
      </div>
    </div>
  );
}
