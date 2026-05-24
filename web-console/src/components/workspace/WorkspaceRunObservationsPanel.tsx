'use client';

import React, { useEffect, useMemo, useState } from 'react';

import { RunnerTaskCard } from '@/components/runner/RunnerTaskCard';
import {
  fetchRunObservationEvents,
  type RunObservationCard,
  type RunObservationEvent,
  type RunObservationPayload,
} from '@/lib/workspace-runs/run-observations-api';
import { useRunObservationsSummary } from '@/lib/workspace-runs/useRunObservationsSummary';
import type { UseRunObservationsSummaryResult } from '@/lib/workspace-runs/useRunObservationsSummary';

interface WorkspaceRunObservationsPanelProps {
  apiUrl: string;
  workspaceId: string;
  summaryState?: UseRunObservationsSummaryResult;
  compact?: boolean;
  showEmptyState?: boolean;
}

function buildProgress(payload: RunObservationPayload | undefined) {
  if (!payload) return null;
  if (payload.progress) return payload.progress;
  if (typeof payload.stage_total !== 'number') return null;
  const stageIndex = typeof payload.stage_index === 'number' ? payload.stage_index : 1;
  return {
    current_step_index: Math.max(0, stageIndex - 1),
    total_steps: payload.stage_total,
    current_step_name: String(payload.stage_code || payload.stage || 'Stage'),
  };
}

function formatElapsed(seconds: unknown): string | null {
  if (typeof seconds !== 'number' || !Number.isFinite(seconds)) return null;
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  const remaining = Math.round(seconds % 60);
  return `${minutes}m ${remaining}s`;
}

function stopReasonLabel(stopReason: unknown): string | null {
  const value = String(stopReason || '').trim();
  if (!value) return null;
  if (value === 'operator_interrupt') return 'Stopped by operator';
  if (value === 'operator_pause') return 'Paused by operator';
  return value;
}

function ObservationFields({ card }: { card: RunObservationCard }) {
  const payload = card.payload || {};
  const elapsed = formatElapsed(payload.elapsed_seconds);
  const stopReason = stopReasonLabel(payload.stop_reason);
  return (
    <div className="space-y-1 text-[10px] leading-snug text-gray-500 dark:text-gray-400">
      {card.summary ? <div className="text-gray-700 dark:text-gray-300">{card.summary}</div> : null}
      <div className="grid grid-cols-2 gap-x-2 gap-y-1">
        {payload.stage_code || payload.stage ? (
          <span className="min-w-0 truncate">Stage: {String(payload.stage_code || payload.stage)}</span>
        ) : null}
        {payload.prompt_id ? (
          <span className="min-w-0 truncate">Prompt: {String(payload.prompt_id)}</span>
        ) : null}
        {elapsed ? <span>Elapsed: {elapsed}</span> : null}
        {typeof payload.queue_running === 'number' || typeof payload.queue_pending === 'number' ? (
          <span>Queue: {Number(payload.queue_running || 0)}/{Number(payload.queue_pending || 0)}</span>
        ) : null}
      </div>
      {stopReason ? <div>{stopReason}</div> : null}
    </div>
  );
}

function EventsList({ events }: { events: RunObservationEvent[] }) {
  return (
    <div className="space-y-1 border-l border-gray-200 pl-2 dark:border-gray-800">
      {events.map((event) => (
        <div key={event.feed_id} className="text-[10px] leading-snug text-gray-500 dark:text-gray-400">
          <span className="font-mono text-gray-700 dark:text-gray-300">{event.status}</span>
          {event.payload?.stage_code ? <span> · {String(event.payload.stage_code)}</span> : null}
          {event.payload?.stop_reason ? <span> · {stopReasonLabel(event.payload.stop_reason)}</span> : null}
        </div>
      ))}
    </div>
  );
}

export default function WorkspaceRunObservationsPanel({
  apiUrl,
  workspaceId,
  summaryState,
  compact = false,
  showEmptyState = true,
}: WorkspaceRunObservationsPanelProps) {
  const localSummaryState = useRunObservationsSummary({
    apiUrl,
    workspaceId,
    activeOnly: true,
    limit: 20,
    enabled: !summaryState,
  });
  const { summary, isLoading, error } = summaryState || localSummaryState;
  const cards = summary?.cards || [];
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [eventsByRun, setEventsByRun] = useState<Record<string, RunObservationEvent[]>>({});
  const selectedCard = useMemo(
    () => cards.find((card) => card.run_id === selectedRunId) || null,
    [cards, selectedRunId],
  );
  const sectionClassName = compact
    ? 'space-y-2 border-b border-gray-200 p-2 dark:border-gray-800'
    : 'space-y-2';

  useEffect(() => {
    if (!selectedCard || eventsByRun[selectedCard.run_id]) return undefined;
    let cancelled = false;
    void fetchRunObservationEvents({
      apiUrl,
      workspaceId,
      runId: selectedCard.run_id,
      limit: 50,
    })
      .then((response) => {
        if (!cancelled) {
          setEventsByRun((current) => ({
            ...current,
            [selectedCard.run_id]: response.events,
          }));
        }
      })
      .catch(() => {
        if (!cancelled) {
          setEventsByRun((current) => ({
            ...current,
            [selectedCard.run_id]: [],
          }));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [apiUrl, eventsByRun, selectedCard, workspaceId]);

  if (isLoading && cards.length === 0) {
    if (!showEmptyState) return null;
    return (
      <section className={sectionClassName} data-testid="workspace-run-observations-panel">
        <div className="text-xs text-gray-500 dark:text-gray-400">Loading external runs...</div>
      </section>
    );
  }

  if (error && cards.length === 0) {
    if (!showEmptyState) return null;
    return (
      <section className={sectionClassName} data-testid="workspace-run-observations-panel">
        <div className="rounded border border-red-200 bg-red-50 p-2 text-xs text-red-700 dark:border-red-800/50 dark:bg-red-900/10 dark:text-red-300">
          {error}
        </div>
      </section>
    );
  }

  if (cards.length === 0) {
    if (!showEmptyState) return null;
    return (
      <section className={sectionClassName} data-testid="workspace-run-observations-panel">
        <div className="rounded border border-gray-200 bg-gray-50 p-3 text-xs text-gray-500 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-400">
          No external runs.
        </div>
      </section>
    );
  }

  return (
    <section className={sectionClassName} data-testid="workspace-run-observations-panel">
      {cards.map((card) => {
        const isSelected = selectedRunId === card.run_id;
        const events = eventsByRun[card.run_id] || [];
        return (
          <div key={card.run_id} className="space-y-2">
            <button
              type="button"
              className="block w-full text-left"
              data-testid={`run-observation-card-${card.run_id}`}
              onClick={() => setSelectedRunId((current) => (current === card.run_id ? null : card.run_id))}
            >
              <RunnerTaskCard
                status={card.status}
                playbookCode={card.provider_code || 'external_runner'}
                title={card.display_title || card.provider_code || card.run_id}
                heartbeatAt={card.heartbeat_at || card.updated_at}
                progress={buildProgress(card.payload)}
                executionId={card.execution_id || card.run_id}
                error={card.status === 'failed' ? card.summary || null : null}
                createdAt={card.created_at || card.started_at}
                extensionSlot={<ObservationFields card={card} />}
              />
            </button>
            {isSelected ? <EventsList events={events} /> : null}
          </div>
        );
      })}
    </section>
  );
}
