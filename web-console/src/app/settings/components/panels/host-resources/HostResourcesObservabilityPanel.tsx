'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Activity, Pause, Play, RefreshCw, Route, XCircle } from 'lucide-react';
import { settingsApi } from '../../../utils/settingsApi';
import { Card } from '../../Card';
import { Section } from '../../Section';
import {
  HostResourceLaneManagerPanel,
  type HostResourceLaneManagerLane,
} from './HostResourceLaneManagerPanel';
import { HostResourceReservationActivityPanel } from './HostResourceReservationActivityPanel';

interface HostResourceLane extends HostResourceLaneManagerLane {
  lane_id: string;
  workspace_id?: string | null;
  capability_scope?: string | null;
  label?: string | null;
  kind?: string | null;
  state?: string | null;
  queue_shard?: string | null;
  runner_profile?: string | null;
  resource_class?: string | null;
  priority_class?: string | null;
  resource_flavor?: string | null;
  max_concurrency?: number | null;
  desired_worker_count?: number | null;
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

interface HostResourceReservation {
  reservation_id: string;
  state?: string;
  created_at?: string;
  cancelled_at?: string;
  route_request?: {
    target_lane?: string;
    resource_groups?: string[];
    priority_class?: string;
    drain_policy?: string;
    preemption_policy?: string;
    resume_policy?: string;
    requested_by?: string;
  };
  candidate_preview?: {
    state?: string;
    scan_limit?: number;
    queues_scanned?: number;
    tasks_scanned?: number;
    matching_count?: number;
    selected_candidate?: {
      task_id?: string;
      queue?: string;
      queue_position?: number;
      score?: number;
      pack_id?: string;
      task_type?: string;
    } | null;
  } | null;
}

interface HostResourceReservationEvent {
  event_id: string;
  reservation_id?: string;
  event_type?: string;
  occurred_at?: string;
  source?: string;
  actor?: string;
  lane_id?: string;
  task_id?: string;
}

interface HostResourceRouteIntentPreview {
  route_intent_preview?: {
    target_lane?: string;
    resource_flavor?: string;
    resource_groups?: string[];
    estimated_memory_mb?: number;
    pressure_delta?: {
      headroom_before_mb?: number;
      headroom_after_mb?: number;
    };
    matching_candidates?: Array<{ task_id?: string; pack_id?: string; queue?: string }>;
    preview_errors?: Array<{ source?: string; error?: string }>;
    non_destructive_action_plan?: Array<{ action?: string; target?: string }>;
    reservation_payload?: Record<string, unknown>;
  };
}

const formatMemory = (memoryMb?: number | null): string => {
  if (memoryMb == null) return 'Unknown';
  if (memoryMb >= 1024) return `${(memoryMb / 1024).toFixed(1)} GiB`;
  return `${memoryMb} MB`;
};

const stateClass = (state?: string | null): string => {
  if (state === 'available' || state === 'nominal') return 'text-emerald-700 bg-emerald-50 border-emerald-200 dark:text-emerald-300 dark:bg-emerald-950/40 dark:border-emerald-800';
  if (state === 'busy' || state === 'paused') return 'text-amber-700 bg-amber-50 border-amber-200 dark:text-amber-300 dark:bg-amber-950/40 dark:border-amber-800';
  if (state === 'degraded' || state === 'pressure' || state === 'critical') return 'text-red-700 bg-red-50 border-red-200 dark:text-red-300 dark:bg-red-950/40 dark:border-red-800';
  return 'text-gray-700 bg-gray-50 border-gray-200 dark:text-gray-300 dark:bg-gray-900 dark:border-gray-700';
};

function StatePill({ state }: { state?: string | null }) {
  return (
    <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${stateClass(state)}`}>
      {state || 'unknown'}
    </span>
  );
}

export function HostResourcesObservabilityPanel() {
  const [snapshot, setSnapshot] = useState<HostResourceSnapshot | null>(null);
  const [activeReservations, setActiveReservations] = useState<HostResourceReservation[]>([]);
  const [reservationHistory, setReservationHistory] = useState<HostResourceReservation[]>([]);
  const [reservationEvents, setReservationEvents] = useState<HostResourceReservationEvent[]>([]);
  const [selectedReservationId, setSelectedReservationId] = useState<string | null>(null);
  const [routePreview, setRoutePreview] = useState<HostResourceRouteIntentPreview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState<string | null>(null);

  const loadLiveState = useCallback(async (refresh = false) => {
    setLoading(true);
    setError(null);
    try {
      const suffix = refresh ? '?refresh=true' : '';
      const [data, reservationData] = await Promise.all([
        settingsApi.get<HostResourceSnapshot>(`/api/v1/host-resources/snapshot${suffix}`),
        settingsApi.get<{ reservations?: HostResourceReservation[] }>('/api/v1/host-resources/route-reservations?include_durable=false&state=active&limit=5'),
      ]);
      setSnapshot(data);
      setActiveReservations(Array.isArray(reservationData.reservations) ? reservationData.reservations : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load host resources');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadDurableReservations = useCallback(async () => {
    try {
      const eventQuery = selectedReservationId
        ? `reservation_id=${encodeURIComponent(selectedReservationId)}&limit=10`
        : 'limit=10';
      const [historyData, eventData] = await Promise.all([
        settingsApi.get<{ reservations?: HostResourceReservation[] }>('/api/v1/host-resources/route-reservations?state=history&limit=10'),
        settingsApi.get<{ events?: HostResourceReservationEvent[] }>(`/api/v1/host-resources/route-reservations/events?${eventQuery}`),
      ]);
      setReservationHistory(Array.isArray(historyData.reservations) ? historyData.reservations : []);
      setReservationEvents(Array.isArray(eventData.events) ? eventData.events : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load reservation history');
    }
  }, [selectedReservationId]);

  const refreshAll = useCallback(async (refreshProbe = false) => {
    await Promise.all([
      loadLiveState(refreshProbe),
      loadDurableReservations(),
    ]);
  }, [loadDurableReservations, loadLiveState]);

  useEffect(() => {
    let mounted = true;
    refreshAll();
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible' && mounted) {
        loadLiveState();
      }
    }, 10000);
    return () => {
      mounted = false;
      window.clearInterval(timer);
    };
  }, [loadLiveState, refreshAll]);

  const lanes = useMemo(() => snapshot?.lanes || [], [snapshot]);
  const consumers = useMemo(() => snapshot?.consumers || [], [snapshot]);
  const notifications = useMemo(() => snapshot?.notifications || [], [snapshot]);
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
      await refreshAll(true);
    } finally {
      setActionBusy(null);
    }
  };

  const cancelReservation = async (reservationId: string) => {
    setActionBusy(`cancel:${reservationId}`);
    try {
      await settingsApi.delete(`/api/v1/host-resources/route-reservations/${encodeURIComponent(reservationId)}`);
      await refreshAll(true);
    } finally {
      setActionBusy(null);
    }
  };

  const reserveNextSlot = async (lane: HostResourceLane) => {
    setActionBusy(`reserve:${lane.lane_id}`);
    try {
      const preview = await settingsApi.post<HostResourceRouteIntentPreview>('/api/v1/host-resources/route-intents/preview', {
        target_lane: lane.lane_id,
        resource_groups: lane.requirements?.exclusive_groups || [],
        priority_class: 'interactive_high',
        preemption_policy: 'never',
        drain_policy: 'drain_after_current',
        resume_policy: 'auto_restore_previous',
        requested_by: 'settings_host_resources',
      });
      setRoutePreview(preview);
    } finally {
      setActionBusy(null);
    }
  };

  const confirmRoutePreview = async () => {
    const payload = routePreview?.route_intent_preview?.reservation_payload;
    if (!payload) return;
    setActionBusy('confirm-route-preview');
    try {
      await settingsApi.post('/api/v1/host-resources/route-reservations', payload);
      setRoutePreview(null);
      await refreshAll(true);
    } finally {
      setActionBusy(null);
    }
  };

  return (
    <Section
      title="Host Resource Observability"
      headerRight={(
        <button
          type="button"
          onClick={() => refreshAll(true)}
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

        {routePreview?.route_intent_preview ? (
          <Card className="p-4">
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <Route className="h-4 w-4 text-secondary dark:text-gray-400" aria-hidden="true" />
                  <span className="font-medium text-primary dark:text-gray-100">
                    {routePreview.route_intent_preview.target_lane || 'Route preview'}
                  </span>
                  <StatePill state="preview" />
                </div>
                <div className="mt-1 text-xs text-secondary dark:text-gray-400">
                  {formatMemory(routePreview.route_intent_preview.estimated_memory_mb)} | after {formatMemory(routePreview.route_intent_preview.pressure_delta?.headroom_after_mb)} | {(routePreview.route_intent_preview.resource_groups || []).join(', ') || 'unscoped'}
                </div>
                {(routePreview.route_intent_preview.preview_errors || []).length > 0 ? (
                  <div className="mt-1 text-xs text-amber-700 dark:text-amber-300">
                    Candidate scan unavailable
                  </div>
                ) : null}
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <button
                  type="button"
                  onClick={() => setRoutePreview(null)}
                  className="inline-flex h-8 items-center gap-1 rounded-md border border-default px-2 text-xs font-medium text-primary hover:bg-surface dark:border-gray-700 dark:text-gray-100 dark:hover:bg-gray-900"
                >
                  <XCircle className="h-3.5 w-3.5" aria-hidden="true" />
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={confirmRoutePreview}
                  disabled={actionBusy === 'confirm-route-preview' || !routePreview.route_intent_preview.reservation_payload}
                  className="inline-flex h-8 items-center gap-1 rounded-md border border-default px-2 text-xs font-medium text-primary hover:bg-surface dark:border-gray-700 dark:text-gray-100 dark:hover:bg-gray-900 disabled:opacity-50"
                >
                  <Route className="h-3.5 w-3.5" aria-hidden="true" />
                  Reserve
                </button>
              </div>
            </div>
          </Card>
        ) : null}

        <HostResourceLaneManagerPanel
          lanes={lanes}
          onRefresh={() => refreshAll(true)}
        />

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

          <HostResourceReservationActivityPanel
            consumers={consumers}
            activeReservations={activeReservations}
            reservationHistory={reservationHistory}
            reservationEvents={reservationEvents}
            notifications={notifications}
            selectedReservationId={selectedReservationId}
            setSelectedReservationId={setSelectedReservationId}
            cancelReservation={cancelReservation}
            actionBusy={actionBusy}
            loading={loading}
          />
        </div>
      </div>
    </Section>
  );
}
