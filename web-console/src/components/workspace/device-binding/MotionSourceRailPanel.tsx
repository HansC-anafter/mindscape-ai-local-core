'use client';

import React from 'react';
import { Settings, ShieldCheck } from 'lucide-react';

import { CaptureSourceRail } from './capture-bridge/CaptureSourceRail';

interface MotionSourceRailPanelProps {
  apiUrl: string;
  workspaceId: string;
  disabled?: boolean;
}

export function MotionSourceRailPanel({
  apiUrl,
  workspaceId,
  disabled = false,
}: MotionSourceRailPanelProps) {
  const settingsHref = `/settings?tab=runtime&section=device-link-readiness&workspace_id=${encodeURIComponent(workspaceId)}`;

  return (
    <div className="flex min-h-full flex-col">
      <div className="border-b border-gray-200 bg-gray-50 p-3 text-xs text-gray-600 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-300">
        <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-gray-100">
          <ShieldCheck className="h-4 w-4 text-sky-500" aria-hidden="true" />
          Local-core device link
        </div>
        <p className="leading-5">
          Pair phone, iPad, desktop, or OBS camera sources here. Start Yoga or Dance practice from the pack workbench after a source is active.
        </p>
        <a
          href={settingsHref}
          className="mt-2 inline-flex items-center gap-1 rounded-md border border-gray-300 px-2 py-1 font-medium text-gray-700 hover:bg-white dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-900"
          aria-label="Open Device Link settings"
        >
          <Settings className="h-3.5 w-3.5" aria-hidden="true" />
          Device Link settings
        </a>
      </div>
      <CaptureSourceRail
        apiUrl={apiUrl}
        workspaceId={workspaceId}
        disabled={disabled}
      />
    </div>
  );
}

export default MotionSourceRailPanel;
