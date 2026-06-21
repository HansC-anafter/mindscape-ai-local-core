import React from 'react';

import type { RemoteChildExecution } from '../types/execution';

export function RemoteExecutionSection({
  remoteChildrenToShow,
}: {
  remoteChildrenToShow: RemoteChildExecution[];
}) {
  if (remoteChildrenToShow.length === 0) {
    return null;
  }

  return (
    <div className="mb-3">
      <h4 className="text-xs font-medium text-gray-900 dark:text-gray-100 mb-1.5">
        Remote Execution
      </h4>
      <div className="space-y-2">
        {remoteChildrenToShow.map((child) => {
          const summary = child.remote_execution_summary;
          if (!summary) return null;
          return (
            <div
              key={child.execution_id}
              className="rounded border border-blue-200 bg-blue-50/60 p-2 text-xs dark:border-blue-800 dark:bg-blue-950/20"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium text-blue-900 dark:text-blue-200">
                  {summary.tool_name || child.playbook_code || child.execution_id}
                </span>
                {summary.target_device_id && (
                  <span className="rounded bg-white/80 px-1.5 py-0.5 text-[10px] text-blue-700 dark:bg-blue-900/40 dark:text-blue-300">
                    VM {summary.target_device_id}
                  </span>
                )}
                {summary.is_replay_attempt && (
                  <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
                    replay
                  </span>
                )}
                {summary.is_superseded_by_replay && (
                  <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-700 dark:bg-gray-800 dark:text-gray-300">
                    superseded
                  </span>
                )}
              </div>
              <div className="mt-1 space-y-0.5 text-gray-700 dark:text-gray-300">
                {summary.workflow_step_id && (
                  <div>step: {summary.workflow_step_id}</div>
                )}
                <div>status: {child.status}</div>
                {summary.callback_delivered_at && (
                  <div>callback delivered: {summary.callback_delivered_at}</div>
                )}
                {summary.callback_error && (
                  <div>callback error: {summary.callback_error}</div>
                )}
                {summary.replay_of_execution_id && (
                  <div>replay of: {summary.replay_of_execution_id}</div>
                )}
                {summary.latest_replay_execution_id && (
                  <div>latest replay: {summary.latest_replay_execution_id}</div>
                )}
                {summary.lineage_root_execution_id && (
                  <div>lineage root: {summary.lineage_root_execution_id}</div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
