'use client';

import React from 'react';
import { Unplug } from 'lucide-react';

import { CaptureSourcePreview } from './CaptureSourcePreview';
import { useCaptureSourceBridge } from './CaptureSourceBridgeProvider';

interface CaptureSourceListProps {
  showPreview?: boolean;
}

export function CaptureSourceList({
  showPreview = true,
}: CaptureSourceListProps = {}) {
  const {
    apiUrl,
    workspaceId,
    sessions,
    revokeSession,
  } = useCaptureSourceBridge();

  if (!sessions.length) {
    return (
      <div
        className="rounded-md border border-dashed border-gray-200 px-2 py-2 text-gray-500 dark:border-gray-800 dark:text-gray-400"
        data-testid="capture-source-empty-state"
      >
        No active motion source connected.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {sessions.map((session) => (
        <div
          key={session.session_id}
          className="rounded-md border border-gray-200 px-2 py-1.5 dark:border-gray-800"
        >
          <div className="flex items-center justify-between gap-2">
            <div className="min-w-0">
              <div className="truncate font-medium text-gray-900 dark:text-gray-100">
                {session.display_name || session.device_id}
              </div>
              <div className="truncate text-gray-500 dark:text-gray-400">
                {session.source_types.join(', ') || session.state}
              </div>
            </div>
            <button
              type="button"
              onClick={() => void revokeSession(session.session_id)}
              className="inline-flex h-7 w-7 items-center justify-center rounded-md text-gray-500 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800"
              aria-label={`Revoke ${session.display_name || session.device_id}`}
              title="Revoke device"
            >
              <Unplug className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
          {showPreview ? (
            <CaptureSourcePreview
              apiUrl={apiUrl}
              workspaceId={workspaceId}
              session={session}
            />
          ) : null}
        </div>
      ))}
    </div>
  );
}

export default CaptureSourceList;
