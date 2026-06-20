'use client';

import { useCallback, useEffect, useState } from 'react';

import { getApiBaseUrl } from '@/lib/api-url';

import type {
  AgentMode,
  AgentTab,
  CliAgent,
  PoolAccount,
  WorkspaceExecutorPolicyPayload,
  WorkspaceGcaStatus,
} from './types';
import { DEFAULT_AGENT_MODES } from './types';

interface UseCliApiKeysSettingsControllerParams {
  initialAgentTab: AgentTab;
  loadAgentAuthStatus: (agentId: AgentTab) => void;
  loadCodexAccountHomes: () => void;
  loadWorkspaceAgents: () => void;
  setError: (message: string | null) => void;
  workspaceId?: string;
}

export function useCliApiKeysSettingsController({
  initialAgentTab,
  loadAgentAuthStatus,
  loadCodexAccountHomes,
  loadWorkspaceAgents,
  setError,
  workspaceId,
}: UseCliApiKeysSettingsControllerParams) {
  const [activeTab, setActiveTab] = useState<AgentTab>(initialAgentTab);
  const [agentModes, setAgentModes] = useState<Record<AgentTab, AgentMode>>(DEFAULT_AGENT_MODES);
  const [values, setValues] = useState<Record<string, string>>({});
  const [configuredKeys, setConfiguredKeys] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [showKey, setShowKey] = useState<Record<string, boolean>>({});

  const [agentModel, setAgentModel] = useState<string>('gemini-3-pro');
  const [savingModel, setSavingModel] = useState(false);
  const [savedModel, setSavedModel] = useState(false);

  const [poolAccounts, setPoolAccounts] = useState<PoolAccount[]>([]);
  const [addingAccount, setAddingAccount] = useState(false);
  const [pendingRuntimeId, setPendingRuntimeId] = useState<string | null>(null);
  const [currentAuthMode, setCurrentAuthMode] = useState<string>('gemini_api_key');
  const [executorRuntimeId, setExecutorRuntimeId] = useState<string | null>(null);
  const [boundGcaRuntimeId, setBoundGcaRuntimeId] = useState<string>('');
  const [workspaceGcaStatus, setWorkspaceGcaStatus] = useState<WorkspaceGcaStatus | null>(null);
  const [savingBinding, setSavingBinding] = useState(false);
  const [savedBinding, setSavedBinding] = useState(false);

  const saveSetting = useCallback(async (key: string, value: string) => {
    const base = getApiBaseUrl();
    const resp = await fetch(`${base}/api/v1/system-settings/${key}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        value,
        category: 'gemini_cli',
      }),
    });
    if (!resp.ok) {
      const errData = await resp.json().catch(() => ({}));
      throw new Error((errData as Record<string, string>).detail || 'Save failed');
    }
  }, []);

  const loadSettings = useCallback(async () => {
    try {
      const base = getApiBaseUrl();
      const resp = await fetch(`${base}/api/v1/system-settings/category/gemini_cli`);
      if (!resp.ok) return;
      const settings: Array<{ key: string; value: string }> = await resp.json();
      const map: Record<string, string> = {};
      const configured: Record<string, boolean> = {};
      let nextGeminiMode: AgentMode = 'api';
      let nextCodexMode: AgentMode = 'api';
      let nextClaudeMode: AgentMode = 'api';

      for (const setting of settings) {
        const rawValue = typeof setting.value === 'string' ? setting.value : '';
        if (setting.key === 'gemini_cli_auth_mode') {
          setCurrentAuthMode(rawValue || 'gemini_api_key');
          nextGeminiMode = rawValue === 'gca' ? 'gca' : 'api';
        }
        if (setting.key === 'codex_cli_auth_mode') {
          nextCodexMode = rawValue === 'host_session' ? 'host_session' : 'api';
        }
        if (setting.key === 'claude_code_cli_auth_mode') {
          nextClaudeMode = rawValue === 'host_token' ? 'host_token' : 'api';
        }
        if (setting.key === 'agent_cli_model') {
          setAgentModel(rawValue || 'gemini-3-pro');
        }
        if (rawValue) {
          configured[setting.key] = true;
        }
        if (rawValue && rawValue !== '***') {
          map[setting.key] = rawValue;
        }
      }

      setAgentModes({
        gemini: nextGeminiMode,
        codex: nextCodexMode,
        claude: nextClaudeMode,
      });
      setConfiguredKeys((prev) => ({ ...prev, ...configured }));
      setValues((prev) => ({ ...prev, ...map }));
    } catch {
      // Form still works with empty values.
    }
  }, []);

  const loadPoolAccounts = useCallback(async () => {
    try {
      const base = getApiBaseUrl();
      const resp = await fetch(`${base}/api/v1/gca-pool`);
      if (!resp.ok) return;
      const data = await resp.json();
      setPoolAccounts(data.accounts || []);
    } catch {
      // Pool list unavailable.
    }
  }, []);

  const loadWorkspaceBinding = useCallback(async () => {
    if (!workspaceId) return;
    try {
      const base = getApiBaseUrl();
      const resp = await fetch(
        `${base}/api/v1/settings/model-route-registry/workspace-executor?workspace_id=${encodeURIComponent(workspaceId)}`
      );
      if (!resp.ok) return;
      const data: WorkspaceExecutorPolicyPayload = await resp.json();
      const targetRuntimeId = data.primary_executor_runtime
        || data.resolved_executor_runtime
        || null;
      setExecutorRuntimeId(targetRuntimeId);
      setBoundGcaRuntimeId(data.surfaces?.gemini_cli?.preferred_runtime_id || '');
    } catch {
      // Binding UI remains empty if the workspace config is unavailable.
    }
  }, [workspaceId]);

  const loadWorkspaceGcaStatus = useCallback(async () => {
    if (!workspaceId) {
      setWorkspaceGcaStatus(null);
      return;
    }
    try {
      const base = getApiBaseUrl();
      const resp = await fetch(
        `${base}/api/v1/gca-pool/workspace-status?workspace_id=${encodeURIComponent(workspaceId)}`
      );
      if (!resp.ok) {
        setWorkspaceGcaStatus(null);
        return;
      }
      const data: WorkspaceGcaStatus = await resp.json();
      setWorkspaceGcaStatus(data);
    } catch {
      setWorkspaceGcaStatus(null);
    }
  }, [workspaceId]);

  useEffect(() => {
    loadSettings();
    loadPoolAccounts();
    loadWorkspaceBinding();
    loadWorkspaceGcaStatus();
    loadWorkspaceAgents();

    const handleOAuthMessage = (event: MessageEvent) => {
      if (event.data?.type === 'RUNTIME_OAUTH_RESULT') {
        setPendingRuntimeId(null);
        if (event.data.success) {
          loadPoolAccounts();
          loadSettings();
          loadWorkspaceGcaStatus();
        } else {
          setError(event.data.error || 'Google authentication failed');
        }
      }
    };
    window.addEventListener('message', handleOAuthMessage);
    return () => window.removeEventListener('message', handleOAuthMessage);
  }, [loadPoolAccounts, loadSettings, loadWorkspaceBinding, loadWorkspaceGcaStatus, loadWorkspaceAgents, setError]);

  useEffect(() => {
    if (activeTab === 'codex' && agentModes.codex === 'host_session') {
      loadAgentAuthStatus('codex');
      loadCodexAccountHomes();
    }
    if (activeTab === 'claude' && agentModes.claude === 'host_token') {
      loadAgentAuthStatus('claude');
    }
  }, [activeTab, agentModes.codex, agentModes.claude, loadAgentAuthStatus, loadCodexAccountHomes]);

  const handleModeChange = useCallback(async (agent: CliAgent, nextMode: AgentMode) => {
    setAgentModes((prev) => ({ ...prev, [agent.id]: nextMode }));
    setError(null);
    try {
      let storedValue: string = nextMode;
      if (agent.id === 'gemini') {
        storedValue = nextMode === 'gca' ? 'gca' : 'gemini_api_key';
        setCurrentAuthMode(storedValue);
      }
      await saveSetting(agent.modeSettingKey, storedValue);
      if (agent.id === 'codex' && nextMode === 'host_session') {
        loadAgentAuthStatus('codex');
        loadCodexAccountHomes();
      }
      if (agent.id === 'claude' && nextMode === 'host_token') {
        loadAgentAuthStatus('claude');
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to switch mode');
    }
  }, [loadAgentAuthStatus, loadCodexAccountHomes, saveSetting, setError]);

  const handleSave = useCallback(async (agent: CliAgent) => {
    const key = agent.settingsKey;
    const val = values[key] || '';
    if (!val.trim()) {
      setError('Please enter an API key');
      return;
    }

    setSaving(key);
    setError(null);
    try {
      await saveSetting(key, val);
      if (agent.id === 'gemini') {
        await saveSetting(agent.modeSettingKey, 'gemini_api_key');
        setCurrentAuthMode('gemini_api_key');
        setAgentModes((prev) => ({ ...prev, gemini: 'api' }));
      }
      if (agent.id === 'codex') {
        await saveSetting(agent.modeSettingKey, 'api');
        setAgentModes((prev) => ({ ...prev, codex: 'api' }));
      }
      if (agent.id === 'claude') {
        await saveSetting(agent.modeSettingKey, 'api');
        setAgentModes((prev) => ({ ...prev, claude: 'api' }));
      }
      setConfiguredKeys((prev) => ({ ...prev, [key]: true }));
      setSaved(key);
      setTimeout(() => setSaved(null), 2000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setSaving(null);
    }
  }, [saveSetting, setError, values]);

  const handleAddAccount = useCallback(async () => {
    setError(null);
    setAddingAccount(true);
    const base = getApiBaseUrl();
    try {
      await saveSetting('gemini_cli_auth_mode', 'gca');
      setCurrentAuthMode('gca');
      setAgentModes((prev) => ({ ...prev, gemini: 'gca' }));

      const resp = await fetch(`${base}/api/v1/gca-pool/add`, { method: 'POST' });
      if (!resp.ok) throw new Error('Failed to create pool account');
      const data = await resp.json();
      const runtimeId = data.account?.id;
      if (!runtimeId) throw new Error('No runtime ID returned');

      setPendingRuntimeId(runtimeId);
      const w = 500, h = 600;
      const left = window.screenX + (window.innerWidth - w) / 2;
      const top = window.screenY + (window.innerHeight - h) / 2;
      window.open(
        `${base}/api/v1/runtime-oauth/${runtimeId}/authorize`,
        'oauth-popup',
        `width=${w},height=${h},left=${left},top=${top},popup=true`
      );

      const pollInterval = setInterval(async () => {
        await loadPoolAccounts();
        const acct = poolAccounts.find((a) => a.id === runtimeId);
        if (acct && acct.auth_status === 'connected') {
          clearInterval(pollInterval);
          setPendingRuntimeId(null);
          loadWorkspaceGcaStatus();
        }
      }, 2000);
      setTimeout(() => {
        clearInterval(pollInterval);
        setPendingRuntimeId(null);
      }, 120000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to add account');
    } finally {
      setAddingAccount(false);
    }
  }, [loadPoolAccounts, loadWorkspaceGcaStatus, poolAccounts, saveSetting, setError]);

  const handleRemoveAccount = useCallback(async (runtimeId: string) => {
    setError(null);
    const base = getApiBaseUrl();
    try {
      await fetch(`${base}/api/v1/runtime-oauth/${runtimeId}/disconnect`, { method: 'POST' });
      await fetch(`${base}/api/v1/gca-pool/${runtimeId}`, { method: 'DELETE' });
      loadPoolAccounts();
      loadWorkspaceGcaStatus();
    } catch {
      setError('Failed to remove account');
    }
  }, [loadPoolAccounts, loadWorkspaceGcaStatus, setError]);

  const handleToggleEnabled = useCallback(async (runtimeId: string, enabled: boolean) => {
    const base = getApiBaseUrl();
    try {
      await fetch(`${base}/api/v1/gca-pool/${runtimeId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      });
      loadPoolAccounts();
      loadWorkspaceGcaStatus();
    } catch {
      setError('Failed to update account');
    }
  }, [loadPoolAccounts, loadWorkspaceGcaStatus, setError]);

  const handleConnectAccount = useCallback(async (runtimeId: string) => {
    setError(null);
    setPendingRuntimeId(runtimeId);
    const base = getApiBaseUrl();
    const w = 500, h = 600;
    const left = window.screenX + (window.innerWidth - w) / 2;
    const top = window.screenY + (window.innerHeight - h) / 2;
    window.open(
      `${base}/api/v1/runtime-oauth/${runtimeId}/authorize`,
      'oauth-popup',
      `width=${w},height=${h},left=${left},top=${top},popup=true`
    );
  }, [setError]);

  const handleSaveWorkspaceBinding = useCallback(async (nextRuntimeId: string) => {
    if (!workspaceId) {
      setError('Workspace context is required.');
      return false;
    }

    setSavingBinding(true);
    setSavedBinding(false);
    setError(null);
    try {
      const base = getApiBaseUrl();
      const resp = await fetch(
        `${base}/api/v1/settings/model-route-registry/workspace-executor/preferred-runtime`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            workspace_id: workspaceId,
            surface: 'gemini_cli',
            preferred_runtime_id: nextRuntimeId || null,
          }),
        }
      );
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error((err as Record<string, string>).detail || 'Failed to save binding');
      }
      await loadWorkspaceBinding();
      await loadWorkspaceGcaStatus();
      setSavedBinding(true);
      setTimeout(() => setSavedBinding(false), 2000);
      return true;
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to save workspace binding');
      return false;
    } finally {
      setSavingBinding(false);
    }
  }, [loadWorkspaceBinding, loadWorkspaceGcaStatus, setError, workspaceId]);

  return {
    activeTab,
    addingAccount,
    agentModel,
    agentModes,
    boundGcaRuntimeId,
    configuredKeys,
    connectedCount: poolAccounts.filter((account) => account.auth_status === 'connected').length,
    currentAuthMode,
    executorRuntimeId,
    handleAddAccount,
    handleConnectAccount,
    handleModeChange,
    handleRemoveAccount,
    handleSave,
    handleSaveWorkspaceBinding,
    handleToggleEnabled,
    pendingRuntimeId,
    poolAccounts,
    saved,
    savedBinding,
    savedModel,
    saveSetting,
    saving,
    savingBinding,
    savingModel,
    setActiveTab,
    setAgentModel,
    setBoundGcaRuntimeId,
    setSavedModel,
    setSavingModel,
    setShowKey,
    setValues,
    showKey,
    values,
    workspaceGcaStatus,
  };
}
