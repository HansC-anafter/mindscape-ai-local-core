'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  CheckCircle2,
  Layers,
  RefreshCw,
  RotateCw,
  ShieldCheck,
  SlidersHorizontal,
} from 'lucide-react';
import { settingsApi } from '../../../utils/settingsApi';
import { Card } from '../../Card';
import type { HostResourceLaneManagerLane } from './HostResourceLaneManagerPanel';

interface HostResourceWorkspaceAllocationsPanelProps {
  lanes: HostResourceLaneManagerLane[];
  workspaceId?: string;
}

interface ResourceGovernanceContext {
  mode?: string;
  scope?: string;
  is_global_admin?: boolean;
  user_id?: string;
  tenant_id?: string;
  workspace_id?: string | null;
  workspace_ids?: string[];
  can_manage_global?: boolean;
  can_manage_workspace_allocations?: boolean;
}

interface WorkspaceAllocation {
  allocation_id: string;
  workspace_id: string;
  lane_id: string;
  label?: string;
  max_worker_target?: number;
  max_concurrency?: number;
  queue_shard?: string;
  task_family?: string;
  max_parallel_task_claims?: number;
  share_policy?: string;
  priority_ceiling?: string;
  blueprint_id?: string;
  applied_at?: string;
  state?: string;
  updated_at?: string;
}

interface WorkspaceAllocationApplication {
  application_id?: string;
  workspace_id?: string;
  blueprint_id?: string;
  state?: string;
  applied_by?: string;
  applied_at?: string;
}

interface WorkspaceEffectiveMatrixRow {
  allocation_id?: string;
  workspace_id?: string;
  queue_shard?: string;
  task_family?: string;
  label?: string;
  max_parallel_task_claims?: number;
  share_policy?: string;
  priority_ceiling?: string;
  state?: string;
  blueprint_id?: string;
  applied_at?: string;
  pending?: number;
  processing?: number;
  global_max_inflight?: number;
  global_available_slots?: number;
}

interface WorkspaceEffectiveAllocation {
  workspace_id?: string;
  applications?: WorkspaceAllocationApplication[];
  effective_matrix?: WorkspaceEffectiveMatrixRow[];
  queue_snapshot?: {
    source?: string;
    captured_at?: string;
    degraded?: boolean;
  };
}

interface AllocationBlueprintSummary {
  blueprint_id: string;
  label?: string;
  scope?: string;
  state?: string;
}

const DEFAULT_BLUEPRINT_ID = 'local-core-workspace-default';

function initialWorkspaceId(workspaceId?: string): string {
  if (workspaceId) return workspaceId;
  if (typeof window === 'undefined') return '';
  return new URLSearchParams(window.location.search).get('workspace_id') || '';
}

function formatDateTime(value?: string): string {
  if (!value) return 'not applied';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function allocationRowsFallback(allocations: WorkspaceAllocation[]): WorkspaceEffectiveMatrixRow[] {
  return allocations
    .filter((allocation) => allocation.queue_shard)
    .map((allocation) => ({
      allocation_id: allocation.allocation_id,
      workspace_id: allocation.workspace_id,
      queue_shard: allocation.queue_shard,
      task_family: allocation.task_family,
      label: allocation.label,
      max_parallel_task_claims: allocation.max_parallel_task_claims,
      share_policy: allocation.share_policy,
      priority_ceiling: allocation.priority_ceiling,
      state: allocation.state,
      blueprint_id: allocation.blueprint_id,
      applied_at: allocation.applied_at,
      pending: 0,
      processing: 0,
      global_max_inflight: 0,
      global_available_slots: 0,
    }));
}

export function HostResourceWorkspaceAllocationsPanel({
  lanes,
  workspaceId,
}: HostResourceWorkspaceAllocationsPanelProps) {
  const [context, setContext] = useState<ResourceGovernanceContext | null>(null);
  const [allocations, setAllocations] = useState<WorkspaceAllocation[]>([]);
  const [effective, setEffective] = useState<WorkspaceEffectiveAllocation | null>(null);
  const [blueprints, setBlueprints] = useState<AllocationBlueprintSummary[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState(() => initialWorkspaceId(workspaceId));
  const [selectedBlueprintId, setSelectedBlueprintId] = useState(DEFAULT_BLUEPRINT_ID);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (workspaceId) {
      setSelectedWorkspaceId(workspaceId);
    }
  }, [workspaceId]);

  const queryWorkspaceId = useMemo(
    () => selectedWorkspaceId.trim() || workspaceId || '',
    [selectedWorkspaceId, workspaceId],
  );

  const loadState = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const query = queryWorkspaceId ? `?workspace_id=${encodeURIComponent(queryWorkspaceId)}` : '';
      const [contextData, allocationData] = await Promise.all([
        settingsApi.get<ResourceGovernanceContext>(`/api/v1/resource-governance/context${query}`),
        settingsApi.get<{
          allocations?: WorkspaceAllocation[];
          effective?: WorkspaceEffectiveAllocation | null;
          governance_context?: ResourceGovernanceContext;
        }>(`/api/v1/host-resources/workspace-allocations${query}`),
      ]);
      const resolvedContext = allocationData.governance_context || contextData;
      setContext(resolvedContext);
      setAllocations(Array.isArray(allocationData.allocations) ? allocationData.allocations : []);
      setEffective(allocationData.effective || null);
      setSelectedWorkspaceId((current) => current || resolvedContext.workspace_id || workspaceId || '');

      if (resolvedContext.can_manage_global) {
        const blueprintData = await settingsApi.get<{ blueprints?: AllocationBlueprintSummary[] }>(
          '/api/v1/host-resources/allocation-blueprints',
        );
        const nextBlueprints = Array.isArray(blueprintData.blueprints) ? blueprintData.blueprints : [];
        setBlueprints(nextBlueprints);
        if (nextBlueprints.length > 0) {
          setSelectedBlueprintId((current) => (
            nextBlueprints.some((blueprint) => blueprint.blueprint_id === current)
              ? current
              : nextBlueprints[0].blueprint_id
          ));
        }
      } else {
        setBlueprints([]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load workspace allocations');
    } finally {
      setBusy(false);
    }
  }, [queryWorkspaceId, workspaceId]);

  useEffect(() => {
    void loadState();
  }, [loadState]);

  const matrixRows = useMemo(
    () => (
      Array.isArray(effective?.effective_matrix) && effective.effective_matrix.length > 0
        ? effective.effective_matrix
        : allocationRowsFallback(allocations)
    ),
    [allocations, effective],
  );
  const latestApplication = effective?.applications?.[0] || null;
  const appliedBlueprintLabel = useMemo(() => {
    const appliedId = latestApplication?.blueprint_id || matrixRows[0]?.blueprint_id;
    if (!appliedId) return 'No blueprint applied';
    return blueprints.find((blueprint) => blueprint.blueprint_id === appliedId)?.label || appliedId;
  }, [blueprints, latestApplication, matrixRows]);
  const canManageWorkspace = Boolean(context?.can_manage_workspace_allocations);
  const selectedWorkspaceLabel = queryWorkspaceId || context?.workspace_id || 'No workspace selected';
  const runtimeLaneCount = lanes.length;

  const applyBlueprint = async () => {
    const workspace = queryWorkspaceId || context?.workspace_id || '';
    if (!workspace || !selectedBlueprintId) return;
    setBusy(true);
    setError(null);
    try {
      const result = await settingsApi.post<{
        allocations?: WorkspaceAllocation[];
        effective?: WorkspaceEffectiveAllocation | null;
        governance_context?: ResourceGovernanceContext;
      }>(
        `/api/v1/host-resources/allocation-blueprints/${encodeURIComponent(selectedBlueprintId)}/apply`,
        { workspace_id: workspace },
      );
      setAllocations(Array.isArray(result.allocations) ? result.allocations : []);
      setEffective(result.effective || null);
      if (result.governance_context) {
        setContext(result.governance_context);
      }
      await loadState();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to apply allocation blueprint');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4" data-testid="host-resource-workspace-allocations-panel">
      <Card className="p-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold text-primary dark:text-gray-100">
              <SlidersHorizontal className="h-4 w-4 text-secondary dark:text-gray-400" aria-hidden="true" />
              Workspace Resource Allocations
            </div>
            <div className="mt-1 text-xs text-secondary dark:text-gray-400">
              {context?.scope || 'loading'} · {selectedWorkspaceLabel}
            </div>
          </div>
          <button
            type="button"
            onClick={() => void loadState()}
            disabled={busy}
            className="inline-flex h-9 items-center gap-2 rounded-md border border-default px-3 text-sm font-medium text-primary hover:bg-surface-secondary disabled:opacity-50 dark:border-gray-700 dark:text-gray-100 dark:hover:bg-gray-800"
          >
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            Refresh
          </button>
        </div>
        {error ? (
          <div className="mt-3 rounded-md border border-red-200 bg-red-50 p-2 text-xs text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-300">
            {error}
          </div>
        ) : null}
      </Card>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
        <Card className="p-4">
          <div className="flex items-start gap-3">
            <ShieldCheck className="mt-0.5 h-5 w-5 text-secondary dark:text-gray-400" aria-hidden="true" />
            <div className="min-w-0">
              <div className="text-sm font-semibold text-primary dark:text-gray-100">Workspace scope</div>
              <div className="mt-1 break-all text-xs text-secondary dark:text-gray-400">{selectedWorkspaceLabel}</div>
              <div className="mt-3 text-xs text-secondary dark:text-gray-400">
                {context?.can_manage_global ? 'Global admin can allocate every workspace.' : 'Workspace users can only adjust their own quota.'}
              </div>
            </div>
          </div>
        </Card>

        <Card className="p-4 xl:col-span-2">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-sm font-semibold text-primary dark:text-gray-100">
                <Layers className="h-4 w-4 text-secondary dark:text-gray-400" aria-hidden="true" />
                Applied blueprint
              </div>
              <div className="mt-1 truncate text-xs text-secondary dark:text-gray-400">
                {appliedBlueprintLabel}
              </div>
              <div className="mt-2 text-xs text-secondary dark:text-gray-400">
                Applied at {formatDateTime(latestApplication?.applied_at || matrixRows[0]?.applied_at)}
              </div>
            </div>
            <div className="flex flex-col gap-2 sm:flex-row">
              {context?.can_manage_global && blueprints.length > 0 ? (
                <select
                  value={selectedBlueprintId}
                  onChange={(event) => setSelectedBlueprintId(event.target.value)}
                  className="h-9 min-w-[220px] rounded-md border border-default bg-surface px-2 text-sm text-primary outline-none focus:border-blue-400 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
                >
                  {blueprints.map((blueprint) => (
                    <option key={blueprint.blueprint_id} value={blueprint.blueprint_id}>
                      {blueprint.label || blueprint.blueprint_id}
                    </option>
                  ))}
                </select>
              ) : null}
              <button
                type="button"
                onClick={() => void applyBlueprint()}
                disabled={busy || !canManageWorkspace || !queryWorkspaceId}
                className="inline-flex h-9 items-center justify-center gap-2 rounded-md border border-default px-3 text-sm font-medium text-primary hover:bg-surface-secondary disabled:opacity-50 dark:border-gray-700 dark:text-gray-100 dark:hover:bg-gray-800"
              >
                <RotateCw className="h-4 w-4" aria-hidden="true" />
                Apply blueprint
              </button>
            </div>
          </div>
        </Card>
      </div>

      <Card className="p-4">
        <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold text-primary dark:text-gray-100">
              <CheckCircle2 className="h-4 w-4 text-secondary dark:text-gray-400" aria-hidden="true" />
              Effective shared pool quotas
            </div>
            <div className="mt-1 text-xs text-secondary dark:text-gray-400">
              Global runner target is managed by runtime controller · {runtimeLaneCount} registered lane templates
            </div>
          </div>
          <div className="text-xs text-secondary dark:text-gray-400">
            Queue snapshot {formatDateTime(effective?.queue_snapshot?.captured_at)}
          </div>
        </div>

        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full border-separate border-spacing-0 text-left text-sm">
            <thead>
              <tr className="text-xs uppercase tracking-wide text-secondary dark:text-gray-400">
                <th className="border-b border-default px-3 py-2 font-semibold dark:border-gray-700">Shared pool</th>
                <th className="border-b border-default px-3 py-2 font-semibold dark:border-gray-700">Task family</th>
                <th className="border-b border-default px-3 py-2 font-semibold dark:border-gray-700">Max parallel tasks</th>
                <th className="border-b border-default px-3 py-2 font-semibold dark:border-gray-700">Processing</th>
                <th className="border-b border-default px-3 py-2 font-semibold dark:border-gray-700">Pending</th>
                <th className="border-b border-default px-3 py-2 font-semibold dark:border-gray-700">Global capacity</th>
                <th className="border-b border-default px-3 py-2 font-semibold dark:border-gray-700">Policy</th>
              </tr>
            </thead>
            <tbody>
              {matrixRows.map((row) => (
                <tr key={row.allocation_id || `${row.queue_shard}:${row.task_family}`}>
                  <td className="border-b border-default px-3 py-3 text-primary dark:border-gray-800 dark:text-gray-100">
                    {row.queue_shard || 'unknown'}
                  </td>
                  <td className="border-b border-default px-3 py-3 text-primary dark:border-gray-800 dark:text-gray-100">
                    <div className="font-medium">{row.label || row.task_family || 'unlabeled'}</div>
                    <div className="mt-0.5 text-xs text-secondary dark:text-gray-400">{row.task_family || 'unknown'}</div>
                  </td>
                  <td className="border-b border-default px-3 py-3 font-semibold text-primary dark:border-gray-800 dark:text-gray-100">
                    {row.max_parallel_task_claims ?? 0}
                  </td>
                  <td className="border-b border-default px-3 py-3 text-primary dark:border-gray-800 dark:text-gray-100">
                    {row.processing ?? 0}
                  </td>
                  <td className="border-b border-default px-3 py-3 text-primary dark:border-gray-800 dark:text-gray-100">
                    {row.pending ?? 0}
                  </td>
                  <td className="border-b border-default px-3 py-3 text-primary dark:border-gray-800 dark:text-gray-100">
                    {row.global_available_slots ?? 0}/{row.global_max_inflight ?? 0}
                  </td>
                  <td className="border-b border-default px-3 py-3 text-secondary dark:border-gray-800 dark:text-gray-400">
                    {row.share_policy || 'shared_pool'} · {row.state || 'unknown'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {!matrixRows.length ? (
          <div className="mt-4 rounded-md border border-default p-3 text-sm text-secondary dark:border-gray-700 dark:text-gray-400">
            No workspace quota blueprint has been applied for this workspace.
          </div>
        ) : null}
      </Card>
    </div>
  );
}
