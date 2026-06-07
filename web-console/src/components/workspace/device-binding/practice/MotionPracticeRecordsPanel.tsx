'use client';

import React from 'react';

import type { MotionPracticeLaunchResult } from '../motionPracticeLauncher';

interface MotionPracticeRecordsPanelProps {
  workspaceId: string;
  commandPreview: string;
  result: MotionPracticeLaunchResult | null;
  onCopyCommand: () => void;
}

export function MotionPracticeRecordsPanel({
  workspaceId,
  commandPreview,
  result,
  onCopyCommand,
}: MotionPracticeRecordsPanelProps) {
  const recordsHref = `/workspaces/${encodeURIComponent(workspaceId)}/meetings${
    result ? `?session_id=${encodeURIComponent(result.meetingId)}` : ''
  }`;
  return (
    <div className="grid grid-cols-2 gap-2">
      <button
        type="button"
        onClick={onCopyCommand}
        disabled={!commandPreview}
        className="rounded-md border border-gray-300 px-2 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:text-gray-400 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-900"
      >
        Copy command
      </button>
      <a
        href={recordsHref}
        className="rounded-md border border-gray-300 px-2 py-1.5 text-center text-xs font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-900"
      >
        Records
      </a>
    </div>
  );
}

export default MotionPracticeRecordsPanel;
