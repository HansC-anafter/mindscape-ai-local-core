'use client';

import React, { useEffect, useMemo, useState } from 'react';

import { useT } from '@/lib/i18n';
import { useWorkspaceMetadata } from '@/contexts/WorkspaceMetadataContext';
import { useWorkspaceExecutorRoute } from '@/hooks/useWorkspaceExecutorRoute';
import { useWorkspaceAgentsSnapshot } from '@/hooks/useWorkspaceAgentsSnapshot';
import { useToast } from '@/components/Toast';
import { WorkspaceExecutorRuntimeSelector } from './WorkspaceExecutorRuntimeSelector';

interface WorkspaceChatRuntimeControlsProps {
  workspaceId: string;
  apiUrl: string;
  layout?: 'inline' | 'panel';
}

function resolveApiUrl(apiUrl: string): string {
  if (apiUrl) {
    return apiUrl;
  }

  if (typeof window !== 'undefined') {
    return window.location.origin.replace(':3000', ':8220');
  }

  return '';
}

export function WorkspaceChatRuntimeControls({
  workspaceId,
  apiUrl,
  layout = 'inline',
}: WorkspaceChatRuntimeControlsProps) {
  const t = useT();
  const resolvedApiUrl = useMemo(() => resolveApiUrl(apiUrl), [apiUrl]);
  const {
    currentChatModel,
    availableChatModels,
    contextTokenCount,
    executorRuntime,
    setExecutorRuntime,
    setCurrentChatModel,
  } = useWorkspaceMetadata();
  const { showToast, ToastComponent } = useToast();
  const { routeEntries, resolvedRuntime, setPrimaryRuntime, clearPrimaryRuntime } = useWorkspaceExecutorRoute(
    workspaceId,
    resolvedApiUrl,
  );
  const agentsSnapshot = useWorkspaceAgentsSnapshot(workspaceId, resolvedApiUrl);
  const [pendingRuntimeSelection, setPendingRuntimeSelection] = useState<string | null | undefined>(undefined);

  useEffect(() => {
    if (pendingRuntimeSelection !== undefined) {
      return;
    }

    if (executorRuntime !== resolvedRuntime) {
      setExecutorRuntime(resolvedRuntime);
    }
  }, [executorRuntime, pendingRuntimeSelection, resolvedRuntime, setExecutorRuntime]);

  const handleModelChange = async (modelName: string, provider: string) => {
    try {
      const response = await fetch(
        `${resolvedApiUrl}/api/v1/settings/model-route-registry/local-core/chat-default?model_name=${encodeURIComponent(modelName)}&provider=${encodeURIComponent(provider)}`,
        { method: 'PUT', headers: { 'Content-Type': 'application/json' } },
      );
      if (response.ok) {
        setCurrentChatModel(modelName);
      }
    } catch (err) {
      console.error('[WorkspaceChatRuntimeControls] Failed to update chat model:', err);
    }
  };

  const handleAgentChange = async (agentId: string | null) => {
    const previousAgent = executorRuntime;
    setPendingRuntimeSelection(agentId);
    setExecutorRuntime(agentId);

    const agentDisplayName = agentId
      ? agentsSnapshot.agents.find((agent) => agent.id === agentId)?.name || agentId
      : 'Mindscape LLM';

    try {
      let success = false;

      success = agentId
        ? await setPrimaryRuntime(agentId)
        : await clearPrimaryRuntime();

      if (!success) {
        setExecutorRuntime(previousAgent);
        setPendingRuntimeSelection(undefined);
        showToast({
          type: 'error',
          message: `Failed to switch executor to ${agentDisplayName}`,
          duration: 3000,
        });
        return;
      }

      showToast({
        type: 'success',
        message: agentId
          ? `Executor switched to ${agentDisplayName}`
          : 'Switched back to Mindscape LLM',
        duration: 3000,
      });
      await agentsSnapshot.refresh();
      setPendingRuntimeSelection(undefined);
    } catch (err) {
      console.error('[WorkspaceChatRuntimeControls] Error setting executor:', err);
      setExecutorRuntime(previousAgent);
      setPendingRuntimeSelection(undefined);
      showToast({
        type: 'error',
        message: 'Failed to switch executor: network error',
        duration: 3000,
      });
    }
  };

  const baseSelectClassName =
    'rounded-[16px] border border-[#c7af7d] bg-white/95 text-slate-900 shadow-[0_6px_14px_rgba(166,139,94,0.10)] outline-none transition focus:border-[#9b7a3a] focus:ring-2 focus:ring-[#d3b57a]/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:focus:border-slate-500 dark:focus:ring-slate-700';
  const selectClassName =
    layout === 'panel'
      ? `${baseSelectClassName} w-full px-3 py-2.5 text-xs`
      : `${baseSelectClassName} max-w-full px-2 py-1 text-xs`;
  const statusClassName = layout === 'panel'
    ? 'rounded-[18px] border border-slate-200 bg-slate-50/90 px-3 py-3 text-xs text-slate-600 dark:border-slate-800 dark:bg-slate-900/70 dark:text-slate-300'
    : 'flex items-center gap-2 text-xs text-gray-500 dark:text-gray-300';
  const selectedRuntimeId = pendingRuntimeSelection !== undefined
    ? pendingRuntimeSelection
    : executorRuntime ?? resolvedRuntime ?? null;

  return (
    <>
      <div
        className={
          layout === 'panel'
            ? 'space-y-3'
            : 'flex min-w-0 flex-wrap items-center gap-2'
        }
        data-testid={
          layout === 'panel'
            ? 'workspace-chat-runtime-controls-panel'
            : 'workspace-chat-runtime-controls-inline'
        }
      >
        {layout !== 'panel' ? (
          <select
            value={currentChatModel || ''}
            onChange={async (event) => {
              const selectedModel = event.target.value;
              const model = availableChatModels.find((entry) => entry.model_name === selectedModel);
              if (model) {
                await handleModelChange(model.model_name, model.provider);
              }
            }}
            className={selectClassName}
            title={t('workspaceSelectChatModel')}
          >
            {availableChatModels.length > 0 ? (
              availableChatModels.map((model) => (
                <option key={model.model_name} value={model.model_name}>
                  {model.model_name}
                </option>
              ))
            ) : (
              <option value="">No models available</option>
            )}
          </select>
        ) : null}

        <WorkspaceExecutorRuntimeSelector
          agents={agentsSnapshot.agents}
          routeEntries={routeEntries}
          resolvedRuntime={resolvedRuntime}
          selectedRuntimeId={selectedRuntimeId}
          disabled={pendingRuntimeSelection !== undefined}
          onSelect={(runtimeId) => void handleAgentChange(runtimeId)}
          layout={layout}
        />

        {layout === 'panel' ? (
          <>
            {currentChatModel || contextTokenCount !== null ? (
              <div className={statusClassName}>
                {currentChatModel ? (
                  <div className="text-[11px] leading-5 text-slate-600 dark:text-slate-300">
                    Model: <span className="font-semibold text-slate-900 dark:text-slate-100">{currentChatModel}</span>
                  </div>
                ) : null}
                {contextTokenCount !== null ? (
                  <div className="mt-1 text-[11px] leading-5 text-slate-500 dark:text-slate-400">
                    {contextTokenCount >= 1000
                      ? `${(contextTokenCount / 1000).toFixed(1)}k`
                      : contextTokenCount.toLocaleString()}{' '}
                    tokens
                  </div>
                ) : null}
              </div>
            ) : null}
            <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
              Model
            </div>
            <div className="mt-1.5">
              <select
                value={currentChatModel || ''}
                onChange={async (event) => {
                  const selectedModel = event.target.value;
                  const model = availableChatModels.find(
                    (entry) => entry.model_name === selectedModel,
                  );
                  if (model) {
                    await handleModelChange(model.model_name, model.provider);
                  }
                }}
                className={selectClassName}
                title={t('workspaceSelectChatModel')}
              >
                {availableChatModels.length > 0 ? (
                  availableChatModels.map((model) => (
                    <option key={model.model_name} value={model.model_name}>
                      {model.model_name}
                    </option>
                  ))
                ) : (
                  <option value="">No models available</option>
                )}
              </select>
            </div>
          </>
        ) : (
          <div className={statusClassName}>
            <>
              {currentChatModel ? (
                <span className="truncate">
                  Model: {currentChatModel}
                </span>
              ) : null}
              {contextTokenCount !== null ? (
                <span title="Context tokens">
                  {contextTokenCount >= 1000
                    ? `${(contextTokenCount / 1000).toFixed(1)}k`
                    : contextTokenCount.toLocaleString()}{' '}
                  tokens
                </span>
              ) : null}
            </>
          </div>
        )}
      </div>
      <ToastComponent />
    </>
  );
}
