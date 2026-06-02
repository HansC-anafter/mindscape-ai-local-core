'use client';

import React, { useMemo, useState } from 'react';
import { Plus, Power, Route } from 'lucide-react';
import { settingsApi } from '../../../utils/settingsApi';
import { Card } from '../../Card';

export interface HostResourceLaneManagerLane {
  lane_id: string;
  workspace_id?: string | null;
  capability_scope?: string | null;
  label?: string | null;
  kind?: string | null;
  queue_shard?: string | null;
  runner_profile?: string | null;
  resource_class?: string | null;
  priority_class?: string | null;
  resource_flavor?: string | null;
  max_concurrency?: number | null;
  desired_worker_count?: number | null;
  state?: string | null;
}

interface HostResourceLaneManagerPanelProps {
  lanes: HostResourceLaneManagerLane[];
  onRefresh: () => Promise<void>;
}

function slugifyLaneName(label: string): string {
  const slug = label
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
  return slug || 'vision_lane';
}

function stateClass(state?: string | null): string {
  if (state === 'available') return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  if (state === 'paused' || state === 'busy') return 'border-amber-200 bg-amber-50 text-amber-700';
  if (state === 'degraded' || state === 'critical') return 'border-red-200 bg-red-50 text-red-700';
  return 'border-gray-200 bg-gray-50 text-gray-600 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300';
}

export function HostResourceLaneManagerPanel({
  lanes,
  onRefresh,
}: HostResourceLaneManagerPanelProps) {
  const [label, setLabel] = useState('');
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const managedLanes = useMemo(() => (
    [...lanes]
      .filter((lane) => lane.queue_shard || lane.capability_scope === 'ig')
      .sort((a, b) => String(a.label || a.lane_id).localeCompare(String(b.label || b.lane_id)))
  ), [lanes]);

  const createLane = async () => {
    const nextLabel = label.trim();
    if (!nextLabel) return;
    const slug = slugifyLaneName(nextLabel);
    setBusyKey('create');
    setError(null);
    try {
      await settingsApi.post('/api/v1/host-resources/lanes', {
        lane_id: `runner:${slug}`,
        workspace_id: null,
        capability_scope: 'ig',
        label: nextLabel,
        kind: 'vision_analyze',
        queue_shard: slug,
        runner_profile: slug,
        resource_class: 'compute',
        priority_class: 'interactive_high',
        resource_flavor: 'local.mlx.vision',
        max_concurrency: 1,
        desired_worker_count: 0,
        model_profile: {},
        metadata: { source: 'settings_host_resources' },
      });
      setLabel('');
      await onRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create lane');
    } finally {
      setBusyKey(null);
    }
  };

  const setWorkerTarget = async (lane: HostResourceLaneManagerLane, desiredWorkerCount: number) => {
    setBusyKey(`worker:${lane.lane_id}`);
    setError(null);
    try {
      const result = await settingsApi.post<{ accepted?: boolean; reason?: string }>(
        `/api/v1/host-resources/lanes/${encodeURIComponent(lane.lane_id)}/worker-target`,
        { desired_worker_count: desiredWorkerCount },
      );
      if (result?.accepted === false && result.reason) {
        setError(result.reason);
      }
      await onRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to set worker target');
    } finally {
      setBusyKey(null);
    }
  };

  return (
    <Card className="p-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold text-primary dark:text-gray-100">
            <Route className="h-4 w-4 text-secondary dark:text-gray-400" aria-hidden="true" />
            Lane Manager
          </div>
          <div className="mt-1 text-xs text-secondary dark:text-gray-400">
            {managedLanes.length} registered lane{managedLanes.length === 1 ? '' : 's'}
          </div>
        </div>
        <div className="flex min-w-0 gap-2">
          <input
            value={label}
            onChange={(event) => setLabel(event.target.value)}
            placeholder="Lane name"
            className="h-9 min-w-0 rounded-md border border-default bg-surface px-2 text-sm text-primary outline-none focus:border-blue-400 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
          />
          <button
            type="button"
            onClick={() => void createLane()}
            disabled={!label.trim() || busyKey === 'create'}
            className="inline-flex h-9 items-center gap-1 rounded-md border border-default px-3 text-sm font-medium text-primary hover:bg-surface-secondary disabled:opacity-50 dark:border-gray-700 dark:text-gray-100 dark:hover:bg-gray-800"
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            Add
          </button>
        </div>
      </div>

      {error ? (
        <div className="mt-3 rounded-md border border-red-200 bg-red-50 p-2 text-xs text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </div>
      ) : null}

      <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-2">
        {managedLanes.map((lane) => {
          const desired = Math.max(0, Number(lane.desired_worker_count || 0));
          const maxConcurrency = Math.max(1, Number(lane.max_concurrency || 1));
          const nextTarget = desired > 0 ? 0 : 1;
          return (
            <div
              key={lane.lane_id}
              className="rounded-md border border-default p-3 dark:border-gray-700"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-primary dark:text-gray-100">
                    {lane.label || lane.lane_id}
                  </div>
                  <div className="mt-1 truncate text-xs text-secondary dark:text-gray-400">
                    {lane.queue_shard || 'no shard'} · {lane.runner_profile || 'no profile'}
                  </div>
                </div>
                <span className={`shrink-0 rounded-md border px-2 py-0.5 text-[11px] font-medium ${stateClass(lane.state)}`}>
                  {lane.state || 'unknown'}
                </span>
              </div>
              <div className="mt-3 flex items-center justify-between gap-2">
                <div className="text-xs text-secondary dark:text-gray-400">
                  target {desired}/{maxConcurrency}
                </div>
                <button
                  type="button"
                  onClick={() => void setWorkerTarget(lane, Math.min(nextTarget, maxConcurrency))}
                  disabled={busyKey === `worker:${lane.lane_id}`}
                  className="inline-flex h-8 items-center gap-1 rounded-md border border-default px-2 text-xs font-medium text-primary hover:bg-surface-secondary disabled:opacity-50 dark:border-gray-700 dark:text-gray-100 dark:hover:bg-gray-800"
                >
                  <Power className="h-3.5 w-3.5" aria-hidden="true" />
                  {desired > 0 ? 'Stop' : 'Target 1'}
                </button>
              </div>
            </div>
          );
        })}
        {!managedLanes.length ? (
          <div className="rounded-md border border-default p-3 text-sm text-secondary dark:border-gray-700 dark:text-gray-400">
            No lanes available.
          </div>
        ) : null}
      </div>
    </Card>
  );
}
