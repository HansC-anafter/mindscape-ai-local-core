'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Activity, Bell, Pause, Play, RefreshCw, Route } from 'lucide-react';
import { settingsApi } from '../../utils/settingsApi';
import { Card } from '../Card';
import { Section } from '../Section';

interface HostResourceLane {
  lane_id: string;
  label?: string;
  kind?: string;
  state?: string;
  requirements?: {
    memory_mb?: number | null;
    memory_source?: string;
    cpu_weight?: number;
    exclusive_groups?: string[];
  };
}

interface HostResourceConsumer {
  consumer_id: string;
  label?: string;
  kind?: string;
  pid?: number;
  memory_mb?: number;
  memory_source?: string;
  rss_mb?: number;
  confidence?: string;
}

interface HostResourceSnapshot {
  captured_at?: string;
  degraded?: boolean;
  degraded_reason?: string;
  host?: {
    os?: string;
    total_memory_bytes?: number | null;
    memory_pressure?: {
      state?: string;
      free_percent?: number | null;
    };
  };
  capacity?: {
    memory_mb?: number;
    reserved_memory_mb?: number;
    cpu_weight_tokens?: number;
  };
  consumers?: HostResourceConsumer[];
  lanes?: HostResourceLane[];
  notifications?: Array<{
    notification_id: string;
    severity?: string;
    message?: string;
    state?: string;
  }>;
}

const formatMemory = (memoryMb?: number | null): string => {
  if (memoryMb == null) return 'Unknown';
  if (memoryMb >= 1024) return `${(memoryMb / 1024).toFixed(1)} GiB`;
  return `${memoryMb} MB`;
};

const stateClass = (state?: string): string => {
  if (state === 'available' || state === 'nominal') return 'text-emerald-700 bg-emerald-50 border-emerald-200 dark:text-emerald-300 dark:bg-emerald-950/40 dark:border-emerald-800';
  if (state === 'busy' || state === 'paused') return 'text-amber-700 bg-amber-50 border-amber-200 dark:text-amber-300 dark:bg-amber-950/40 dark:border-amber-800';
  if (state === 'degraded' || state === 'pressure' || state === 'critical') return 'text-red-700 bg-red-50 border-red-200 dark:text-red-300 dark:bg-red-950/40 dark:border-red-800';
  return 'text-gray-700 bg-gray-50 border-gray-200 dark:text-gray-300 dark:bg-gray-900 dark:border-gray-700';
};

function StatePill({ state }: { state?: string }) {
  return (
    <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${stateClass(state)}`}>
      {state || 'unknown'}
    </span>
  );
}

export function HostResourcesPanel() {
  const [snapshot, setSnapshot] = useState<HostResourceSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState<string | null>(null);

  const loadSnapshot = useCallback(async (refresh = false) => {
    setLoading(true);
    setError(null);
    try {
      const suffix = refresh ? '?refresh=true' : '';
      const data = await settingsApi.get<HostResourceSnapshot>(`/api/v1/host-resources/snapshot${suffix}`);
      setSnapshot(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load host resources');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let mounted = true;
    loadSnapshot();
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible' && mounted) {
        loadSnapshot();
      }
    }, 5000);
    return () => {
      mounted = false;
      window.clearInterval(timer);
    };
  }, [loadSnapshot]);

  const lanes = snapshot?.lanes || [];
  const consumers = snapshot?.consumers || [];
  const notifications = snapshot?.notifications || [];
  const pressureState = snapshot?.host?.memory_pressure?.state || 'unknown';
  const availableMemory = snapshot?.capacity?.memory_mb || 0;
  const reservedMemory = snapshot?.capacity?.reserved_memory_mb || 0;

  const busyCount = useMemo(
    () => lanes.filter((lane) => ['busy', 'paused', 'degraded', 'unknown_requirements'].includes(lane.state || '')).length,
    [lanes]
  );

  const postLaneAction = async (laneId: string, action: 'pause' | 'resume') => {
    setActionBusy(`${action}:${laneId}`);
    try {
      await settingsApi.post(`/api/v1/host-resources/lanes/${encodeURIComponent(laneId)}/${action}`);
      await loadSnapshot(true);
    } finally {
      setActionBusy(null);
    }
  };

  const reserveNextSlot = async (lane: HostResourceLane) => {
    setActionBusy(`reserve:${lane.lane_id}`);
    try {
      await settingsApi.post('/api/v1/host-resources/route-reservations', {
        route_request: {
          target_lane: lane.lane_id,
          resource_groups: lane.requirements?.exclusive_groups || [],
          priority_class: 'interactive_high',
          preemption_policy: 'never',
          drain_policy: 'drain_after_current',
          resume_policy: 'auto_restore_previous',
          requested_by: 'settings_host_resources',
        },
      });
      await loadSnapshot(true);
    } finally {
      setActionBusy(null);
    }
  };

  return (
    <Section
      title="Host Resources"
      headerRight={(
        <button
          type="button"
          onClick={() => loadSnapshot(true)}
          className="inline-flex h-9 items-center gap-2 rounded-md border border-default px-3 text-sm font-medium text-primary hover:bg-surface-secondary dark:border-gray-700 dark:text-gray-100 dark:hover:bg-gray-800"
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          Refresh
        </button>
      )}
    >
      <div className="space-y-4" data-testid="host-resources-panel">
        {error ? (
          <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-300">
            {error}
          </div>
        ) : null}

        <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
          <Card className="p-4">
            <div className="flex items-center gap-2 text-sm font-medium text-secondary dark:text-gray-400">
              <Activity className="h-4 w-4" aria-hidden="true" />
              Pressure
            </div>
            <div className="mt-3 flex items-center justify-between">
              <StatePill state={snapshot?.degraded ? 'degraded' : pressureState} />
              <span className="text-sm text-secondary dark:text-gray-400">{snapshot?.host?.memory_pressure?.free_percent ?? '-'}%</span>
            </div>
          </Card>
          <Card className="p-4">
            <div className="text-sm font-medium text-secondary dark:text-gray-400">Headroom</div>
            <div className="mt-3 text-xl font-semibold text-primary dark:text-gray-100">{formatMemory(availableMemory)}</div>
          </Card>
          <Card className="p-4">
            <div className="text-sm font-medium text-secondary dark:text-gray-400">Reserved</div>
            <div className="mt-3 text-xl font-semibold text-primary dark:text-gray-100">{formatMemory(reservedMemory)}</div>
          </Card>
          <Card className="p-4">
            <div className="text-sm font-medium text-secondary dark:text-gray-400">Lanes</div>
            <div className="mt-3 text-xl font-semibold text-primary dark:text-gray-100">{busyCount}/{lanes.length}</div>
          </Card>
        </div>

        {snapshot?.degraded ? (
          <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
            {snapshot.degraded_reason || 'Host resource probe degraded'}
          </div>
        ) : null}

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <Card className="p-0 xl:col-span-2">
            <div className="border-b border-default px-4 py-3 text-sm font-semibold text-primary dark:border-gray-700 dark:text-gray-100">
              Lanes
            </div>
            <div className="divide-y divide-default dark:divide-gray-700">
              {lanes.map((lane) => (
                <div key={lane.lane_id} className="flex flex-col gap-3 px-4 py-3 md:flex-row md:items-center md:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium text-primary dark:text-gray-100">{lane.label || lane.lane_id}</span>
                      <StatePill state={lane.state} />
                    </div>
                    <div className="mt-1 text-xs text-secondary dark:text-gray-400">
                      {formatMemory(lane.requirements?.memory_mb)} | {lane.requirements?.memory_source || 'unknown'} | {(lane.requirements?.exclusive_groups || []).join(', ') || 'unscoped'}
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <button
                      type="button"
                      onClick={() => reserveNextSlot(lane)}
                      disabled={actionBusy === `reserve:${lane.lane_id}`}
                      className="inline-flex h-8 items-center gap-1 rounded-md border border-default px-2 text-xs font-medium text-primary hover:bg-surface dark:border-gray-700 dark:text-gray-100 dark:hover:bg-gray-900 disabled:opacity-50"
                    >
                      <Route className="h-3.5 w-3.5" aria-hidden="true" />
                      Reserve
                    </button>
                    {lane.state === 'paused' ? (
                      <button
                        type="button"
                        onClick={() => postLaneAction(lane.lane_id, 'resume')}
                        disabled={actionBusy === `resume:${lane.lane_id}`}
                        className="inline-flex h-8 items-center gap-1 rounded-md border border-default px-2 text-xs font-medium text-primary hover:bg-surface dark:border-gray-700 dark:text-gray-100 dark:hover:bg-gray-900 disabled:opacity-50"
                      >
                        <Play className="h-3.5 w-3.5" aria-hidden="true" />
                        Resume
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => postLaneAction(lane.lane_id, 'pause')}
                        disabled={actionBusy === `pause:${lane.lane_id}`}
                        className="inline-flex h-8 items-center gap-1 rounded-md border border-default px-2 text-xs font-medium text-primary hover:bg-surface dark:border-gray-700 dark:text-gray-100 dark:hover:bg-gray-900 disabled:opacity-50"
                      >
                        <Pause className="h-3.5 w-3.5" aria-hidden="true" />
                        Pause
                      </button>
                    )}
                  </div>
                </div>
              ))}
              {!lanes.length && !loading ? (
                <div className="px-4 py-6 text-sm text-secondary dark:text-gray-400">No lanes reported.</div>
              ) : null}
            </div>
          </Card>

          <div className="space-y-4">
            <Card className="p-0">
              <div className="border-b border-default px-4 py-3 text-sm font-semibold text-primary dark:border-gray-700 dark:text-gray-100">
                Consumers
              </div>
              <div className="divide-y divide-default dark:divide-gray-700">
                {consumers.map((consumer) => (
                  <div key={consumer.consumer_id} className="px-4 py-3">
                    <div className="flex items-center justify-between gap-3">
                      <span className="truncate text-sm font-medium text-primary dark:text-gray-100">{consumer.label || consumer.consumer_id}</span>
                      <span className="text-xs text-secondary dark:text-gray-400">PID {consumer.pid || '-'}</span>
                    </div>
                    <div className="mt-1 text-xs text-secondary dark:text-gray-400">
                      {formatMemory(consumer.memory_mb)} | {consumer.memory_source || 'unknown'} | RSS {formatMemory(consumer.rss_mb)}
                    </div>
                  </div>
                ))}
                {!consumers.length && !loading ? (
                  <div className="px-4 py-6 text-sm text-secondary dark:text-gray-400">No active consumers.</div>
                ) : null}
              </div>
            </Card>

            <Card className="p-0">
              <div className="flex items-center gap-2 border-b border-default px-4 py-3 text-sm font-semibold text-primary dark:border-gray-700 dark:text-gray-100">
                <Bell className="h-4 w-4" aria-hidden="true" />
                Notifications
              </div>
              <div className="divide-y divide-default dark:divide-gray-700">
                {notifications.map((notification) => (
                  <div key={notification.notification_id} className="px-4 py-3 text-sm text-secondary dark:text-gray-300">
                    {notification.message || notification.notification_id}
                  </div>
                ))}
                {!notifications.length && !loading ? (
                  <div className="px-4 py-6 text-sm text-secondary dark:text-gray-400">No notifications.</div>
                ) : null}
              </div>
            </Card>
          </div>
        </div>
      </div>
    </Section>
  );
}
