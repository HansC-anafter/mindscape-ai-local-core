import type { AddressableObjectRef } from '@/lib/addressable-object-layer';

import {
  buildHostRuntimeGraphContext,
  type HostRuntimeGraphContext,
} from './hostRuntimeGraphContext';

export function HostRuntimeObjectContextBar({
  meetingId,
  selectedObjectRef,
  graphContext,
}: {
  meetingId: string | null;
  selectedObjectRef: AddressableObjectRef | null;
  graphContext?: HostRuntimeGraphContext | null;
}) {
  const resolvedGraphContext = graphContext ?? buildHostRuntimeGraphContext({
    workspaceId: selectedObjectRef?.workspace_id || 'unknown_workspace',
    meetingId,
    selectedObjectRef,
  });
  const anchorLabel = resolvedGraphContext.selected_graph_anchor?.anchor_uri || 'No graph anchor';
  const aggregateUnit = resolvedGraphContext.object_graph_aggregate_unit;

  return (
    <div className="space-y-2 text-xs" data-testid="host-runtime-object-context">
      <div className="rounded border border-slate-200 bg-white p-2 dark:border-slate-800 dark:bg-slate-950">
        <div className="font-semibold text-slate-800 dark:text-slate-100">Meeting</div>
        <div className="mt-1 truncate font-mono text-slate-500 dark:text-slate-400">{meetingId || 'No meeting'}</div>
      </div>
      <div className="rounded border border-slate-200 bg-white p-2 dark:border-slate-800 dark:bg-slate-950">
        <div className="font-semibold text-slate-800 dark:text-slate-100">Graph anchor</div>
        <div className="mt-1 truncate font-mono text-slate-500 dark:text-slate-400">{anchorLabel}</div>
      </div>
      <div className="rounded border border-slate-200 bg-white p-2 dark:border-slate-800 dark:bg-slate-950">
        <div className="font-semibold text-slate-800 dark:text-slate-100">Graph selection</div>
        <div className="mt-1 truncate font-mono text-slate-500 dark:text-slate-400">
          {resolvedGraphContext.graph_selection_ref.selection_hash}
        </div>
      </div>
      <div className="rounded border border-slate-200 bg-white p-2 dark:border-slate-800 dark:bg-slate-950">
        <div className="font-semibold text-slate-800 dark:text-slate-100">Aggregate unit</div>
        <div className="mt-1 grid grid-cols-2 gap-1 text-slate-500 dark:text-slate-400">
          <span>nodes {aggregateUnit.node_count}</span>
          <span>edges {aggregateUnit.edge_count}</span>
          <span>budget {aggregateUnit.budget.max_nodes}</span>
          <span>{aggregateUnit.truncation.truncated ? 'truncated' : 'bounded'}</span>
        </div>
        <div className="mt-1 truncate font-mono text-slate-500 dark:text-slate-400">{aggregateUnit.snapshot_hash}</div>
      </div>
      <div className="rounded border border-slate-200 bg-white p-2 dark:border-slate-800 dark:bg-slate-950">
        <div className="font-semibold text-slate-800 dark:text-slate-100">Compatibility object</div>
        <div className="mt-1 truncate font-mono text-slate-500 dark:text-slate-400">{selectedObjectRef?.uri || 'No compatibility ref'}</div>
      </div>
    </div>
  );
}
