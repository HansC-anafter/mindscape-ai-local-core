'use client';

import React from 'react';

import type {
  MotionPracticeLaunchResult,
  MotionPracticeTarget,
} from '../motionPracticeLauncher';

export type MotionPracticeLaunchState = 'idle' | 'starting' | 'submitted' | 'error';

interface MotionPracticeSessionStatusPanelProps {
  target: MotionPracticeTarget;
  launchState: MotionPracticeLaunchState;
  error: string | null;
  result: MotionPracticeLaunchResult | null;
}

export function MotionPracticeSessionStatusPanel({
  target,
  launchState,
  error,
  result,
}: MotionPracticeSessionStatusPanelProps) {
  return (
    <div className="space-y-2">
      <div
        className={`rounded border p-2 text-xs ${
          target.enabled
            ? 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-200'
            : 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200'
        }`}
        data-testid="motion-practice-readiness"
      >
        {target.readinessLabel}
      </div>

      {error ? (
        <div className="rounded border border-red-200 bg-red-50 p-2 text-xs text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-200">
          {error}
        </div>
      ) : null}

      {result ? (
        <div className="space-y-1 rounded border border-emerald-200 bg-emerald-50 p-2 text-xs text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-200">
          <div>Submitted: {result.status}</div>
          <div className="break-all font-mono">meeting {result.meetingId}</div>
          <div className="break-all font-mono">command {result.commandId}</div>
          {result.liveSessionId ? (
            <div className="break-all font-mono">motion {result.liveSessionId}</div>
          ) : null}
        </div>
      ) : null}

      {launchState === 'idle' && !result ? (
        <div className="rounded border border-gray-200 px-2 py-1 text-[11px] text-gray-500 dark:border-gray-800 dark:text-gray-400">
          No practice command submitted.
        </div>
      ) : null}
    </div>
  );
}

export default MotionPracticeSessionStatusPanel;
