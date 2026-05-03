'use client';

import React, { useEffect, useMemo, useState } from 'react';

import { t } from '@/lib/i18n';
import { useWorkspaceMetadata } from '@/contexts/WorkspaceMetadataContext';
import { useChatModel } from '@/hooks/useChatModel';
import { useWorkspaceExecutorRoute } from '@/hooks/useWorkspaceExecutorRoute';
import { useToast } from '@/components/Toast';

interface AgentInfo {
  id: string;
  name: string;
  description: string;
  status: string;
  version: string;
  risk_level: string;
  transport?: string | null;
  reason?: string | null;
}

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
  const resolvedApiUrl = useMemo(() => resolveApiUrl(apiUrl), [apiUrl]);
  const {
    currentChatModel,
    availableChatModels,
    contextTokenCount,
    executorRuntime,
    setExecutorRuntime,
  } = useWorkspaceMetadata();
  const { showToast, ToastComponent } = useToast();
  const { selectModel } = useChatModel(resolvedApiUrl, { workspaceId });
  const { routeEntries, resolvedRuntime, setPrimaryRuntime, clearPrimaryRuntime } = useWorkspaceExecutorRoute(
    workspaceId,
    resolvedApiUrl,
  );
  const [availableAgents, setAvailableAgents] = useState<AgentInfo[]>([]);
  const [pendingRuntimeSelection, setPendingRuntimeSelection] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const fetchAgents = async () => {
      try {
        const response = await fetch(`${resolvedApiUrl}/api/v1/workspaces/${workspaceId}/agents`);
        if (!response.ok || cancelled) {
          return;
        }
        const data = await response.json();
        if (!cancelled) {
          setAvailableAgents(data.agents || []);
        }
      } catch (err) {
        if (!cancelled) {
          console.error('[WorkspaceChatRuntimeControls] Failed to fetch agents:', err);
        }
      }
    };

    void fetchAgents();
    const interval = window.setInterval(fetchAgents, 30_000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [resolvedApiUrl, workspaceId]);

  useEffect(() => {
    if (pendingRuntimeSelection !== null) {
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
        selectModel(modelName);
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
      ? availableAgents.find((agent) => agent.id === agentId)?.name || agentId
      : 'Mindscape LLM';

    try {
      let success = false;

      success = agentId
        ? await setPrimaryRuntime(agentId)
        : await clearPrimaryRuntime();

      if (!success) {
        setExecutorRuntime(previousAgent);
        setPendingRuntimeSelection(null);
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
      setPendingRuntimeSelection(null);
    } catch (err) {
      console.error('[WorkspaceChatRuntimeControls] Error setting executor:', err);
      setExecutorRuntime(previousAgent);
      setPendingRuntimeSelection(null);
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
  const boundRuntimeIds = new Set(routeEntries);
  const selectedRuntimeId = executorRuntime ?? resolvedRuntime ?? null;
  const selectedAgent =
    availableAgents.find((agent) => agent.id === selectedRuntimeId) || null;
  const selectedRuntimeIsBound = Boolean(
    selectedRuntimeId && (boundRuntimeIds.has(selectedRuntimeId) || resolvedRuntime === selectedRuntimeId),
  );
  const selectedRuntimeStatusLabel = selectedAgent
    ? selectedAgent.status === 'available'
      ? selectedAgent.transport
        ? `${selectedAgent.transport} connected`
        : 'available'
      : selectedRuntimeIsBound
        ? 'workspace-bound, bridge offline'
        : 'unavailable'
    : selectedRuntimeIsBound
      ? 'workspace-bound'
      : 'Mindscape default';

  const getOptionSuffix = (agent: AgentInfo): string => {
    const isBound = boundRuntimeIds.has(agent.id) || resolvedRuntime === agent.id;
    if (agent.status === 'available') {
      return '';
    }
    if (isBound) {
      return ' (bound)';
    }
    return ' (unavailable)';
  };

  const isAgentSelectable = (agent: AgentInfo): boolean => {
    return agent.status === 'available' || boundRuntimeIds.has(agent.id) || resolvedRuntime === agent.id;
  };

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
        {layout === 'panel' ? (
          <div className={statusClassName}>
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                  Active Runtime
                </div>
                <div className="mt-1 text-sm font-semibold leading-5 text-slate-900 dark:text-slate-100">
                  {selectedAgent?.name || (selectedRuntimeId ? selectedRuntimeId : 'Mindscape LLM')}
                </div>
              </div>
              <span
                className={`mt-0.5 inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.14em] ${
                  selectedAgent?.status === 'available'
                    ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300'
                    : selectedRuntimeIsBound
                      ? 'bg-amber-100 text-amber-700 dark:bg-amber-950/30 dark:text-amber-300'
                      : 'bg-slate-200 text-slate-600 dark:bg-slate-800 dark:text-slate-300'
                }`}
              >
                {selectedAgent?.status === 'available'
                  ? 'available'
                  : selectedRuntimeIsBound
                    ? 'bound'
                    : 'offline'}
              </span>
            </div>
            <div className="mt-2 text-[11px] leading-5 text-slate-500 dark:text-slate-400">
              {selectedRuntimeStatusLabel}
              {selectedAgent?.reason ? ` - ${selectedAgent.reason}` : ''}
            </div>
            {currentChatModel ? (
              <div className="mt-2 text-[11px] leading-5 text-slate-600 dark:text-slate-300">
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

        {availableAgents.length > 0 ? (
          layout === 'panel' ? (
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                Runtime
              </div>
              <div className="mt-1.5">
                <select
                  value={selectedRuntimeId || ''}
                  onChange={(event) => {
                    const selectedAgent = event.target.value || null;
                    void handleAgentChange(selectedAgent);
                  }}
                  className={selectClassName}
                  title={t('workspaceSelectAgent') || 'Select Agent'}
                >
                  <option value="">Mindscape LLM</option>
                  {availableAgents.map((agent) => (
                    <option
                      key={agent.id}
                      value={agent.id}
                      disabled={!isAgentSelectable(agent)}
                    >
                      {agent.name}{getOptionSuffix(agent)}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          ) : (
            <select
              value={selectedRuntimeId || ''}
              onChange={(event) => {
                const selectedAgent = event.target.value || null;
                void handleAgentChange(selectedAgent);
              }}
              className={selectClassName}
              title={t('workspaceSelectAgent') || 'Select Agent'}
            >
              <option value="">Mindscape LLM</option>
              {availableAgents.map((agent) => (
                <option
                  key={agent.id}
                  value={agent.id}
                  disabled={!isAgentSelectable(agent)}
                >
                  {agent.name}{getOptionSuffix(agent)}
                </option>
              ))}
            </select>
          )
        ) : null}

        {layout === 'panel' ? (
          <div>
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
          </div>
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
