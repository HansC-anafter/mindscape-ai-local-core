import { GitBranch } from 'lucide-react';

import { meetingNodeMatchesImpact } from './meetingCommandImpact';
import type { MeetingCommandImpact, MeetingNode, MeetingNodeStatus } from './meetingWorkbenchTypes';

export interface MeetingCommandDisplay {
  sequence: number;
  phase: MeetingCommandImpact['phase'];
}

function statusClass(status: MeetingNodeStatus, isSelected: boolean): string {
  if (isSelected) {
    return 'border-blue-500 bg-blue-50 text-blue-950 shadow-sm dark:border-blue-400 dark:bg-blue-950/40 dark:text-blue-100';
  }

  switch (status) {
    case 'context':
      return 'border-emerald-300 bg-emerald-50 text-emerald-950 dark:border-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-100';
    case 'running':
      return 'border-amber-300 bg-amber-50 text-amber-950 dark:border-amber-700 dark:bg-amber-950/30 dark:text-amber-100';
    case 'blocked':
    case 'error':
      return 'border-rose-300 bg-rose-50 text-rose-950 dark:border-rose-700 dark:bg-rose-950/30 dark:text-rose-100';
    case 'pending':
    case 'ready':
    default:
      return 'border-slate-200 bg-white text-slate-900 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100';
  }
}

export function buildCommandDisplay(nodes: MeetingNode[]): Map<string, MeetingCommandDisplay> {
  const display = new Map<string, MeetingCommandDisplay>();
  nodes
    .filter((node) => node.kind === 'command')
    .forEach((node, index) => {
      display.set(node.id, {
        sequence: index + 1,
        phase: index === 0 ? 'initial' : index === 1 ? 'inserted' : 'follow-up',
      });
    });
  return display;
}

export function MeetingGraphNodeCard({
  node,
  selectedNodeId,
  commandImpact,
  commandMeta,
  onSelectNode,
}: {
  node: MeetingNode;
  selectedNodeId: string;
  commandImpact: MeetingCommandImpact | null;
  commandMeta?: MeetingCommandDisplay;
  onSelectNode: (nodeId: string) => void;
}) {
  const isSelected = node.id === selectedNodeId;
  const isImpactRelated = commandImpact ? meetingNodeMatchesImpact(node, commandImpact.nodeIds) : false;
  const isImpactMuted = Boolean(commandImpact) && !isImpactRelated;

  return (
    <button
      type="button"
      onClick={() => onSelectNode(node.id)}
      className={`w-full rounded-md border p-2.5 text-left transition-colors ${statusClass(
        node.status,
        isSelected,
      )} ${isImpactRelated && !isSelected ? 'ring-2 ring-blue-200 dark:ring-blue-800' : ''} ${
        isImpactMuted ? 'opacity-35' : ''
      }`}
      data-testid={`meeting-graph-node-${node.id}`}
      data-meeting-node="true"
      data-impact-state={commandImpact ? (isImpactRelated ? 'related' : 'muted') : 'none'}
      aria-pressed={isSelected}
    >
      <div className="flex items-start gap-2">
        <GitBranch className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <span className="truncate text-[10px] font-semibold uppercase tracking-[0.12em] opacity-70">
          {node.eyebrow}
        </span>
        <div className="ml-auto flex max-w-[8.5rem] flex-wrap justify-end gap-1">
          {commandMeta ? (
            <span className="rounded bg-indigo-50 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-200">
              #{commandMeta.sequence} {commandMeta.phase}
            </span>
          ) : null}
          {node.childCount ? (
            <span className="rounded bg-white/70 px-1.5 py-0.5 text-[10px] font-semibold tabular-nums opacity-80 dark:bg-slate-950/70">
              {node.childCount}
            </span>
          ) : null}
          {isImpactRelated && !isSelected ? (
            <span className="rounded bg-blue-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-blue-700 dark:bg-blue-950/60 dark:text-blue-200">
              Impact
            </span>
          ) : null}
        </div>
      </div>
      <div className="mt-2 truncate text-sm font-semibold">{node.title}</div>
      <div className="mt-1 max-h-10 overflow-hidden text-xs leading-5 opacity-75">{node.detail}</div>
    </button>
  );
}
