'use client';

import React from 'react';

import { RunnerTaskCard } from '@/components/runner/RunnerTaskCard';
import { useWorkspaceDataOptional } from '@/contexts/WorkspaceDataContext';
import {
  type RunObservationCard,
  type RunObservationPayload,
} from '@/lib/workspace-runs/run-observations-api';
import { useRunObservationsSummary } from '@/lib/workspace-runs/useRunObservationsSummary';
import type { UseRunObservationsSummaryResult } from '@/lib/workspace-runs/useRunObservationsSummary';

interface WorkspacePausedRunsPanelProps {
  apiUrl: string;
  workspaceId: string;
  summaryState?: UseRunObservationsSummaryResult;
}

function isPaused(status: unknown): boolean {
  return String(status || '').trim().toLowerCase() === 'paused';
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

function stopReasonLabel(stopReason: unknown): string | null {
  const value = String(stopReason || '').trim();
  if (!value) return null;
  if (value === 'operator_interrupt') return 'Stopped by operator';
  if (value === 'operator_pause') return 'Paused by operator';
  return value;
}

function ExternalPausedFields({ card }: { card: RunObservationCard }) {
  const payload = card.payload || {};
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
      </div>
      {stopReason ? <div>{stopReason}</div> : null}
    </div>
  );
}

function WorkspaceExecutionFields({ execution }: { execution: Record<string, any> }) {
  const pausedAt = execution.paused_at || execution.updated_at || null;
  return (
    <div className="space-y-1 text-[10px] leading-snug text-gray-500 dark:text-gray-400">
      {pausedAt ? <div>Paused at: {String(pausedAt)}</div> : null}
      {execution.origin_intent_label ? <div>{String(execution.origin_intent_label)}</div> : null}
    </div>
  );
}

export default function WorkspacePausedRunsPanel({
  apiUrl,
  workspaceId,
  summaryState,
}: WorkspacePausedRunsPanelProps) {
  const workspaceData = useWorkspaceDataOptional();
  const workspacePausedExecutions = (workspaceData?.executions || []).filter((execution) =>
    isPaused(execution.status),
  );
  const localSummaryState = useRunObservationsSummary({
    apiUrl,
    workspaceId,
    activeOnly: true,
    limit: 50,
    enabled: !summaryState,
  });
  const { summary, isLoading, error } = summaryState || localSummaryState;
  const externalPausedCards = (summary?.cards || []).filter((card) => isPaused(card.status));
  const totalPaused = workspacePausedExecutions.length + externalPausedCards.length;

  return (
    <section className="space-y-3" data-testid="workspace-paused-runs-panel">
      <div className="flex items-center justify-between gap-3">
        <div className="text-xs font-semibold uppercase tracking-normal text-gray-500 dark:text-gray-400">
          Workspace Paused Runs
        </div>
        <div className="shrink-0 rounded border border-orange-200 bg-orange-50 px-2 py-1 text-xs font-bold text-orange-700 dark:border-orange-800/50 dark:bg-orange-900/20 dark:text-orange-300">
          {totalPaused}
        </div>
      </div>

      {error && externalPausedCards.length === 0 ? (
        <div className="rounded border border-red-200 bg-red-50 p-2 text-xs text-red-700 dark:border-red-800/50 dark:bg-red-900/10 dark:text-red-300">
          {error}
        </div>
      ) : null}

      {isLoading && totalPaused === 0 ? (
        <div className="text-xs text-gray-500 dark:text-gray-400">Loading paused runs...</div>
      ) : null}

      {!isLoading && totalPaused === 0 ? (
        <div className="rounded border border-gray-200 bg-gray-50 p-3 text-xs text-gray-500 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-400">
          No paused workspace runs.
        </div>
      ) : null}

      {externalPausedCards.length > 0 ? (
        <div className="space-y-2">
          <div className="text-[10px] font-semibold uppercase tracking-normal text-gray-400 dark:text-gray-500">
            External Runners
          </div>
          {externalPausedCards.map((card) => (
            <RunnerTaskCard
              key={card.run_id}
              status={card.status}
              playbookCode={card.provider_code || 'external_runner'}
              title={card.display_title || card.provider_code || card.run_id}
              heartbeatAt={card.heartbeat_at || card.updated_at}
              progress={buildProgress(card.payload)}
              executionId={card.execution_id || card.run_id}
              createdAt={card.created_at || card.started_at}
              extensionSlot={<ExternalPausedFields card={card} />}
            />
          ))}
        </div>
      ) : null}

      {workspacePausedExecutions.length > 0 ? (
        <div className="space-y-2">
          <div className="text-[10px] font-semibold uppercase tracking-normal text-gray-400 dark:text-gray-500">
            Workspace Executions
          </div>
          {workspacePausedExecutions.map((execution) => {
            const executionId = execution.execution_id || execution.id;
            return (
              <RunnerTaskCard
                key={executionId}
                status={execution.status}
                playbookCode={execution.playbook_code}
                title={execution.playbook_code || executionId}
                progress={{
                  current_step_index: execution.current_step_index,
                  total_steps: execution.total_steps,
                }}
                executionId={executionId}
                createdAt={execution.created_at || execution.started_at}
                extensionSlot={<WorkspaceExecutionFields execution={execution} />}
              />
            );
          })}
        </div>
      ) : null}
    </section>
  );
}
