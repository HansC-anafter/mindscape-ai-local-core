'use client';

import dynamic from 'next/dynamic';
import React, { useEffect, useMemo, useState } from 'react';
import {
  adaptMemoryImpactGraph,
} from './memory-impact-graph/adapter';
import { useMemoryImpactGraph } from './memory-impact-graph/useMemoryImpactGraph';
import type {
  MemoryImpactGraphQuery,
  MemoryImpactGraphResponse,
  MemoryImpactVisualNode,
} from './memory-impact-graph/types';

const MemoryImpactGraphCanvas = dynamic(
  () =>
    import('./memory-impact-graph/MemoryImpactGraphCanvas').then(
      (mod) => mod.MemoryImpactGraphCanvas
    ),
  {
    ssr: false,
    loading: () => (
      <div className="h-96 rounded-lg border border-slate-200 bg-white/70 px-4 py-6 text-sm text-slate-600 dark:border-slate-700 dark:bg-slate-950/40 dark:text-slate-300">
        Loading graph canvas...
      </div>
    ),
  }
);

interface MemoryImpactGraphPanelProps extends MemoryImpactGraphQuery {
  title?: string;
  description?: string;
  className?: string;
  compact?: boolean;
}

function badgeClass(status?: string | null): string {
  if (!status) {
    return 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300';
  }
  if (status === 'closed' || status === 'active' || status === 'verified') {
    return 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300';
  }
  if (status === 'candidate' || status === 'observed' || status === 'pending') {
    return 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300';
  }
  if (status === 'failed' || status === 'aborted') {
    return 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300';
  }
  return 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300';
}

function nodeTone(node: MemoryImpactVisualNode): string {
  if (node.isFocus) {
    return 'ring-2 ring-sky-300 dark:ring-sky-700';
  }
  if (node.isSelected) {
    return 'ring-1 ring-emerald-300 dark:ring-emerald-700';
  }
  return '';
}

function summarizeNodeMetadata(node: MemoryImpactVisualNode): Array<[string, string]> {
  const metadata = node.metadata || {};
  const pairs: Array<[string, string]> = [];

  const packetLayer = typeof metadata.packet_layer === 'string' ? metadata.packet_layer : null;
  if (packetLayer) {
    pairs.push(['Packet Layer', packetLayer]);
  }

  const verificationStatus =
    typeof metadata.verification_status === 'string'
      ? metadata.verification_status
      : null;
  if (verificationStatus) {
    pairs.push(['Verification', verificationStatus]);
  }

  const executionId =
    typeof metadata.execution_id === 'string' ? metadata.execution_id : null;
  if (executionId) {
    pairs.push(['Execution', executionId]);
  }

  const decisionId =
    typeof metadata.decision_id === 'string' ? metadata.decision_id : null;
  if (decisionId) {
    pairs.push(['Decision', decisionId]);
  }

  const memoryItemId =
    typeof metadata.memory_item_id === 'string' ? metadata.memory_item_id : null;
  if (memoryItemId) {
    pairs.push(['Memory Item', memoryItemId]);
  }

  const digestId = typeof metadata.digest_id === 'string' ? metadata.digest_id : null;
  if (digestId) {
    pairs.push(['Digest', digestId]);
  }

  const artifactRef =
    typeof metadata.artifact_ref === 'string' ? metadata.artifact_ref : null;
  if (artifactRef) {
    pairs.push(['Artifact', artifactRef]);
  }

  const writebackRunId =
    typeof metadata.writeback_run_id === 'string'
      ? metadata.writeback_run_id
      : null;
  if (writebackRunId) {
    pairs.push(['Writeback Run', writebackRunId]);
  }

  return pairs;
}

function MemoryImpactNodeDetail({
  node,
  response,
}: {
  node: MemoryImpactVisualNode | null;
  response: MemoryImpactGraphResponse | null;
}) {
  if (!node || !response) {
    return (
      <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50/70 p-4 text-sm text-slate-600 dark:border-slate-700 dark:bg-slate-900/40 dark:text-slate-300">
        Select a node to inspect why it was activated or produced.
      </div>
    );
  }

  const incoming = response.edges.filter((edge) => edge.to_node_id === node.id);
  const outgoing = response.edges.filter((edge) => edge.from_node_id === node.id);
  const metadataPairs = summarizeNodeMetadata(node);
  const detailText =
    typeof node.metadata.summary === 'string'
      ? node.metadata.summary
      : typeof node.metadata.description === 'string'
        ? node.metadata.description
        : typeof node.metadata.content === 'string'
          ? node.metadata.content
          : typeof node.metadata.claim === 'string'
            ? node.metadata.claim
            : null;

  return (
    <div className={`rounded-lg border border-slate-200 bg-white/80 p-4 shadow-sm dark:border-slate-700 dark:bg-slate-950/40 ${nodeTone(node)}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[10px] font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
            {node.type.replace(/_/g, ' ')}
          </div>
          <div className="mt-1 text-sm font-semibold text-slate-900 dark:text-slate-100">
            {node.label}
          </div>
          {node.subtitle && (
            <div className="mt-1 text-xs text-slate-600 dark:text-slate-300">
              {node.subtitle}
            </div>
          )}
        </div>
        {node.status && (
          <span className={`rounded px-2 py-1 text-[11px] font-medium ${badgeClass(node.status)}`}>
            {node.status}
          </span>
        )}
      </div>

      {detailText && (
        <div className="mt-3 text-sm leading-6 text-slate-700 dark:text-slate-200">
          {detailText}
        </div>
      )}

      {metadataPairs.length > 0 && (
        <div className="mt-4 grid gap-2 sm:grid-cols-2">
          {metadataPairs.map(([label, value]) => (
            <div
              key={`${node.id}:${label}`}
              className="rounded-md bg-slate-50 px-3 py-2 dark:bg-slate-900/70"
            >
              <div className="text-[10px] uppercase tracking-wide text-slate-500 dark:text-slate-400">
                {label}
              </div>
              <div className="mt-1 break-all text-xs text-slate-700 dark:text-slate-200">
                {value}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <div className="rounded-md bg-slate-50 px-3 py-3 dark:bg-slate-900/70">
          <div className="text-[10px] uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Incoming Edges
          </div>
          <div className="mt-2 space-y-2">
            {incoming.length > 0 ? incoming.map((edge) => (
              <div key={edge.id} className="text-xs text-slate-700 dark:text-slate-200">
                <span className="font-medium">{edge.kind}</span>
                <span className="ml-1 text-slate-500 dark:text-slate-400">
                  · {edge.provenance}
                </span>
              </div>
            )) : (
              <div className="text-xs text-slate-500 dark:text-slate-400">None</div>
            )}
          </div>
        </div>
        <div className="rounded-md bg-slate-50 px-3 py-3 dark:bg-slate-900/70">
          <div className="text-[10px] uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Outgoing Edges
          </div>
          <div className="mt-2 space-y-2">
            {outgoing.length > 0 ? outgoing.map((edge) => (
              <div key={edge.id} className="text-xs text-slate-700 dark:text-slate-200">
                <span className="font-medium">{edge.kind}</span>
                <span className="ml-1 text-slate-500 dark:text-slate-400">
                  · {edge.provenance}
                </span>
              </div>
            )) : (
              <div className="text-xs text-slate-500 dark:text-slate-400">None</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export function MemoryImpactGraphPanel({
  workspaceId,
  apiUrl,
  sessionId,
  executionId,
  threadId,
  title = 'Selected Memory Subgraph',
  description = 'This task-centered view shows which memory nodes were selected for context, what the session produced, and where writeback landed.',
  className = '',
  compact = false,
}: MemoryImpactGraphPanelProps) {
  const { data, loading, error } = useMemoryImpactGraph({
    workspaceId,
    apiUrl,
    sessionId,
    executionId,
    threadId,
  });

  const adapted = useMemo(
    () => (data ? adaptMemoryImpactGraph(data) : null),
    [data]
  );
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  useEffect(() => {
    setSelectedNodeId(adapted?.defaultSelectedNodeId || null);
  }, [adapted?.defaultSelectedNodeId]);

  const selectedNode = useMemo(
    () => adapted?.nodes.find((node) => node.id === selectedNodeId) || null,
    [adapted?.nodes, selectedNodeId]
  );

  const countsByType = data?.packet_summary.counts_by_type || {};
  const routeSections = data?.packet_summary.route_sections || [];
  const warnings = data?.warnings || [];
  const heightClass = compact ? 'h-72' : 'h-96';

  return (
    <div className={`rounded-xl border border-slate-200 bg-slate-50/70 p-4 dark:border-slate-700 dark:bg-slate-900/40 ${className}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="text-[10px] font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Memory Impact
          </div>
          <div className="mt-1 text-sm font-semibold text-slate-900 dark:text-slate-100">
            {title}
          </div>
          <div className="mt-1 text-xs leading-5 text-slate-600 dark:text-slate-300">
            {description}
          </div>
        </div>
        {data?.focus.session_id && (
          <div className="rounded-md bg-white/80 px-3 py-2 text-right text-xs text-slate-600 shadow-sm dark:bg-slate-950/60 dark:text-slate-300">
            <div className="font-medium text-slate-900 dark:text-slate-100">
              Session {data.focus.session_id.slice(0, 8)}
            </div>
            {data.focus.execution_ids.length > 0 && (
              <div className="mt-1">
                {data.focus.execution_ids.length} execution
                {data.focus.execution_ids.length > 1 ? 's' : ''}
              </div>
            )}
          </div>
        )}
      </div>

      {loading ? (
        <div className="mt-4 rounded-lg border border-slate-200 bg-white/80 px-4 py-6 text-sm text-slate-600 dark:border-slate-700 dark:bg-slate-950/40 dark:text-slate-300">
          Loading memory impact graph...
        </div>
      ) : error ? (
        <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-6 text-sm text-amber-800 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-200">
          {error}
        </div>
      ) : !data || !adapted || adapted.nodes.length === 0 ? (
        <div className="mt-4 rounded-lg border border-dashed border-slate-300 bg-white/70 px-4 py-6 text-sm text-slate-600 dark:border-slate-700 dark:bg-slate-950/40 dark:text-slate-300">
          No memory impact graph is available for this scope yet.
        </div>
      ) : (
        <>
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            <div className="rounded-lg border border-slate-200 bg-white/80 px-3 py-3 dark:border-slate-700 dark:bg-slate-950/40">
              <div className="text-[10px] uppercase tracking-wide text-slate-500 dark:text-slate-400">
                Selected Packet
              </div>
              <div className="mt-1 text-lg font-semibold text-slate-900 dark:text-slate-100">
                {data.packet_summary.selected_node_count}
              </div>
              <div className="mt-1 text-xs text-slate-600 dark:text-slate-300">
                nodes selected for task context
              </div>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white/80 px-3 py-3 dark:border-slate-700 dark:bg-slate-950/40">
              <div className="text-[10px] uppercase tracking-wide text-slate-500 dark:text-slate-400">
                Route Sections
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                {routeSections.length > 0 ? routeSections.map((section) => (
                  <span
                    key={section}
                    className="rounded-full bg-sky-100 px-2 py-1 text-[11px] font-medium text-sky-800 dark:bg-sky-900/30 dark:text-sky-300"
                  >
                    {section.replace(/_/g, ' ')}
                  </span>
                )) : (
                  <span className="text-xs text-slate-500 dark:text-slate-400">None</span>
                )}
              </div>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white/80 px-3 py-3 dark:border-slate-700 dark:bg-slate-950/40">
              <div className="text-[10px] uppercase tracking-wide text-slate-500 dark:text-slate-400">
                Graph Footprint
              </div>
              <div className="mt-1 text-lg font-semibold text-slate-900 dark:text-slate-100">
                {adapted.nodes.length} / {adapted.edges.length}
              </div>
              <div className="mt-1 text-xs text-slate-600 dark:text-slate-300">
                nodes / edges in the focused subgraph
              </div>
            </div>
          </div>

          {warnings.length > 0 && (
            <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-3 text-xs text-amber-800 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-200">
              {warnings.join(' · ')}
            </div>
          )}

          <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,2fr),minmax(320px,1fr)]">
            <div className="space-y-3">
              <MemoryImpactGraphCanvas
                nodes={adapted.nodes}
                edges={adapted.edges}
                onNodeClick={(node) => setSelectedNodeId(node.id)}
                heightClass={heightClass}
              />

              <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                {Object.entries(countsByType).map(([type, count]) => (
                  <div
                    key={type}
                    className="rounded-md bg-white/80 px-3 py-2 text-xs text-slate-700 shadow-sm dark:bg-slate-950/40 dark:text-slate-200"
                  >
                    <div className="uppercase tracking-wide text-slate-500 dark:text-slate-400">
                      {type.replace(/_/g, ' ')}
                    </div>
                    <div className="mt-1 text-sm font-semibold text-slate-900 dark:text-slate-100">
                      {count}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <MemoryImpactNodeDetail node={selectedNode} response={data} />
          </div>
        </>
      )}
    </div>
  );
}
