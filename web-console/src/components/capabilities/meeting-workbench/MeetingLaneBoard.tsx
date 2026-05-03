import { useMemo } from 'react';

import { GRAPH_LANES } from './meetingWorkbenchConstants';
import { buildCommandDisplay, MeetingGraphNodeCard } from './MeetingGraphNodeCard';
import type {
  MeetingCommandImpact,
  MeetingGraphLaneConfig,
  MeetingLane,
  MeetingNode,
} from './meetingWorkbenchTypes';

export function MeetingLaneBoard({
  nodes,
  laneConfigs,
  selectedNodeId,
  commandImpact,
  onSelectNode,
}: {
  nodes: MeetingNode[];
  laneConfigs: MeetingGraphLaneConfig[];
  selectedNodeId: string;
  commandImpact: MeetingCommandImpact | null;
  onSelectNode: (nodeId: string) => void;
}) {
  const nodesByLane = useMemo(() => {
    const grouped = new Map<MeetingLane, MeetingNode[]>();
    GRAPH_LANES.forEach((lane) => grouped.set(lane.id, []));
    nodes.forEach((node) => {
      const laneNodes = grouped.get(node.lane) ?? [];
      laneNodes.push(node);
      grouped.set(node.lane, laneNodes);
    });
    return grouped;
  }, [nodes]);
  const commandDisplay = useMemo(() => buildCommandDisplay(nodes), [nodes]);

  return (
    <div className="grid grid-cols-[repeat(7,minmax(11rem,15rem))] items-start gap-3" data-testid="meeting-graph-lanes">
      {laneConfigs.map((lane) => {
        const laneNodes = nodesByLane.get(lane.id) ?? [];
        return (
          <section
            key={lane.id}
            className="min-h-[15rem] rounded-lg border border-slate-200 bg-white/80 p-2 shadow-sm dark:border-slate-800 dark:bg-slate-950/80"
            data-testid={`meeting-graph-lane-${lane.id}`}
            aria-label={`${lane.label} lane`}
          >
            <div className="mb-2 flex items-center justify-between gap-2 border-b border-slate-200 pb-2 dark:border-slate-800">
              <div className="min-w-0">
                <div className="truncate text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
                  {lane.label}
                </div>
                <div className="truncate text-[11px] text-slate-400 dark:text-slate-500">{lane.description}</div>
              </div>
              <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold tabular-nums text-slate-500 dark:bg-slate-900 dark:text-slate-400">
                {laneNodes.length}
              </span>
            </div>
            <div className="max-h-72 space-y-2 overflow-auto pr-1" data-meeting-lane-scroll="true">
              {laneNodes.length > 0 ? (
                laneNodes.map((node) => (
                  <MeetingGraphNodeCard
                    key={node.id}
                    node={node}
                    selectedNodeId={selectedNodeId}
                    commandImpact={commandImpact}
                    commandMeta={commandDisplay.get(node.id)}
                    onSelectNode={onSelectNode}
                  />
                ))
              ) : (
                <div className="rounded-md border border-dashed border-slate-200 px-2 py-3 text-xs text-slate-400 dark:border-slate-800 dark:text-slate-500">
                  No nodes
                </div>
              )}
            </div>
          </section>
        );
      })}
    </div>
  );
}
