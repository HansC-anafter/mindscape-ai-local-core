'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { RefreshCw, Route, ShieldAlert, SlidersHorizontal } from 'lucide-react';
import { Card } from '../../Card';
import {
  loadRuntimeDispatchMetadata,
  type RuntimeDispatchMetadata,
  type RuntimeDispatchTarget,
} from './runtimeDispatchClient';

interface HostResourceRuntimeDispatchPanelProps {
  workspaceId?: string;
}

function gateClass(enabled?: boolean): string {
  if (enabled) {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300';
  }
  return 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300';
}

function stateClass(target: RuntimeDispatchTarget): string {
  if (target.assignable) {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300';
  }
  return 'border-gray-200 bg-gray-50 text-gray-600 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300';
}

function shortNumber(value?: number | null): string {
  return value == null ? '-' : String(value);
}

export function HostResourceRuntimeDispatchPanel({
  workspaceId,
}: HostResourceRuntimeDispatchPanelProps) {
  const [metadata, setMetadata] = useState<RuntimeDispatchMetadata | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadMetadata = useCallback(async () => {
    const normalizedWorkspaceId = workspaceId?.trim();
    if (!normalizedWorkspaceId) {
      setMetadata(null);
      setError('Workspace id is required for runtime dispatch metadata.');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      setMetadata(await loadRuntimeDispatchMetadata(normalizedWorkspaceId));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load runtime dispatch metadata');
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    void loadMetadata();
  }, [loadMetadata]);

  const featureGate = metadata?.targets.feature_gate || metadata?.selectors.feature_gate;
  const targets = useMemo(
    () => (Array.isArray(metadata?.targets.targets) ? metadata.targets.targets : []),
    [metadata],
  );
  const selectorTypes = useMemo(
    () => (
      Array.isArray(metadata?.selectors.selector_types)
        ? metadata.selectors.selector_types
        : []
    ),
    [metadata],
  );

  return (
    <div data-testid="runtime-dispatch-metadata-panel">
      <Card className="p-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 text-sm font-semibold text-primary dark:text-gray-100">
            <Route className="h-4 w-4 text-secondary dark:text-gray-400" aria-hidden="true" />
            Runtime Dispatch
            <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${gateClass(featureGate?.enabled)}`}>
              {featureGate?.enabled ? 'Enabled' : 'Disabled'}
            </span>
          </div>
          <div className="mt-1 text-xs text-secondary dark:text-gray-400">
            {metadata?.targets.metadata_source || 'host_resources_lane_registry'} | {targets.length} target{targets.length === 1 ? '' : 's'} | {selectorTypes.length} selector type{selectorTypes.length === 1 ? '' : 's'}
          </div>
        </div>
        <button
          type="button"
          onClick={() => void loadMetadata()}
          disabled={loading}
          className="inline-flex h-9 items-center gap-2 rounded-md border border-default px-3 text-sm font-medium text-primary hover:bg-surface-secondary disabled:opacity-50 dark:border-gray-700 dark:text-gray-100 dark:hover:bg-gray-800"
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          Refresh
        </button>
        </div>

        {error ? (
          <div className="mt-3 flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
            <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            <span>{error}</span>
          </div>
        ) : null}

        <div className="mt-4 grid grid-cols-1 gap-3 xl:grid-cols-2">
        <div className="rounded-md border border-default dark:border-gray-700">
          <div className="flex items-center gap-2 border-b border-default px-3 py-2 text-xs font-semibold text-secondary dark:border-gray-700 dark:text-gray-400">
            <SlidersHorizontal className="h-3.5 w-3.5" aria-hidden="true" />
            Selector Types
          </div>
          <div className="divide-y divide-default dark:divide-gray-700">
            {selectorTypes.map((selector) => (
              <div key={selector.selector_type} className="px-3 py-2">
                <div className="text-sm font-medium text-primary dark:text-gray-100">
                  {selector.label || selector.selector_type}
                </div>
                <div className="mt-1 text-xs text-secondary dark:text-gray-400">
                  max {selector.max_items ?? metadata?.selectors.limits?.max_items ?? 500} | workspace scoped {selector.workspace_scope_required ? 'yes' : 'no'}
                </div>
              </div>
            ))}
            {!selectorTypes.length ? (
              <div className="px-3 py-4 text-sm text-secondary dark:text-gray-400">
                {loading ? 'Loading selector metadata...' : 'No selector metadata available.'}
              </div>
            ) : null}
          </div>
        </div>

        <div className="rounded-md border border-default dark:border-gray-700">
          <div className="flex items-center gap-2 border-b border-default px-3 py-2 text-xs font-semibold text-secondary dark:border-gray-700 dark:text-gray-400">
            <Route className="h-3.5 w-3.5" aria-hidden="true" />
            Dispatch Targets
          </div>
          <div className="divide-y divide-default dark:divide-gray-700">
            {targets.map((target) => (
              <div key={target.target_id || target.lane_id} className="px-3 py-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium text-primary dark:text-gray-100">
                    {target.label || target.lane_id}
                  </span>
                  <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${stateClass(target)}`}>
                    {target.assignable ? 'Assignable' : target.assignability_reason || target.state || 'Unavailable'}
                  </span>
                </div>
                <div className="mt-1 text-xs text-secondary dark:text-gray-400">
                  {target.queue_shard || 'no queue'} | {target.runner_profile || 'no runner'} | slots {shortNumber(target.capacity_summary?.available_slots_total)} | pending {shortNumber(target.capacity_summary?.pending)}
                </div>
              </div>
            ))}
            {!targets.length ? (
              <div className="px-3 py-4 text-sm text-secondary dark:text-gray-400">
                {loading ? 'Loading target metadata...' : 'No dispatch targets available.'}
              </div>
            ) : null}
          </div>
        </div>
        </div>
      </Card>
    </div>
  );
}
