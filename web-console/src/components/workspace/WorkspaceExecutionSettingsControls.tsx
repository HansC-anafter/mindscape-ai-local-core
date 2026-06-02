'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Bot, ExternalLink, RefreshCw, SlidersHorizontal } from 'lucide-react';

import { useWorkspaceDataOptional } from '@/contexts/WorkspaceDataContext';
import { useWorkspaceExecutorRoute } from '@/hooks/useWorkspaceExecutorRoute';
import { useWorkspaceAgentsSnapshot } from '@/hooks/useWorkspaceAgentsSnapshot';
import { isDocumentHidden, onDocumentVisible } from '@/lib/page-visibility';
import { sharedGetFetch } from '@/lib/resilient-fetch';
import { openAppRouteInNewWindow } from '@/lib/navigation/openAppRouteInNewWindow';
import { WorkspaceExecutorRuntimeSelector } from './WorkspaceExecutorRuntimeSelector';
import { WorkspaceRuntimeCliFloatingPanel } from './WorkspaceRuntimeCliFloatingPanel';
import { WorkspaceRuntimeProfileFloatingPanel } from './WorkspaceRuntimeProfileFloatingPanel';

interface ChatModelOption {
  model_name: string;
  provider: string;
  description?: string;
}

interface WorkspaceChatRoutePayload {
  chat_model?: {
    model_name: string;
    provider: string;
    metadata?: Record<string, any>;
  } | null;
  available_chat_models?: ChatModelOption[];
  route_authority?: string;
  source?: string;
  dispatch_chain?: string[];
}

interface WorkspaceExecutionSettingsControlsProps {
  workspaceId: string;
  apiUrl: string;
}

function modelOptionKey(model: ChatModelOption): string {
  return `${model.provider}:${model.model_name}`;
}

function workspaceSettingsUrl(
  workspaceId: string,
  params: Record<string, string>,
): string {
  const searchParams = new URLSearchParams({
    ...params,
    workspace_id: workspaceId,
  });
  return `/settings?${searchParams.toString()}`;
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block space-y-1 text-xs font-semibold uppercase tracking-[0.08em] text-gray-500 dark:text-gray-400">
      <span>{label}</span>
      {children}
    </label>
  );
}

function ActionButton({
  icon,
  label,
  detail,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  detail: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className="flex w-full items-center gap-3 rounded border border-gray-200 px-3 py-2 text-left hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-900"
      onClick={onClick}
    >
      <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-200">
        {icon}
      </span>
      <span className="min-w-0">
        <span className="block text-sm font-semibold leading-5 text-gray-900 dark:text-gray-100">
          {label}
        </span>
        <span className="block text-xs leading-5 text-gray-500 dark:text-gray-400">
          {detail}
        </span>
      </span>
    </button>
  );
}

export function WorkspaceExecutionSettingsControls({
  workspaceId,
  apiUrl,
}: WorkspaceExecutionSettingsControlsProps) {
  const workspaceData = useWorkspaceDataOptional();
  const [chatRoute, setChatRoute] = useState<WorkspaceChatRoutePayload | null>(null);
  const [chatLoading, setChatLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [pendingRuntimeSelection, setPendingRuntimeSelection] = useState<string | null | undefined>(undefined);
  const [runtimeCliOpen, setRuntimeCliOpen] = useState(false);
  const [runtimeProfileOpen, setRuntimeProfileOpen] = useState(false);
  const {
    routeEntries,
    resolvedRuntime,
    loading: executorLoading,
    error: executorError,
    setPrimaryRuntime,
    clearPrimaryRuntime,
  } = useWorkspaceExecutorRoute(workspaceId, apiUrl);
  const agentsSnapshot = useWorkspaceAgentsSnapshot(workspaceId, apiUrl);

  const loadChatRoute = useCallback(async () => {
    if (isDocumentHidden()) {
      return;
    }

    setChatLoading(true);
    setMessage(null);
    try {
      const response = await sharedGetFetch(
        `${apiUrl}/api/v1/settings/model-route-registry/workspace-chat?workspace_id=${encodeURIComponent(workspaceId)}&profile_id=default-user`,
        { method: 'GET' },
        { dedupKey: `workspace-chat-route:${workspaceId}` },
      );
      if (!response.ok) {
        throw new Error(`Execution snapshot failed: ${response.status}`);
      }
      setChatRoute(await response.json());
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Execution snapshot failed');
    } finally {
      setChatLoading(false);
    }
  }, [apiUrl, workspaceId]);

  useEffect(() => {
    void loadChatRoute();
    return onDocumentVisible(() => {
      void loadChatRoute();
    });
  }, [loadChatRoute]);

  const currentChatModel = chatRoute?.chat_model || null;
  const selectedModelKey = currentChatModel ? modelOptionKey(currentChatModel) : '';
  const selectedRuntimeId = pendingRuntimeSelection !== undefined
    ? pendingRuntimeSelection
    : resolvedRuntime;
  const loading = chatLoading || executorLoading || agentsSnapshot.loading;
  const routeMessage = message || executorError || agentsSnapshot.error;

  const updateChatModel = async (selectedKey: string) => {
    const selected = (chatRoute?.available_chat_models || []).find(
      (model) => modelOptionKey(model) === selectedKey,
    );
    if (!selected) {
      return;
    }

    setSaving(true);
    setMessage(null);
    try {
      const response = await fetch(
        `${apiUrl}/api/v1/settings/model-route-registry/local-core/chat-default?model_name=${encodeURIComponent(selected.model_name)}&provider=${encodeURIComponent(selected.provider)}`,
        { method: 'PUT', headers: { 'Content-Type': 'application/json' } },
      );
      if (!response.ok) {
        throw new Error(`Chat model update failed: ${response.status}`);
      }
      setChatRoute(await response.json());
      setMessage('Chat model saved');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Chat model update failed');
    } finally {
      setSaving(false);
    }
  };

  const updateExecutor = async (runtimeId: string | null) => {
    setSaving(true);
    setMessage(null);
    setPendingRuntimeSelection(runtimeId);

    try {
      const success = runtimeId
        ? await setPrimaryRuntime(runtimeId)
        : await clearPrimaryRuntime();
      if (!success) {
        throw new Error(runtimeId ? 'Executor update failed' : 'Executor reset failed');
      }
      await agentsSnapshot.refresh();
      setMessage(runtimeId ? 'Executor saved' : 'Executor reset to Mindscape LLM');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Executor update failed');
    } finally {
      setPendingRuntimeSelection(undefined);
      setSaving(false);
    }
  };

  const testChatModel = async () => {
    setTesting(true);
    setMessage(null);
    try {
      const response = await fetch(`${apiUrl}/api/v1/system-settings/llm-models/test-chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(data?.message || `Chat model test failed: ${response.status}`);
      }
      setMessage(data?.message || 'Chat model test completed');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Chat model test failed');
    } finally {
      setTesting(false);
    }
  };

  const llmSettingsUrl = useMemo(
    () => workspaceSettingsUrl(workspaceId, { tab: 'basic', section: 'llm-chat' }),
    [workspaceId],
  );
  const routingUrl = useMemo(
    () => workspaceSettingsUrl(workspaceId, {
      tab: 'basic',
      section: 'model-routing-registry',
    }),
    [workspaceId],
  );

  return (
    <div className="space-y-3" data-testid="workspace-settings-execution-section">
      <div className="rounded border border-gray-200 p-2 text-xs dark:border-gray-800">
        <div className="flex items-start gap-2">
          <Bot aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-gray-500" />
          <div className="min-w-0">
            <div className="font-semibold">Workspace Execution</div>
            <div className="break-words text-gray-500 dark:text-gray-400">
              {workspaceData?.systemStatus?.llm_provider || currentChatModel?.provider || 'Mindscape LLM'}
              {currentChatModel?.model_name ? ` - ${currentChatModel.model_name}` : ''}
            </div>
            <div className="break-words text-gray-500 dark:text-gray-400">
              Source: {chatRoute?.source || currentChatModel?.metadata?.source || 'model-route-registry'}
            </div>
          </div>
        </div>
      </div>

      <Field label="Chat Model">
        <select
          className="w-full rounded border border-gray-200 bg-white px-2 py-1.5 text-sm dark:border-gray-700 dark:bg-gray-900"
          disabled={saving || loading || !chatRoute?.available_chat_models?.length}
          value={selectedModelKey}
          onChange={(event) => void updateChatModel(event.target.value)}
        >
          {chatRoute?.available_chat_models?.length ? (
            chatRoute.available_chat_models.map((model) => (
              <option key={modelOptionKey(model)} value={modelOptionKey(model)}>
                {model.model_name} ({model.provider})
              </option>
            ))
          ) : (
            <option value="">No chat models available</option>
          )}
        </select>
      </Field>

      <WorkspaceExecutorRuntimeSelector
        agents={agentsSnapshot.agents}
        routeEntries={routeEntries}
        resolvedRuntime={resolvedRuntime}
        selectedRuntimeId={selectedRuntimeId}
        disabled={saving || loading}
        onSelect={(runtimeId) => void updateExecutor(runtimeId)}
        layout="panel"
      />

      <button
        type="button"
        className="inline-flex w-full items-center justify-center gap-2 rounded border border-gray-200 px-3 py-2 text-sm font-semibold hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-900"
        disabled={testing}
        onClick={() => void testChatModel()}
      >
        <RefreshCw aria-hidden="true" className={`h-4 w-4 ${testing ? 'animate-spin' : ''}`} />
        {testing ? 'Testing' : 'Test Chat Model'}
      </button>

      <div className="space-y-2" aria-label="Execution actions">
        <ActionButton
          icon={<Bot aria-hidden="true" className="h-4 w-4" />}
          label="Runtime CLI Accounts"
          detail="Manage workspace Codex account homes"
          onClick={() => setRuntimeCliOpen(true)}
        />
        <ActionButton
          icon={<SlidersHorizontal aria-hidden="true" className="h-4 w-4" />}
          label="Runtime Profile"
          detail="Manage workspace execution contracts"
          onClick={() => setRuntimeProfileOpen(true)}
        />
        <ActionButton
          icon={<ExternalLink aria-hidden="true" className="h-4 w-4" />}
          label="LLM Settings"
          detail="Open global model defaults in a new window"
          onClick={() => openAppRouteInNewWindow(llmSettingsUrl)}
        />
        <ActionButton
          icon={<ExternalLink aria-hidden="true" className="h-4 w-4" />}
          label="Routing Rules"
          detail="Open model route registry in a new window"
          onClick={() => openAppRouteInNewWindow(routingUrl)}
        />
      </div>

      {routeMessage ? <div className="text-xs text-gray-500 dark:text-gray-400">{routeMessage}</div> : null}
      <WorkspaceRuntimeCliFloatingPanel
        open={runtimeCliOpen}
        workspaceId={workspaceId}
        onClose={() => setRuntimeCliOpen(false)}
      />
      <WorkspaceRuntimeProfileFloatingPanel
        open={runtimeProfileOpen}
        workspaceId={workspaceId}
        apiUrl={apiUrl}
        onClose={() => setRuntimeProfileOpen(false)}
      />
    </div>
  );
}
