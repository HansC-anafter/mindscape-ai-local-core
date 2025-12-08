'use client';

import React, { useState, useEffect } from 'react';
import { VersionMetadata, getVersionMetadata } from '@/lib/sandbox-api';

interface SandboxVersionTimelineProps {
  versions: string[];
  currentVersion: string | null;
  onVersionSelect: (version: string) => void;
  workspaceId: string;
  sandboxId: string;
}

export default function SandboxVersionTimeline({
  versions,
  currentVersion,
  onVersionSelect,
  workspaceId,
  sandboxId,
}: SandboxVersionTimelineProps) {
  const [versionMetadata, setVersionMetadata] = useState<Record<string, VersionMetadata>>({});

  useEffect(() => {
    const loadMetadata = async () => {
      const metadata: Record<string, VersionMetadata> = {};
      for (const version of versions) {
        try {
          const data = await getVersionMetadata(workspaceId, sandboxId, version);
          metadata[version] = data;
        } catch (err) {
          console.error(`Failed to load metadata for ${version}:`, err);
        }
      }
      setVersionMetadata(metadata);
    };

    if (versions.length > 0) {
      loadMetadata();
    }
  }, [versions, workspaceId, sandboxId]);

  return (
    <div className="sandbox-version-timeline">
      <h3 className="text-lg font-semibold mb-4">Version History</h3>
      {versions.length === 0 ? (
        <div className="text-sm text-gray-500">No versions yet</div>
      ) : (
        <div className="space-y-2">
          {versions.map((version) => {
            const metadata = versionMetadata[version];
            const isCurrent = currentVersion === version;

            return (
              <div
                key={version}
                onClick={() => onVersionSelect(version)}
                className={`p-3 border rounded cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 ${
                  isCurrent ? 'border-blue-500 bg-blue-50 dark:bg-blue-900' : 'border-gray-200 dark:border-gray-700'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="font-medium">{version}</div>
                  {isCurrent && (
                    <span className="text-xs text-blue-600">Current</span>
                  )}
                </div>
                {metadata && (
                  <div className="text-xs text-gray-500 mt-1">
                    {metadata.file_count} files • {metadata.total_size} bytes
                    {metadata.created_at && (
                      <span> • {new Date(metadata.created_at).toLocaleString()}</span>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

