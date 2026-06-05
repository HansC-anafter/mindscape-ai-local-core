'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Pause, Play, RefreshCw, Square } from 'lucide-react';
import { settingsApi } from '../../../utils/settingsApi';
import { Card } from '../../Card';

interface RunnerCapacity {
  max_inflight?: number;
  inflight?: number;
  available_slots?: number;
  saturated?: boolean;
}

interface RunnerClaimControl {
  mode?: string;
  claim_enabled?: boolean;
  reason?: string | null;
  updated_at?: string | null;
  source?: string | null;
}

interface HostResourceRunner {
  runner_id?: string;
  profile_code?: string;
  queue_shards?: string[];
  capacity?: RunnerCapacity;
  claim_control?: RunnerClaimControl;
}

interface SpilloverControlResult {
  accepted?: boolean;
  action?: string;
  profile_code?: string;
  max_inflight?: number;
  reason?: string;
  result?: {
    status?: {
      running?: boolean;
      raw?: string;
      rows?: unknown[];
    };
    stdout?: string;
    stderr?: string;
    exit_code?: number | null;
  };
}

function modeClass(mode: string): string {
  if (mode === 'active') return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  if (mode === 'drain') return 'border-amber-200 bg-amber-50 text-amber-700';
  if (mode === 'paused') return 'border-red-200 bg-red-50 text-red-700';
  return 'border-gray-200 bg-gray-50 text-gray-600 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300';
}

function runnerLabel(runner: HostResourceRunner): string {
  return String(runner.profile_code || runner.runner_id || 'runner');
}

export function HostResourceRunnerControlPanel() {
  const [runners, setRunners] = useState<HostResourceRunner[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyRunnerId, setBusyRunnerId] = useState<string | null>(null);
  const [busySpilloverAction, setBusySpilloverAction] = useState<string | null>(null);
  const [spilloverProfile, setSpilloverProfile] = useState('default_local');
  const [spilloverMaxInflight, setSpilloverMaxInflight] = useState(1);
  const [spilloverStatus, setSpilloverStatus] = useState<SpilloverControlResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const sortedRunners = useMemo(() => (
    [...runners].sort((a, b) => runnerLabel(a).localeCompare(runnerLabel(b)))
  ), [runners]);

  const loadRunners = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const payload = await settingsApi.get<{ runners?: HostResourceRunner[] }>(
        '/api/v1/host-resources/runners',
      );
      setRunners(Array.isArray(payload.runners) ? payload.runners : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load runners');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadSpilloverStatus = useCallback(async () => {
    try {
      const payload = await settingsApi.get<SpilloverControlResult>(
        '/api/v1/host-resources/runner-spillover',
      );
      setSpilloverStatus(payload);
    } catch (err) {
      setSpilloverStatus({
        accepted: false,
        reason: err instanceof Error ? err.message : 'Failed to load spillover status',
      });
    }
  }, []);

  useEffect(() => {
    void loadRunners();
    void loadSpilloverStatus();
  }, [loadRunners, loadSpilloverStatus]);

  const setClaimMode = async (runnerId: string, mode: 'active' | 'drain') => {
    setBusyRunnerId(runnerId);
    setError(null);
    try {
      await settingsApi.put(
        `/api/v1/host-resources/runners/${encodeURIComponent(runnerId)}/claim-mode`,
        {
          mode,
          reason: mode === 'drain' ? 'operator_drain' : 'operator_resume',
          ttl_seconds: 21600,
        },
      );
      await loadRunners();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update runner');
    } finally {
      setBusyRunnerId(null);
    }
  };

  const refreshAll = async () => {
    await Promise.all([loadRunners(), loadSpilloverStatus()]);
  };

  const runSpilloverAction = async (action: 'start' | 'stop' | 'status') => {
    setBusySpilloverAction(action);
    setError(null);
    try {
      const payload = await settingsApi.post<SpilloverControlResult>(
        '/api/v1/host-resources/runner-spillover',
        {
          action,
          profile_code: spilloverProfile,
          max_inflight: spilloverMaxInflight,
        },
      );
      setSpilloverStatus(payload);
      await refreshAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update spillover runner');
    } finally {
      setBusySpilloverAction(null);
    }
  };

  const spilloverRunning = Boolean(spilloverStatus?.result?.status?.running);
  const spilloverBusy = Boolean(busySpilloverAction);

  return (
    <Card className="p-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <div className="text-sm font-semibold text-primary dark:text-gray-100">
            Runner Control
          </div>
          <div className="mt-1 text-xs text-secondary dark:text-gray-400">
            {loading ? 'Loading' : `${sortedRunners.length} active runner${sortedRunners.length === 1 ? '' : 's'}`}
          </div>
        </div>
        <button
          type="button"
          onClick={() => void refreshAll()}
          className="inline-flex h-9 items-center gap-2 rounded-md border border-default px-3 text-sm font-medium text-primary hover:bg-surface-secondary disabled:opacity-50 dark:border-gray-700 dark:text-gray-100 dark:hover:bg-gray-800"
          disabled={loading}
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          Refresh
        </button>
      </div>

      <div className="mt-4 rounded-md border border-default p-3 dark:border-gray-700">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div className="grid flex-1 grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_112px]">
            <label className="flex flex-col gap-1 text-xs font-medium text-secondary dark:text-gray-400">
              <span>Spillover profile</span>
              <select
                value={spilloverProfile}
                onChange={(event) => setSpilloverProfile(event.target.value)}
                className="h-9 rounded-md border border-default bg-white px-2 text-sm text-primary dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
                disabled={spilloverBusy}
              >
                <option value="default_local">default_local</option>
                <option value="browser_local">browser_local</option>
                <option value="vision_local">vision_local</option>
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs font-medium text-secondary dark:text-gray-400">
              <span>Max inflight</span>
              <input
                type="number"
                min={1}
                max={4}
                value={spilloverMaxInflight}
                onChange={(event) => {
                  const next = Number.parseInt(event.target.value || '1', 10);
                  setSpilloverMaxInflight(Number.isFinite(next) ? Math.min(Math.max(next, 1), 4) : 1);
                }}
                className="h-9 rounded-md border border-default bg-white px-2 text-sm text-primary dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
                disabled={spilloverBusy}
              />
            </label>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className={`rounded-md border px-2 py-1 text-xs font-medium ${spilloverRunning ? modeClass('active') : modeClass('paused')}`}>
              {spilloverRunning ? 'running' : 'stopped'}
            </span>
            <button
              type="button"
              onClick={() => void runSpilloverAction('status')}
              className="inline-flex h-9 items-center gap-2 rounded-md border border-default px-3 text-sm font-medium text-primary hover:bg-surface-secondary disabled:opacity-50 dark:border-gray-700 dark:text-gray-100 dark:hover:bg-gray-800"
              disabled={spilloverBusy}
            >
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              Status
            </button>
            <button
              type="button"
              onClick={() => void runSpilloverAction('start')}
              className="inline-flex h-9 items-center gap-2 rounded-md border border-emerald-200 bg-emerald-50 px-3 text-sm font-medium text-emerald-700 hover:bg-emerald-100 disabled:opacity-50 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-300"
              disabled={spilloverBusy || spilloverRunning}
            >
              <Play className="h-4 w-4" aria-hidden="true" />
              Start
            </button>
            <button
              type="button"
              onClick={() => void runSpilloverAction('stop')}
              className="inline-flex h-9 items-center gap-2 rounded-md border border-red-200 bg-red-50 px-3 text-sm font-medium text-red-700 hover:bg-red-100 disabled:opacity-50 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300"
              disabled={spilloverBusy || !spilloverRunning}
            >
              <Square className="h-4 w-4" aria-hidden="true" />
              Stop
            </button>
          </div>
        </div>
        {spilloverStatus?.reason ? (
          <div className="mt-2 rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-300">
            {spilloverStatus.reason}
          </div>
        ) : null}
      </div>

      {error ? (
        <div className="mt-3 rounded-md border border-red-200 bg-red-50 p-2 text-xs text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </div>
      ) : null}

      <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-2">
        {sortedRunners.map((runner) => {
          const runnerId = String(runner.runner_id || '').trim();
          const capacity = runner.capacity || {};
          const claimControl = runner.claim_control || {};
          const mode = String(claimControl.mode || 'active').toLowerCase();
          const isDrain = mode === 'drain' || mode === 'paused';
          const nextMode = isDrain ? 'active' : 'drain';
          return (
            <div
              key={runnerId}
              className="rounded-md border border-default p-3 dark:border-gray-700"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-primary dark:text-gray-100">
                    {runnerLabel(runner)}
                  </div>
                  <div className="mt-1 truncate text-xs text-secondary dark:text-gray-400">
                    {runner.queue_shards?.join(', ') || 'no shard'}
                  </div>
                  <div className="mt-1 truncate text-xs text-secondary dark:text-gray-400">
                    {runnerId || 'no runner id'}
                  </div>
                </div>
                <span className={`shrink-0 rounded-md border px-2 py-0.5 text-[11px] font-medium ${modeClass(mode)}`}>
                  {mode}
                </span>
              </div>
              <div className="mt-3 flex items-center justify-between gap-2">
                <div className="text-xs text-secondary dark:text-gray-400">
                  {Number(capacity.inflight || 0)}/{Number(capacity.max_inflight || 0)} inflight · {Number(capacity.available_slots || 0)} open
                </div>
                <button
                  type="button"
                  onClick={() => runnerId && void setClaimMode(runnerId, nextMode)}
                  disabled={!runnerId || busyRunnerId === runnerId}
                  className="inline-flex h-8 items-center gap-1 rounded-md border border-default px-2 text-xs font-medium text-primary hover:bg-surface-secondary disabled:opacity-50 dark:border-gray-700 dark:text-gray-100 dark:hover:bg-gray-800"
                >
                  {isDrain ? (
                    <Play className="h-3.5 w-3.5" aria-hidden="true" />
                  ) : (
                    <Pause className="h-3.5 w-3.5" aria-hidden="true" />
                  )}
                  {isDrain ? 'Resume' : 'Drain'}
                </button>
              </div>
            </div>
          );
        })}
        {!sortedRunners.length && !loading ? (
          <div className="rounded-md border border-default p-3 text-sm text-secondary dark:border-gray-700 dark:text-gray-400">
            No active runners.
          </div>
        ) : null}
      </div>
    </Card>
  );
}
