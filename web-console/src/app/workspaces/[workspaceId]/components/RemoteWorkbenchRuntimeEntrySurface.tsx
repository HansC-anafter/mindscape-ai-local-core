'use client';

import React from 'react';
import { Bot, Workflow } from 'lucide-react';

import { MeetingRunsWorkspaceSurface } from '@/components/capabilities/meeting-workbench/runs/MeetingRunsWorkspaceSurface';
import { getApiBaseUrl } from '@/lib/api-url';

import {
  buildRemoteWorkbenchGraphAnchor,
  buildRemoteWorkbenchMeetingId,
} from './remoteWorkbenchRuntimeEntryModel';

interface RemoteWorkbenchRuntimeEntrySurfaceProps {
  workspaceId: string;
  targetCapabilityCode: string | null;
  targetCapabilityLabel: string | null;
  apiUrl?: string;
}

export function RemoteWorkbenchRuntimeEntrySurface({
  workspaceId,
  targetCapabilityCode,
  targetCapabilityLabel,
  apiUrl,
}: RemoteWorkbenchRuntimeEntrySurfaceProps) {
  const resolvedApiUrl = apiUrl ?? getApiBaseUrl();
  const meetingId = React.useMemo(
    () => buildRemoteWorkbenchMeetingId({ workspaceId, targetCapabilityCode }),
    [targetCapabilityCode, workspaceId],
  );
  const graphAnchor = React.useMemo(
    () => buildRemoteWorkbenchGraphAnchor({
      workspaceId,
      targetCapabilityCode,
      targetCapabilityLabel,
    }),
    [targetCapabilityCode, targetCapabilityLabel, workspaceId],
  );

  return (
    <section
      className="flex min-h-[34rem] min-w-0 flex-col border-b border-[#d7c7ae] bg-slate-50 lg:border-b-0 lg:border-r dark:border-slate-800 dark:bg-slate-950"
      data-testid="remote-workbench-runtime-entry"
    >
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-slate-200 bg-white px-3 py-2 dark:border-slate-800 dark:bg-slate-950">
        <div className="flex min-w-0 items-center gap-2">
          <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-900/50 dark:bg-blue-950/50 dark:text-blue-200">
            <Bot className="h-4 w-4" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">
              AOL Graph Agent
            </div>
            <div className="truncate text-xs text-slate-500 dark:text-slate-400">
              {targetCapabilityLabel || targetCapabilityCode || 'All eligible packs'}
            </div>
          </div>
        </div>
        <div className="inline-flex shrink-0 items-center gap-1 rounded-md border border-slate-200 px-2 py-1 text-[11px] font-semibold text-slate-600 dark:border-slate-800 dark:text-slate-300">
          <Workflow className="h-3.5 w-3.5" aria-hidden="true" />
          RUNS
        </div>
      </header>
      <div className="min-h-0 flex-1 overflow-hidden" data-testid="remote-workbench-runtime-runs-surface">
        <MeetingRunsWorkspaceSurface
          apiUrl={resolvedApiUrl}
          workspaceId={workspaceId}
          meetingId={meetingId}
          selectedObjectRef={graphAnchor}
          compactLayout
        />
      </div>
    </section>
  );
}

export default RemoteWorkbenchRuntimeEntrySurface;
