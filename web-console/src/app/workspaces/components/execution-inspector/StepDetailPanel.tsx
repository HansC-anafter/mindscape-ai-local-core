'use client';

import React, { useState, useEffect, useMemo, Suspense } from 'react';
import type {
  ExecutionStep,
  ToolCall,
  StepEvent,
  PlaybookStepDefinition,
  Artifact,
  ReviewBundleArtifact,
  RemoteChildExecution,
  RelatedGovernedMemoryLink,
} from './types/execution';
import { deriveAllSteps } from './utils/execution-inspector';
import { getStepStatusColor, getEffectiveStepStatus } from './utils/execution-inspector';
import { loadCapabilityUIComponent, artifactsMatchComponent } from '@/lib/capability-ui-loader';
import { parseServerTimestamp } from '@/lib/time';
import { GovernedMemoryPreview } from '@/components/workspace/governance/GovernedMemoryPreview';
import ArtifactReviewPane from './ArtifactReviewPane';

export interface StepDetailPanelProps {
  steps: ExecutionStep[];
  playbookStepDefinitions?: PlaybookStepDefinition[];
  totalSteps?: number;
  currentStepIndex: number;
  currentStepToolCalls: ToolCall[];
  stepEvents: StepEvent[];
  executionStatus?: string;
  artifacts?: Artifact[];
  reviewBundleArtifacts?: ReviewBundleArtifact[];
  reviewBundlesLoading?: boolean;
  remoteChildExecutions?: RemoteChildExecution[];
  workspaceId?: string;
  apiUrl?: string;
  relatedGovernedMemory?: RelatedGovernedMemoryLink | null;
  onViewArtifact?: (artifact: Artifact) => void;
  onReviewBundleArtifactUpdated?: (artifact: ReviewBundleArtifact) => void;
  t: (key: string, params?: any) => string;
}

export default function StepDetailPanel({
  steps,
  playbookStepDefinitions,
  totalSteps,
  currentStepIndex,
  currentStepToolCalls,
  stepEvents,
  executionStatus,
  artifacts = [],
  reviewBundleArtifacts = [],
  reviewBundlesLoading = false,
  remoteChildExecutions = [],
  workspaceId,
  apiUrl,
  relatedGovernedMemory,
  onViewArtifact,
  onReviewBundleArtifactUpdated,
  t,
}: StepDetailPanelProps) {
  // Dynamic capability UI components (boundary: no hardcoded Cloud components)
  const [installedCapabilities, setInstalledCapabilities] = useState<any[]>([]);
  const [capabilityUIComponents, setCapabilityUIComponents] = useState<Map<string, React.ComponentType<any>>>(new Map());
  const [openModalKey, setOpenModalKey] = useState<string | null>(null);
  const [selectedReviewBundleId, setSelectedReviewBundleId] = useState<string | null>(null);

  // Load installed capabilities (boundary: via API, not hardcoded)
  useEffect(() => {
    if (apiUrl == null) return;

    const loadCapabilities = async () => {
      try {
        const response = await fetch(`${apiUrl}/api/v1/capability-packs/installed-capabilities`);
        if (response.ok) {
          const capabilities = await response.json();
          setInstalledCapabilities(capabilities);
        }
      } catch (err) {
        console.warn('Failed to load installed capabilities:', err);
      }
    };

    loadCapabilities();
  }, [apiUrl]);

  // Load UI components when artifacts match (boundary: lazy loading)
  useEffect(() => {
    if (apiUrl == null || artifacts.length === 0 || installedCapabilities.length === 0) {
      return;
    }

    for (const capability of installedCapabilities) {
      if (capability.ui_components && capability.ui_components.length > 0) {
        for (const componentInfo of capability.ui_components) {
          // Check if artifacts match this component's criteria (boundary: generic check)
          if (artifactsMatchComponent(artifacts, componentInfo)) {
            const key = `${capability.code}:${componentInfo.code}`;

            // Only load if not already loaded
            setCapabilityUIComponents(prev => {
              if (prev.has(key)) {
                return prev; // Already loaded
              }
              return prev;
            });

            // Load component asynchronously
            loadCapabilityUIComponent(
              capability.code,
              componentInfo.code,
              apiUrl
            ).then(Component => {
              if (Component) {
                setCapabilityUIComponents(prev => {
                  const newMap = new Map(prev);
                  newMap.set(key, Component);
                  return newMap;
                });
              }
            }).catch(err => {
              console.warn(`Failed to load component ${key}:`, err);
            });
          }
        }
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [artifacts.length, installedCapabilities.length, apiUrl]);
  const allSteps = deriveAllSteps({
    playbookStepDefinitions,
    totalSteps,
    steps,
  });

  const executedStepsMap = new Map(steps.map(s => [s.step_index, s]));
  const currentStep = executedStepsMap.get(currentStepIndex) || allSteps.find(s => s.step_index === currentStepIndex)?.executed;
  const currentStepInfo = allSteps.find(s => s.step_index === currentStepIndex);
  const currentStepNameCandidates = [
    currentStepInfo?.step_name,
    currentStep?.step_name,
    currentStep?.id,
  ]
    .filter((value): value is string => typeof value === 'string' && value.trim().length > 0)
    .map((value) => value.trim().toLowerCase());
  const relatedRemoteChildren = remoteChildExecutions.filter((child) => {
    const workflowStepId = child.remote_execution_summary?.workflow_step_id;
    if (!workflowStepId) {
      return remoteChildExecutions.length === 1;
    }
    return currentStepNameCandidates.includes(workflowStepId.trim().toLowerCase());
  });
  const remoteChildrenToShow =
    relatedRemoteChildren.length > 0
      ? relatedRemoteChildren
      : remoteChildExecutions.length === 1
        ? remoteChildExecutions
        : [];
  const selectedReviewBundle = useMemo(
    () =>
      reviewBundleArtifacts.find((artifact) => artifact.id === selectedReviewBundleId)
      || reviewBundleArtifacts[0]
      || null,
    [reviewBundleArtifacts, selectedReviewBundleId],
  );

  useEffect(() => {
    if (!reviewBundleArtifacts.length) {
      setSelectedReviewBundleId(null);
      return;
    }
    if (!selectedReviewBundleId || !reviewBundleArtifacts.some((artifact) => artifact.id === selectedReviewBundleId)) {
      setSelectedReviewBundleId(reviewBundleArtifacts[0].id);
    }
  }, [reviewBundleArtifacts, selectedReviewBundleId]);

  if (!currentStepInfo) {
    return (
      <div className="h-full overflow-y-auto bg-surface-secondary dark:bg-gray-800 p-3 min-w-0">
        <div className="text-center py-8 text-gray-500 dark:text-gray-300">
          {t('selectStepToViewDetails' as any) || 'Select a step to view details'}
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto bg-surface-secondary dark:bg-gray-800 p-3 min-w-0">
      <div className="mb-3 pb-3 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center gap-2 mb-1.5">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            {t('stepNumber', { number: currentStepIndex })}: {currentStepInfo.step_name || t('unnamed' as any)}
          </h3>
          {currentStep && (
            <span
              className={`px-1.5 py-0.5 rounded text-[10px] font-medium border ${getStepStatusColor(currentStep)}`}
            >
              {getEffectiveStepStatus(currentStep, executionStatus)}
            </span>
          )}
        </div>
        {(currentStep?.description || currentStep?.log_summary || currentStepInfo?.description) && (
          <p className="text-xs text-gray-600 dark:text-gray-300 mb-1.5 whitespace-pre-wrap">
            {currentStep?.description || currentStep?.log_summary || currentStepInfo?.description}
          </p>
        )}
        {currentStep?.agent_type && (
          <div className="text-xs text-gray-500 dark:text-gray-300">
            {t('agent' as any)} <span className="font-medium">{currentStep.agent_type}</span>
          </div>
        )}
        {!currentStep && (
          <p className="text-xs text-gray-500 dark:text-gray-400 italic">
            {t('stepNotExecutedYet' as any) || 'This step has not been executed yet.'}
          </p>
        )}
      </div>

      {remoteChildrenToShow.length > 0 && (
        <div className="mb-3">
          <h4 className="text-xs font-medium text-gray-900 dark:text-gray-100 mb-1.5">
            Remote Execution
          </h4>
          <div className="space-y-2">
            {remoteChildrenToShow.map((child) => {
              const summary = child.remote_execution_summary;
              if (!summary) return null;
              return (
                <div
                  key={child.execution_id}
                  className="rounded border border-blue-200 bg-blue-50/60 p-2 text-xs dark:border-blue-800 dark:bg-blue-950/20"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-blue-900 dark:text-blue-200">
                      {summary.tool_name || child.playbook_code || child.execution_id}
                    </span>
                    {summary.target_device_id && (
                      <span className="rounded bg-white/80 px-1.5 py-0.5 text-[10px] text-blue-700 dark:bg-blue-900/40 dark:text-blue-300">
                        VM {summary.target_device_id}
                      </span>
                    )}
                    {summary.is_replay_attempt && (
                      <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
                        replay
                      </span>
                    )}
                    {summary.is_superseded_by_replay && (
                      <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-700 dark:bg-gray-800 dark:text-gray-300">
                        superseded
                      </span>
                    )}
                  </div>
                  <div className="mt-1 space-y-0.5 text-gray-700 dark:text-gray-300">
                    {summary.workflow_step_id && (
                      <div>step: {summary.workflow_step_id}</div>
                    )}
                    <div>status: {child.status}</div>
                    {summary.callback_delivered_at && (
                      <div>callback delivered: {summary.callback_delivered_at}</div>
                    )}
                    {summary.callback_error && (
                      <div>callback error: {summary.callback_error}</div>
                    )}
                    {summary.replay_of_execution_id && (
                      <div>replay of: {summary.replay_of_execution_id}</div>
                    )}
                    {summary.latest_replay_execution_id && (
                      <div>latest replay: {summary.latest_replay_execution_id}</div>
                    )}
                    {summary.lineage_root_execution_id && (
                      <div>lineage root: {summary.lineage_root_execution_id}</div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Event Stream - Only show if there are events */}
      {stepEvents.length > 0 && (
        <div className="mb-3">
          <h4 className="text-xs font-medium text-gray-900 dark:text-gray-100 mb-1.5">
            {t('eventStream' as any)}
          </h4>
          <div className="space-y-1.5">
            {stepEvents.map((event) => (
              <div
                key={event.id}
                className="flex gap-2 p-1.5 bg-surface-accent dark:bg-gray-700 rounded border border-default dark:border-gray-600"
              >
                <div className="flex-shrink-0 text-[10px] text-gray-500 dark:text-gray-300 w-14">
                  {event.timestamp.toLocaleTimeString(undefined, {
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                  })}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-[10px] text-gray-600 dark:text-gray-300">
                    {event.type === 'tool' && event.tool && (
                      <span className="font-medium">
                        {t('tool' as any)} {event.tool}
                      </span>
                    )}
                    {event.type === 'collaboration' && event.agent && (
                      <span className="font-medium">
                        {t('collaboration' as any)} {event.agent}
                      </span>
                    )}
                    {event.type === 'step' && event.agent && (
                      <span className="font-medium">
                        {t('agent' as any)} {event.agent}
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-gray-900 dark:text-gray-100 mt-0.5">
                    {event.content}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tool Calls */}
      {currentStepToolCalls.length > 0 && (
        <div className="mb-4">
          <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
            {t('toolCalls' as any)}
          </h4>
          <div className="space-y-2">
            {currentStepToolCalls.map((toolCall) => (
              <div
                key={toolCall.id}
                className="p-3 bg-surface-accent dark:bg-gray-700 rounded border border-default dark:border-gray-600"
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                    {toolCall.tool_name}
                  </span>
                  <span
                    className={`text-xs px-2 py-0.5 rounded ${toolCall.status === 'completed'
                        ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
                        : toolCall.status === 'failed'
                          ? 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300'
                          : 'bg-accent-10 dark:bg-blue-900/30 text-accent dark:text-blue-300'
                      }`}
                  >
                    {toolCall.status}
                  </span>
                </div>
                {toolCall.started_at && (
                  <div className="text-xs text-gray-500 dark:text-gray-300">
                    {parseServerTimestamp(toolCall.started_at)?.toLocaleTimeString(undefined, {
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit',
                    })}
                    {toolCall.completed_at &&
                      ` - ${parseServerTimestamp(toolCall.completed_at)?.toLocaleTimeString(undefined, {
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit',
                      })}`}
                  </div>
                )}
                {toolCall.error && (
                  <div className="text-xs text-red-600 dark:text-red-400 mt-1">
                    {toolCall.error}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Error */}
      {currentStep?.error && (
        <div className="mt-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-700 rounded">
          <div className="text-sm font-medium text-red-700 dark:text-red-300 mb-1">
            {t('error' as any)}
          </div>
          <div className="text-sm text-red-600 dark:text-red-400">{currentStep?.error}</div>
        </div>
      )}

      {/* Dynamic Capability UI Components (boundary: loaded via API, not hardcoded) */}
      {workspaceId && apiUrl && (() => {
        const matchingComponentKeys: string[] = [];
        for (const capability of installedCapabilities) {
          if (capability.ui_components && capability.ui_components.length > 0) {
            for (const componentInfo of capability.ui_components) {
              if (artifactsMatchComponent(artifacts, componentInfo)) {
                const key = `${capability.code}:${componentInfo.code}`;
                if (capabilityUIComponents.has(key)) {
                  matchingComponentKeys.push(key);
                }
              }
            }
          }
        }

        return matchingComponentKeys.map((key) => {
          const [capabilityCode, componentCode] = key.split(':');
          const Component = capabilityUIComponents.get(key);
          const capability = installedCapabilities.find(c => c.code === capabilityCode);
          const componentInfo = capability?.ui_components?.find((c: any) => c.code === componentCode);
          const isOpen = openModalKey === key;

          if (!Component || !componentInfo) {
            return null;
          }

          return (
            <div key={key} className="mb-3 p-2 border-b border-gray-200 dark:border-gray-700">
              <button
                onClick={() => setOpenModalKey(key)}
                className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-blue-500 hover:bg-blue-600 text-white rounded-lg transition-colors text-sm font-medium"
              >
                <span>{componentInfo.description || `View ${componentInfo.code}`}</span>
              </button>
              {isOpen && (
                <Suspense fallback={<div className="p-4 text-center">Loading...</div>}>
                  <Component
                    isOpen={isOpen}
                    onClose={() => setOpenModalKey(null)}
                    workspaceId={workspaceId}
                  />
                </Suspense>
              )}
            </div>
          );
        });
      })()}

      {/* Artifacts for this step */}
      <div className="mt-4">
        <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
          {t('artifacts' as any) || 'Artifacts'}
        </h4>
        {workspaceId && apiUrl && relatedGovernedMemory?.memoryItemId && (
          <GovernedMemoryPreview
            workspaceId={workspaceId}
            memoryItemId={relatedGovernedMemory.memoryItemId}
            apiUrl={apiUrl}
            lifecycleStatus={relatedGovernedMemory.lifecycleStatus}
            verificationStatus={relatedGovernedMemory.verificationStatus}
            compact
            className="mb-3"
          />
        )}
        {artifacts.length === 0 ? (
          <div className="p-4 rounded border border-dashed border-default dark:border-gray-700 bg-surface-accent dark:bg-gray-800 text-center text-xs text-secondary dark:text-gray-400">
            <div>{t('noArtifacts' as any) || 'This step has not produced artifacts yet'}</div>
          </div>
        ) : (
          <div className="space-y-2">
            {artifacts.map((artifact) => (
              <button
                key={artifact.id}
                onClick={() => onViewArtifact?.(artifact)}
                className="w-full text-left p-3 rounded border border-default dark:border-gray-700 bg-surface-accent dark:bg-gray-800 hover:bg-tertiary dark:hover:bg-gray-700 transition-colors"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                    {artifact.name || artifact.id}
                  </span>
                  <span className="text-[10px] px-2 py-0.5 rounded bg-accent-10 dark:bg-blue-900/30 text-accent dark:text-blue-300">
                    {artifact.type || 'file'}
                  </span>
                </div>
                {artifact.createdAt && (
                  <div className="text-[11px] text-gray-500 dark:text-gray-400 mt-1">
                    {parseServerTimestamp(artifact.createdAt)?.toLocaleTimeString() ?? '—'}
                  </div>
                )}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="mt-4">
        <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
          Visual Acceptance
        </h4>
        {reviewBundlesLoading ? (
          <div className="rounded border border-default bg-surface-accent p-4 text-xs text-gray-500 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300">
            Loading review bundles...
          </div>
        ) : !reviewBundleArtifacts.length ? (
          <div className="rounded border border-dashed border-default bg-surface-accent p-4 text-xs text-gray-500 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300">
            This execution does not have a matching visual acceptance bundle yet.
          </div>
        ) : (
          <div className="space-y-3">
            <div className="grid gap-2 md:grid-cols-2">
              {reviewBundleArtifacts.map((artifact) => {
                const content = artifact.content || {};
                const latestDecision = content.latest_review_decision?.decision || content.status;
                const isSelected = artifact.id === selectedReviewBundle?.id;
                return (
                  <button
                    key={artifact.id}
                    type="button"
                    onClick={() => setSelectedReviewBundleId(artifact.id)}
                    className={`rounded border px-3 py-3 text-left transition ${
                      isSelected
                        ? 'border-blue-300 bg-blue-50 dark:border-blue-700 dark:bg-blue-950/20'
                        : 'border-default bg-surface-accent hover:bg-tertiary dark:border-gray-700 dark:bg-gray-800 dark:hover:bg-gray-700'
                    }`}
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                        {content.scene_id || artifact.name}
                      </span>
                      <span className="rounded-full border border-default px-2 py-0.5 text-[10px] text-gray-600 dark:border-gray-700 dark:text-gray-300">
                        {content.source_kind || 'bundle'}
                      </span>
                    </div>
                    <div className="mt-2 space-y-1 text-[11px] text-gray-500 dark:text-gray-400">
                      <div>run_id={content.run_id || '-'}</div>
                      <div>scene_id={content.scene_id || '-'}</div>
                      <div>decision={latestDecision || '-'}</div>
                    </div>
                  </button>
                );
              })}
            </div>

            <ArtifactReviewPane
              artifact={selectedReviewBundle}
              workspaceId={workspaceId}
              apiUrl={apiUrl}
              onArtifactUpdated={onReviewBundleArtifactUpdated}
            />
          </div>
        )}
      </div>
    </div>
  );
}
