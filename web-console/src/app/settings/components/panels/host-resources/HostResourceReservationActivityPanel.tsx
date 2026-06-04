'use client';

import React from 'react';
import { Bell, History, Route, XCircle } from 'lucide-react';
import { Card } from '../../Card';

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
  };
  candidate_preview?: {
    tasks_scanned?: number;
    selected_candidate?: {
      task_id?: string;
      queue?: string;
      queue_position?: number;
      pack_id?: string;
    } | null;
  } | null;
}

interface HostResourceReservationEvent {
  event_id: string;
  reservation_id?: string;
  event_type?: string;
  occurred_at?: string;
  source?: string;
  lane_id?: string;
}

interface HostResourceNotification {
  notification_id: string;
  message?: string;
}

interface HostResourceConsumer {
  consumer_id: string;
  label?: string;
  pid?: number;
  memory_mb?: number;
  memory_source?: string;
  rss_mb?: number;
}

interface HostResourceReservationActivityPanelProps {
  consumers: HostResourceConsumer[];
  activeReservations: HostResourceReservation[];
  reservationHistory: HostResourceReservation[];
  reservationEvents: HostResourceReservationEvent[];
  notifications: HostResourceNotification[];
  selectedReservationId: string | null;
  setSelectedReservationId: React.Dispatch<React.SetStateAction<string | null>>;
  cancelReservation: (reservationId: string) => Promise<void>;
  actionBusy: string | null;
  loading: boolean;
}

function stateClass(state?: string | null): string {
  if (state === 'available' || state === 'nominal') return 'text-emerald-700 bg-emerald-50 border-emerald-200 dark:text-emerald-300 dark:bg-emerald-950/40 dark:border-emerald-800';
  if (state === 'busy' || state === 'paused') return 'text-amber-700 bg-amber-50 border-amber-200 dark:text-amber-300 dark:bg-amber-950/40 dark:border-amber-800';
  if (state === 'degraded' || state === 'pressure' || state === 'critical') return 'text-red-700 bg-red-50 border-red-200 dark:text-red-300 dark:bg-red-950/40 dark:border-red-800';
  return 'text-gray-700 bg-gray-50 border-gray-200 dark:text-gray-300 dark:bg-gray-900 dark:border-gray-700';
}

function StatePill({ state }: { state?: string | null }) {
  return (
    <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${stateClass(state)}`}>
      {state || 'unknown'}
    </span>
  );
}

const formatMemory = (memoryMb?: number | null): string => {
  if (memoryMb == null) return 'Unknown';
  if (memoryMb >= 1024) return `${(memoryMb / 1024).toFixed(1)} GiB`;
  return `${memoryMb} MB`;
};

export function HostResourceReservationActivityPanel({
  consumers,
  activeReservations,
  reservationHistory,
  reservationEvents,
  notifications,
  selectedReservationId,
  setSelectedReservationId,
  cancelReservation,
  actionBusy,
  loading,
}: HostResourceReservationActivityPanelProps) {
  return (
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
          <Route className="h-4 w-4" aria-hidden="true" />
          Reservations
        </div>
        <div className="divide-y divide-default dark:divide-gray-700">
          <div className="bg-surface-secondary px-4 py-2 text-xs font-semibold uppercase text-secondary dark:bg-gray-900 dark:text-gray-400">
            Active
          </div>
          {activeReservations.slice(0, 5).map((reservation) => {
            const routeRequest = reservation.route_request || {};
            const candidate = reservation.candidate_preview?.selected_candidate || null;
            const active = reservation.state === 'reserved_waiting' || reservation.state === 'permitted';
            const drainActive = active && routeRequest.drain_policy === 'drain_after_current';
            return (
              <div key={reservation.reservation_id} className="px-4 py-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="truncate text-sm font-medium text-primary dark:text-gray-100">
                        {routeRequest.target_lane || reservation.reservation_id}
                      </span>
                      <StatePill state={reservation.state} />
                    </div>
                    <div className="mt-1 text-xs text-secondary dark:text-gray-400">
                      {routeRequest.priority_class || 'default'} · {routeRequest.drain_policy || 'prefer'} · {(routeRequest.resource_groups || []).join(', ') || 'unscoped'}
                    </div>
                    {reservation.candidate_preview ? (
                      <div className="mt-2 rounded-md border border-default bg-surface-secondary px-2 py-1.5 text-xs text-secondary dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300">
                        {candidate ? (
                          <span>
                            Next: {candidate.task_id} · {candidate.pack_id || candidate.queue || 'queue'} · #{(candidate.queue_position ?? 0) + 1}
                          </span>
                        ) : drainActive ? (
                          <span>
                            Drain active · waiting for match · scanned {reservation.candidate_preview.tasks_scanned || 0}
                          </span>
                        ) : (
                          <span>
                            No pending match · scanned {reservation.candidate_preview.tasks_scanned || 0}
                          </span>
                        )}
                      </div>
                    ) : null}
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setSelectedReservationId(reservation.reservation_id)}
                      className="inline-flex h-8 items-center gap-1 rounded-md border border-default px-2 text-xs font-medium text-primary hover:bg-surface dark:border-gray-700 dark:text-gray-100 dark:hover:bg-gray-900"
                    >
                      <History className="h-3.5 w-3.5" aria-hidden="true" />
                      Events
                    </button>
                    {active ? (
                      <button
                        type="button"
                        onClick={() => cancelReservation(reservation.reservation_id)}
                        disabled={actionBusy === `cancel:${reservation.reservation_id}`}
                        className="inline-flex h-8 items-center gap-1 rounded-md border border-default px-2 text-xs font-medium text-primary hover:bg-surface dark:border-gray-700 dark:text-gray-100 dark:hover:bg-gray-900 disabled:opacity-50"
                      >
                        <XCircle className="h-3.5 w-3.5" aria-hidden="true" />
                        Cancel
                      </button>
                    ) : null}
                  </div>
                </div>
              </div>
            );
          })}
          {!activeReservations.length && !loading ? (
            <div className="px-4 py-6 text-sm text-secondary dark:text-gray-400">No active route reservations.</div>
          ) : null}
          <div className="bg-surface-secondary px-4 py-2 text-xs font-semibold uppercase text-secondary dark:bg-gray-900 dark:text-gray-400">
            History
          </div>
          {reservationHistory.slice(0, 5).map((reservation) => {
            const routeRequest = reservation.route_request || {};
            return (
              <div key={reservation.reservation_id} className="px-4 py-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="truncate text-sm font-medium text-primary dark:text-gray-100">
                        {routeRequest.target_lane || reservation.reservation_id}
                      </span>
                      <StatePill state={reservation.state} />
                    </div>
                    <div className="mt-1 text-xs text-secondary dark:text-gray-400">
                      {routeRequest.priority_class || 'default'} · {routeRequest.drain_policy || 'prefer'} · {reservation.cancelled_at || reservation.created_at || '-'}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setSelectedReservationId(reservation.reservation_id)}
                    className="inline-flex h-8 shrink-0 items-center gap-1 rounded-md border border-default px-2 text-xs font-medium text-primary hover:bg-surface dark:border-gray-700 dark:text-gray-100 dark:hover:bg-gray-900"
                  >
                    <History className="h-3.5 w-3.5" aria-hidden="true" />
                    Events
                  </button>
                </div>
              </div>
            );
          })}
          {!reservationHistory.length && !loading ? (
            <div className="px-4 py-6 text-sm text-secondary dark:text-gray-400">No reservation history.</div>
          ) : null}
        </div>
      </Card>

      <Card className="p-0">
        <div className="flex items-center justify-between gap-3 border-b border-default px-4 py-3 dark:border-gray-700">
          <div className="flex min-w-0 items-center gap-2 text-sm font-semibold text-primary dark:text-gray-100">
            <History className="h-4 w-4" aria-hidden="true" />
            <span className="truncate">
              {selectedReservationId ? `Events · ${selectedReservationId}` : 'Reservation Events'}
            </span>
          </div>
          {selectedReservationId ? (
            <button
              type="button"
              onClick={() => setSelectedReservationId(null)}
              className="inline-flex h-8 shrink-0 items-center gap-1 rounded-md border border-default px-2 text-xs font-medium text-primary hover:bg-surface dark:border-gray-700 dark:text-gray-100 dark:hover:bg-gray-900"
            >
              <XCircle className="h-3.5 w-3.5" aria-hidden="true" />
              Clear
            </button>
          ) : null}
        </div>
        <div className="divide-y divide-default dark:divide-gray-700">
          {reservationEvents.slice(0, 5).map((event) => (
            <div key={event.event_id} className="px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <span className="truncate text-sm font-medium text-primary dark:text-gray-100">
                  {event.event_type || event.event_id}
                </span>
                <span className="shrink-0 text-xs text-secondary dark:text-gray-400">
                  {event.occurred_at ? new Date(event.occurred_at).toLocaleTimeString() : '-'}
                </span>
              </div>
              <div className="mt-1 truncate text-xs text-secondary dark:text-gray-400">
                {event.lane_id || event.reservation_id || event.source || 'host-resource-ledger'}
              </div>
            </div>
          ))}
          {!reservationEvents.length && !loading ? (
            <div className="px-4 py-6 text-sm text-secondary dark:text-gray-400">No reservation events.</div>
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
  );
}
