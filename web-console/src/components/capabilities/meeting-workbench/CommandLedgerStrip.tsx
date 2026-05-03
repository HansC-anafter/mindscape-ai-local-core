import { ListChecks } from 'lucide-react';

import type { GraphViewMode, MeetingNode, MeetingTranslate } from './meetingWorkbenchTypes';

function commandStatusClass(status: MeetingNode['status'], selected: boolean): string {
  if (selected) {
    return 'border-blue-400 bg-blue-50 text-blue-800 dark:border-blue-600 dark:bg-blue-950/50 dark:text-blue-200';
  }
  if (status === 'running') {
    return 'border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-200';
  }
  if (status === 'error' || status === 'blocked') {
    return 'border-rose-300 bg-rose-50 text-rose-800 dark:border-rose-700 dark:bg-rose-950/40 dark:text-rose-200';
  }
  return 'border-slate-200 bg-white text-slate-700 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-200';
}

export function CommandLedgerStrip({
  graphViewMode,
  nodes,
  selectedNodeId,
  onSelectNode,
  t,
}: {
  graphViewMode: GraphViewMode;
  nodes: MeetingNode[];
  selectedNodeId: string;
  onSelectNode: (nodeId: string) => void;
  t: MeetingTranslate;
}) {
  if (graphViewMode !== 'work') {
    return null;
  }

  const commandNodes = nodes.filter((node) => node.kind === 'command').slice(0, 8);

  return (
    <section
      className="flex h-12 shrink-0 items-center gap-2 border-t border-slate-200 bg-white/95 px-3 py-1.5 dark:border-slate-800 dark:bg-slate-950/95"
      data-testid="meeting-command-ledger-strip"
      aria-label={t('meetingWorkbenchCommandLedger')}
    >
      <div className="flex shrink-0 items-center gap-1.5 px-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
        <ListChecks className="h-3.5 w-3.5" aria-hidden="true" />
        {t('meetingWorkbenchCommandLedger')}
      </div>
      <div className="flex min-w-0 flex-1 gap-1.5 overflow-x-auto">
        {commandNodes.length > 0 ? (
          commandNodes.map((node, index) => {
            const selected = node.id === selectedNodeId;
            return (
              <button
                key={node.id}
                type="button"
                onClick={() => onSelectNode(node.id)}
                className={`inline-flex h-8 min-w-[9rem] max-w-[13rem] shrink-0 items-center gap-1.5 rounded-md border px-2 text-left text-xs transition-colors ${commandStatusClass(
                  node.status,
                  selected,
                )}`}
                data-testid={`meeting-command-ledger-entry-${node.id}`}
                aria-pressed={selected}
                title={node.title}
              >
                <span className="shrink-0 font-mono text-[10px] opacity-60">#{index + 1}</span>
                <span className="truncate font-medium">{node.title}</span>
              </button>
            );
          })
        ) : (
          <div className="flex h-8 items-center rounded-md border border-dashed border-slate-200 px-2 text-xs text-slate-400 dark:border-slate-800 dark:text-slate-500">
            {t('meetingWorkbenchAwaitingCommand')}
          </div>
        )}
      </div>
    </section>
  );
}
