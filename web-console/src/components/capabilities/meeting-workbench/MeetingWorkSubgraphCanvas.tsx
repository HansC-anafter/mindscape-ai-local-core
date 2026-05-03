import { ArrowRight } from 'lucide-react';
import { useMemo } from 'react';

import { buildCommandDisplay, MeetingGraphNodeCard } from './MeetingGraphNodeCard';
import type { MeetingCommandImpact, MeetingGraphEdge, MeetingLane, MeetingNode, MeetingTranslate } from './meetingWorkbenchTypes';

const MAX_STEP_NODES = 8;
const MAX_PROVENANCE_EDGES = 6;

const WORK_SUBGRAPH_STEPS: Array<{
  id: string;
  labelKey: Parameters<MeetingTranslate>[0];
  descriptionKey: Parameters<MeetingTranslate>[0];
  lanes: MeetingLane[];
}> = [
  {
    id: 'focus',
    labelKey: 'meetingWorkbenchStepFocus',
    descriptionKey: 'meetingWorkbenchStepFocusDescription',
    lanes: ['context'],
  },
  {
    id: 'guidance',
    labelKey: 'meetingWorkbenchStepGuidance',
    descriptionKey: 'meetingWorkbenchStepGuidanceDescription',
    lanes: ['graph'],
  },
  {
    id: 'command',
    labelKey: 'meetingWorkbenchStepCommand',
    descriptionKey: 'meetingWorkbenchStepCommandDescription',
    lanes: ['commands'],
  },
  {
    id: 'runtime',
    labelKey: 'meetingWorkbenchStepRuntime',
    descriptionKey: 'meetingWorkbenchStepRuntimeDescription',
    lanes: ['runs'],
  },
  {
    id: 'outcome',
    labelKey: 'meetingWorkbenchStepOutcome',
    descriptionKey: 'meetingWorkbenchStepOutcomeDescription',
    lanes: ['outputs', 'artifacts'],
  },
  {
    id: 'next',
    labelKey: 'meetingWorkbenchStepNext',
    descriptionKey: 'meetingWorkbenchStepNextDescription',
    lanes: ['next'],
  },
];

function getVisibleWorkNodes(nodes: MeetingNode[], commandImpact: MeetingCommandImpact | null): MeetingNode[] {
  if (!commandImpact) {
    return nodes;
  }

  return nodes.filter((node) => {
    return commandImpact.nodeIds.has(node.id) || node.lane === 'context' || node.lane === 'next';
  });
}

function getRelevantProvenanceEdges(
  edges: MeetingGraphEdge[],
  visibleNodes: MeetingNode[],
  commandImpact: MeetingCommandImpact | null,
): MeetingGraphEdge[] {
  const visibleNodeIds = new Set(visibleNodes.map((node) => node.id));
  return edges
    .filter((edge) => {
      if (commandImpact) {
        return commandImpact.edgeIds.has(edge.id);
      }
      return visibleNodeIds.has(edge.from_id) && visibleNodeIds.has(edge.to_id);
    });
}

function nodeTitle(nodesById: Map<string, MeetingNode>, nodeId: string): string {
  return nodesById.get(nodeId)?.title || nodeId;
}

export function MeetingWorkSubgraphCanvas({
  nodes,
  edges,
  selectedNodeId,
  commandImpact,
  onSelectNode,
  t,
}: {
  nodes: MeetingNode[];
  edges: MeetingGraphEdge[];
  selectedNodeId: string;
  commandImpact: MeetingCommandImpact | null;
  onSelectNode: (nodeId: string) => void;
  t: MeetingTranslate;
}) {
  const visibleNodes = useMemo(() => getVisibleWorkNodes(nodes, commandImpact), [commandImpact, nodes]);
  const nodesById = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes]);
  const relevantProvenanceEdges = useMemo(
    () => getRelevantProvenanceEdges(edges, visibleNodes, commandImpact),
    [commandImpact, edges, visibleNodes],
  );
  const displayedProvenanceEdges = relevantProvenanceEdges.slice(0, MAX_PROVENANCE_EDGES);
  const overflowProvenanceEdges = relevantProvenanceEdges.slice(MAX_PROVENANCE_EDGES);
  const commandDisplay = useMemo(() => buildCommandDisplay(nodes), [nodes]);
  const selectedNode = nodes.find((node) => node.id === selectedNodeId) ?? nodes[0] ?? null;

  return (
    <div className="min-w-[68rem] space-y-3" data-testid="meeting-work-subgraph">
      <div
        className="flex items-center justify-between gap-3 rounded-md border border-slate-200 bg-white/80 px-3 py-2 shadow-sm dark:border-slate-800 dark:bg-slate-950/80"
        data-testid="meeting-work-subgraph-focus"
      >
        <div className="min-w-0">
          <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
            {t('meetingWorkbenchSelectedSubgraph')}
          </div>
          <div className="mt-1 truncate text-sm font-semibold text-slate-900 dark:text-slate-100">
            {selectedNode ? selectedNode.title : t('meetingWorkbenchNoNodeSelected')}
          </div>
        </div>
        <div className="shrink-0 rounded bg-slate-100 px-2 py-1 text-[11px] font-semibold text-slate-500 dark:bg-slate-900 dark:text-slate-400">
          {commandImpact ? t('meetingWorkbenchCommandImpact') : t('meetingWorkbenchMeetingFlow')}
        </div>
      </div>
      <div
        className="rounded-md border border-slate-200 bg-white/70 px-3 py-2 shadow-sm dark:border-slate-800 dark:bg-slate-950/70"
        data-testid="meeting-work-provenance"
      >
        <div className="mb-2 flex items-center justify-between gap-2">
          <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
            {t('meetingWorkbenchProvenancePath')}
          </div>
          <div className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold tabular-nums text-slate-500 dark:bg-slate-900 dark:text-slate-400">
            {displayedProvenanceEdges.length}/{relevantProvenanceEdges.length}
          </div>
        </div>
        <div className="flex gap-1.5 overflow-x-auto">
          {displayedProvenanceEdges.length > 0 ? (
            <>
              {displayedProvenanceEdges.map((edge) => (
                <div
                  key={edge.id}
                  className="flex max-w-[18rem] shrink-0 items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] text-slate-600 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300"
                  data-testid={`meeting-work-provenance-edge-${edge.id}`}
                  title={`${nodeTitle(nodesById, edge.from_id)} -> ${edge.type} -> ${nodeTitle(nodesById, edge.to_id)}`}
                >
                  <span className="truncate">{nodeTitle(nodesById, edge.from_id)}</span>
                  <ArrowRight className="h-3 w-3 shrink-0 text-slate-300 dark:text-slate-700" aria-hidden="true" />
                  <span className="shrink-0 rounded bg-blue-50 px-1.5 py-0.5 font-semibold text-blue-700 dark:bg-blue-950/50 dark:text-blue-200">
                    {edge.label || edge.type}
                  </span>
                  <ArrowRight className="h-3 w-3 shrink-0 text-slate-300 dark:text-slate-700" aria-hidden="true" />
                  <span className="truncate">{nodeTitle(nodesById, edge.to_id)}</span>
                </div>
              ))}
              {overflowProvenanceEdges.length > 0 ? (
                <details
                  className="group relative shrink-0 rounded-md border border-dashed border-slate-200 bg-white px-2 py-1 text-[11px] text-slate-500 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-400"
                  data-testid="meeting-work-provenance-overflow"
                >
                  <summary className="cursor-pointer list-none font-semibold text-slate-600 outline-none hover:text-slate-900 dark:text-slate-300 dark:hover:text-slate-100">
                    {t('meetingWorkbenchMoreProofEdges', { count: String(overflowProvenanceEdges.length) })}
                  </summary>
                  <div className="absolute left-0 top-8 z-20 max-h-48 w-80 overflow-auto rounded-md border border-slate-200 bg-white p-2 shadow-lg dark:border-slate-800 dark:bg-slate-950">
                    <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-400">
                      {t('meetingWorkbenchHiddenProofEdges')}
                    </div>
                    <div className="space-y-1">
                      {overflowProvenanceEdges.map((edge) => (
                        <div
                          key={edge.id}
                          className="truncate rounded bg-slate-50 px-2 py-1 font-mono text-[10px] text-slate-600 dark:bg-slate-900 dark:text-slate-300"
                          data-testid={`meeting-work-provenance-overflow-edge-${edge.id}`}
                          title={`${nodeTitle(nodesById, edge.from_id)} -> ${edge.type} -> ${nodeTitle(nodesById, edge.to_id)}`}
                        >
                          {nodeTitle(nodesById, edge.from_id)} {'->'} {edge.label || edge.type} {'->'} {nodeTitle(nodesById, edge.to_id)}
                        </div>
                      ))}
                    </div>
                  </div>
                </details>
              ) : null}
            </>
          ) : (
            <div className="rounded-md border border-dashed border-slate-200 px-2 py-1 text-[11px] text-slate-400 dark:border-slate-800 dark:text-slate-500">
              {t('meetingWorkbenchAwaitingRuntimeProof')}
            </div>
          )}
        </div>
      </div>
      <div className="grid grid-cols-[repeat(6,minmax(10rem,14rem))] items-start gap-3">
        {WORK_SUBGRAPH_STEPS.map((step, index) => {
          const stepNodes = visibleNodes.filter((node) => step.lanes.includes(node.lane));
          const displayedNodes = stepNodes.slice(0, MAX_STEP_NODES);
          const hiddenCount = Math.max(0, stepNodes.length - displayedNodes.length);
          return (
            <section
              key={step.id}
              className="min-h-[15rem] rounded-md border border-slate-200 bg-white/80 p-2 shadow-sm dark:border-slate-800 dark:bg-slate-950/80"
              data-testid={`meeting-work-step-${step.id}`}
              aria-label={`${t(step.labelKey)} ${t('meetingWorkbenchWorkStep')}`}
            >
              <div className="mb-2 flex items-start justify-between gap-2 border-b border-slate-200 pb-2 dark:border-slate-800">
                <div className="min-w-0">
                  <div className="truncate text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
                    {t(step.labelKey)}
                  </div>
                  <div className="truncate text-[11px] text-slate-400 dark:text-slate-500">{t(step.descriptionKey)}</div>
                </div>
                {index < WORK_SUBGRAPH_STEPS.length - 1 ? (
                  <ArrowRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-300 dark:text-slate-700" aria-hidden="true" />
                ) : null}
              </div>
              <div className="max-h-80 space-y-2 overflow-auto pr-1" data-meeting-lane-scroll="true">
                {displayedNodes.length > 0 ? (
                  <>
                    {displayedNodes.map((node) => (
                      <MeetingGraphNodeCard
                        key={node.id}
                        node={node}
                        selectedNodeId={selectedNodeId}
                        commandImpact={commandImpact}
                        commandMeta={commandDisplay.get(node.id)}
                        onSelectNode={onSelectNode}
                      />
                    ))}
                    {hiddenCount > 0 ? (
                      <div className="rounded-md border border-dashed border-slate-200 px-2 py-2 text-xs font-medium text-slate-400 dark:border-slate-800 dark:text-slate-500">
                        {t('meetingWorkbenchHiddenSignals', { count: String(hiddenCount) })}
                      </div>
                    ) : null}
                  </>
                ) : (
                  <div className="rounded-md border border-dashed border-slate-200 px-2 py-3 text-xs text-slate-400 dark:border-slate-800 dark:text-slate-500">
                    {t('meetingWorkbenchAwaitingSignal')}
                  </div>
                )}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
