'use client';

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { getApiBaseUrl } from '@/lib/api-url';

import { GcaPoolPane } from './cliApiKeys/GcaPoolPane';
import {
    CLI_AGENTS,
    DEFAULT_AGENT_MODES,
    AgentAuthActionResponse,
    AgentAuthStatusResponse,
    AgentMode,
    AgentTab,
    CliAgent,
    ExecutorSpec,
    PoolAccount,
    WorkspaceAgentInfo,
    WorkspaceAgentListResponse,
    WorkspaceGcaStatus,
} from './cliApiKeys/types';

interface CliApiKeysSectionProps {
    workspaceId?: string;
}

export default function CliApiKeysSection({ workspaceId }: CliApiKeysSectionProps) {
    const [activeTab, setActiveTab] = useState<AgentTab>('gemini');
    const [agentModes, setAgentModes] = useState<Record<AgentTab, AgentMode>>(DEFAULT_AGENT_MODES);
    const [values, setValues] = useState<Record<string, string>>({});
    const [configuredKeys, setConfiguredKeys] = useState<Record<string, boolean>>({});
    const [saving, setSaving] = useState<string | null>(null);
    const [saved, setSaved] = useState<string | null>(null);
    const [showKey, setShowKey] = useState<Record<string, boolean>>({});
    const [error, setError] = useState<string | null>(null);

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

    const [workspaceAgents, setWorkspaceAgents] = useState<Record<string, WorkspaceAgentInfo>>({});
    const [authStatuses, setAuthStatuses] = useState<Record<string, AgentAuthStatusResponse>>({});
    const [authStatusLoading, setAuthStatusLoading] = useState<Record<string, boolean>>({});
    const [authActionLoading, setAuthActionLoading] = useState<Record<string, string | null>>({});

    const agentMap = useMemo(
        () => Object.fromEntries(CLI_AGENTS.map((agent) => [agent.id, agent])) as Record<AgentTab, CliAgent>,
        []
    );

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
            throw new Error(
                (errData as Record<string, string>).detail || 'Save failed'
            );
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
            // Form still works with empty values
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
            // Pool list unavailable
        }
    }, []);

    const loadWorkspaceBinding = useCallback(async () => {
        if (!workspaceId) return;
        try {
            const base = getApiBaseUrl();
            const resp = await fetch(`${base}/api/v1/workspaces/${workspaceId}/executor-specs`);
            if (!resp.ok) return;
            const data: {
                resolved_executor_runtime?: string;
                executor_specs?: ExecutorSpec[];
            } = await resp.json();
            const specs = data.executor_specs || [];
            const targetRuntimeId = data.resolved_executor_runtime
                || specs.find((spec) => spec.is_primary)?.runtime_id
                || null;
            setExecutorRuntimeId(targetRuntimeId);
            const targetSpec = specs.find((spec) => spec.runtime_id === targetRuntimeId);
            const preferred = targetSpec?.config?.preferred_gca_runtime_id
                || targetSpec?.config?.gca_runtime_id
                || '';
            setBoundGcaRuntimeId(preferred);
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

    const loadWorkspaceAgents = useCallback(async () => {
        if (!workspaceId) {
            setWorkspaceAgents({});
            return;
        }
        try {
            const base = getApiBaseUrl();
            const resp = await fetch(`${base}/api/v1/workspaces/${workspaceId}/agents`);
            if (!resp.ok) return;
            const data: WorkspaceAgentListResponse = await resp.json();
            const nextMap: Record<string, WorkspaceAgentInfo> = {};
            for (const agent of data.agents || []) {
                nextMap[agent.id] = agent;
            }
            setWorkspaceAgents(nextMap);
        } catch {
            setWorkspaceAgents({});
        }
    }, [workspaceId]);

    const loadAgentAuthStatus = useCallback(async (agentId: AgentTab) => {
        const agent = agentMap[agentId];
        if (!workspaceId || !agent?.runtimeAgentId) return;
        setAuthStatusLoading((prev) => ({ ...prev, [agentId]: true }));
        try {
            const base = getApiBaseUrl();
            const resp = await fetch(
                `${base}/api/v1/workspaces/${workspaceId}/agents/${agent.runtimeAgentId}/auth-status`
            );
            if (!resp.ok) {
                const payload = await resp.json().catch(() => ({}));
                throw new Error((payload as Record<string, string>).detail || 'Failed to load auth status');
            }
            const data: AgentAuthStatusResponse = await resp.json();
            setAuthStatuses((prev) => ({ ...prev, [agentId]: data }));
        } catch (e: unknown) {
            setAuthStatuses((prev) => ({
                ...prev,
                [agentId]: {
                    agent_id: agent.runtimeAgentId || agent.id,
                    workspace_id: workspaceId,
                    available: false,
                    mode: agentId === 'claude' ? 'host_token' : 'host_session',
                    status: 'error',
                    error: e instanceof Error ? e.message : 'Failed to load auth status',
                    login_supported: agentId === 'codex',
                    logout_supported: agentId === 'codex',
                },
            }));
        } finally {
            setAuthStatusLoading((prev) => ({ ...prev, [agentId]: false }));
        }
    }, [agentMap, workspaceId]);

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
    }, [loadPoolAccounts, loadSettings, loadWorkspaceBinding, loadWorkspaceGcaStatus, loadWorkspaceAgents]);

    useEffect(() => {
        if (activeTab === 'codex' && agentModes.codex === 'host_session') {
            loadAgentAuthStatus('codex');
        }
        if (activeTab === 'claude' && agentModes.claude === 'host_token') {
            loadAgentAuthStatus('claude');
        }
    }, [activeTab, agentModes.codex, agentModes.claude, loadAgentAuthStatus]);

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
            }
            if (agent.id === 'claude' && nextMode === 'host_token') {
                loadAgentAuthStatus('claude');
            }
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : 'Failed to switch mode');
        }
    }, [loadAgentAuthStatus, saveSetting]);

    const handleSave = async (agent: CliAgent) => {
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
    };

    const handleAddAccount = async () => {
        setError(null);
        setAddingAccount(true);
        const base = getApiBaseUrl();
        try {
            await saveSetting('gemini_cli_auth_mode', 'gca');
            setCurrentAuthMode('gca');
            setAgentModes((prev) => ({ ...prev, gemini: 'gca' }));

            const resp = await fetch(`${base}/api/v1/gca-pool/add`, {
                method: 'POST',
            });
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
    };

    const handleRemoveAccount = async (runtimeId: string) => {
        setError(null);
        const base = getApiBaseUrl();
        try {
            await fetch(
                `${base}/api/v1/runtime-oauth/${runtimeId}/disconnect`,
                { method: 'POST' }
            );
            await fetch(`${base}/api/v1/gca-pool/${runtimeId}`, {
                method: 'DELETE',
            });
            loadPoolAccounts();
            loadWorkspaceGcaStatus();
        } catch {
            setError('Failed to remove account');
        }
    };

    const handleToggleEnabled = async (runtimeId: string, enabled: boolean) => {
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
    };

    const handleConnectAccount = async (runtimeId: string) => {
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
    };

    const handleSaveWorkspaceBinding = useCallback(async (nextRuntimeId: string) => {
        if (!workspaceId || !executorRuntimeId) {
            setError('No executor runtime is bound to this workspace.');
            return false;
        }

        setSavingBinding(true);
        setSavedBinding(false);
        setError(null);
        try {
            const base = getApiBaseUrl();
            const resp = await fetch(
                `${base}/api/v1/workspaces/${workspaceId}/executor-specs/${executorRuntimeId}/config`,
                {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        merge: true,
                        config: {
                            preferred_gca_runtime_id: nextRuntimeId || null,
                        },
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
    }, [executorRuntimeId, loadWorkspaceBinding, loadWorkspaceGcaStatus, workspaceId]);

    const handleAgentAuthAction = useCallback(async (
        agentId: Extract<AgentTab, 'codex'>,
        action: 'login' | 'logout'
    ) => {
        const agent = agentMap[agentId];
        if (!workspaceId || !agent.runtimeAgentId) {
            setError('Workspace runtime context is required for host-session actions.');
            return;
        }
        setAuthActionLoading((prev) => ({ ...prev, [agentId]: action }));
        setError(null);
        try {
            const base = getApiBaseUrl();
            const resp = await fetch(
                `${base}/api/v1/workspaces/${workspaceId}/agents/${agent.runtimeAgentId}/${action}`,
                { method: 'POST' }
            );
            const payload: AgentAuthActionResponse = await resp.json().catch(() => ({
                agent_id: agent.runtimeAgentId!,
                workspace_id: workspaceId,
                action,
                success: false,
                output: '',
                error: `${action} failed`,
            }));
            if (!resp.ok) {
                throw new Error(payload.error || `Failed to ${action}`);
            }
            if (payload.note) {
                setError(payload.note);
            }
            await loadAgentAuthStatus(agentId);
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : `Failed to ${action}`);
        } finally {
            setAuthActionLoading((prev) => ({ ...prev, [agentId]: null }));
        }
    }, [agentMap, loadAgentAuthStatus, workspaceId]);

    const connectedCount = poolAccounts.filter((a) => a.auth_status === 'connected').length;
    const activeAgent = agentMap[activeTab];
    const activeMode = agentModes[activeTab];
    const activeAuthStatus = authStatuses[activeTab];

    const hasConfiguredAuth = useCallback((agent: CliAgent) => {
        if (agent.id === 'gemini') {
            return connectedCount > 0 || !!configuredKeys[agent.settingsKey];
        }
        if (agent.id === 'codex') {
            return !!configuredKeys[agent.settingsKey]
                || activeTab === 'codex' && activeAuthStatus?.status === 'authenticated'
                || authStatuses.codex?.status === 'authenticated';
        }
        if (agent.id === 'claude') {
            return !!configuredKeys[agent.settingsKey];
        }
        return false;
    }, [activeAuthStatus?.status, activeTab, authStatuses.codex?.status, configuredKeys, connectedCount]);

    const renderApiKeyPane = (agent: CliAgent) => (
        <>
            <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-3">
                <p className="text-xs font-medium text-blue-700 dark:text-blue-300 mb-2">
                    How to get your {agent.label} API Key:
                </p>
                <ol className="list-decimal list-inside space-y-1">
                    {agent.guideSteps.map((step, i) => (
                        <li
                            key={i}
                            className="text-xs text-blue-600 dark:text-blue-400"
                        >
                            {i === 0 ? (
                                <>
                                    <a
                                        href={agent.guideUrl}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="underline hover:text-blue-800 dark:hover:text-blue-200"
                                    >
                                        {step}
                                    </a>
                                    {' ↗'}
                                </>
                            ) : (
                                step
                            )}
                        </li>
                    ))}
                </ol>
            </div>

            <div>
                <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                    {agent.label} API Key
                </label>
                <div className="flex gap-2">
                    <div className="relative flex-1">
                        <input
                            type={showKey[agent.id] ? 'text' : 'password'}
                            value={values[agent.settingsKey] || ''}
                            onChange={(e) =>
                                setValues((prev) => ({
                                    ...prev,
                                    [agent.settingsKey]: e.target.value,
                                }))
                            }
                            placeholder={agent.placeholder}
                            className="w-full px-3 py-2 text-sm border rounded-md
                                border-gray-300 dark:border-gray-600
                                bg-white dark:bg-gray-700
                                text-gray-900 dark:text-gray-100
                                placeholder-gray-400 dark:placeholder-gray-500
                                focus:ring-2 focus:ring-blue-500 focus:border-blue-500
                                font-mono"
                        />
                        <button
                            type="button"
                            onClick={() =>
                                setShowKey((prev) => ({
                                    ...prev,
                                    [agent.id]: !prev[agent.id],
                                }))
                            }
                            className="absolute right-2 top-1/2 -translate-y-1/2
                                text-gray-400 hover:text-gray-600 dark:hover:text-gray-300
                                text-xs"
                        >
                            {showKey[agent.id] ? 'Hide' : 'Show'}
                        </button>
                    </div>
                    <button
                        onClick={() => handleSave(agent)}
                        disabled={saving === agent.settingsKey}
                        className={`
                            px-4 py-2 text-sm font-medium rounded-md transition-colors
                            ${saved === agent.settingsKey
                                ? 'bg-green-600 text-white'
                                : 'bg-blue-600 hover:bg-blue-700 text-white'
                            }
                            disabled:opacity-50 disabled:cursor-not-allowed
                            min-w-[70px]
                        `}
                    >
                        {saving === agent.settingsKey
                            ? '...'
                            : saved === agent.settingsKey
                                ? '✓'
                                : 'Save'}
                    </button>
                </div>
            </div>

            {configuredKeys[agent.settingsKey] && (
                <div className="flex items-center gap-1.5 text-xs text-green-600 dark:text-green-400">
                    <span className="w-2 h-2 rounded-full bg-green-500" />
                    API key configured
                </div>
            )}
        </>
    );

    const renderModeSwitcher = (agent: CliAgent) => (
        <div className="flex flex-wrap gap-2">
            {agent.modeOptions.map((option) => (
                <button
                    key={option.value}
                    type="button"
                    onClick={() => handleModeChange(agent, option.value)}
                    className={`px-3 py-1.5 text-xs font-medium rounded-full border transition-colors ${
                        activeMode === option.value
                            ? 'border-blue-500 bg-blue-50 text-blue-600 dark:border-blue-400 dark:bg-blue-900/20 dark:text-blue-300'
                            : 'border-gray-300 text-gray-600 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800'
                    }`}
                >
                    {option.label}
                </button>
            ))}
        </div>
    );

    const renderHostPane = (agent: CliAgent) => {
        const runtimeInfo = agent.runtimeAgentId ? workspaceAgents[agent.runtimeAgentId] : null;
        const status = authStatuses[agent.id];
        const loading = authStatusLoading[agent.id];
        const busyAction = authActionLoading[agent.id];

        return (
            <div className="space-y-4">
                <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-3 space-y-2">
                    <p className="text-xs font-medium text-amber-700 dark:text-amber-300">
                        {agent.id === 'codex' ? 'Host Session' : 'Host Token'}
                    </p>
                    <p className="text-xs text-amber-600 dark:text-amber-400">
                        {agent.id === 'codex'
                            ? 'This uses the real host Codex CLI login state. API keys saved here are only for pure API mode.'
                            : 'Claude Code host-token mode is managed on the host. The backend does not fake a login state for it.'}
                    </p>
                </div>

                <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-3 space-y-2">
                    <div className="flex items-center gap-2 text-xs">
                        <span className={`w-2 h-2 rounded-full ${
                            runtimeInfo?.status === 'available' ? 'bg-green-500' : 'bg-gray-400'
                        }`} />
                        <span className="text-gray-700 dark:text-gray-300">
                            Runtime surface: {runtimeInfo?.status || 'unknown'}
                        </span>
                        {runtimeInfo?.transport && (
                            <span className="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400">
                                {runtimeInfo.transport}
                            </span>
                        )}
                        {runtimeInfo?.reason && (
                            <span className="text-gray-500 dark:text-gray-400">
                                {runtimeInfo.reason}
                            </span>
                        )}
                    </div>

                    {!workspaceId && (
                        <p className="text-xs text-gray-500 dark:text-gray-400">
                            Open this panel from a workspace to inspect live host-session status.
                        </p>
                    )}

                    {workspaceId && (
                        <>
                            <div className="flex items-center gap-2 flex-wrap">
                                {agent.id === 'codex' && (
                                    <>
                                        <button
                                            type="button"
                                            onClick={() => handleAgentAuthAction('codex', 'login')}
                                            disabled={busyAction === 'login' || runtimeInfo?.status !== 'available'}
                                            className="px-3 py-1.5 text-xs font-medium rounded-md bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
                                        >
                                            {busyAction === 'login' ? '登入中...' : '登入'}
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => handleAgentAuthAction('codex', 'logout')}
                                            disabled={busyAction === 'logout' || runtimeInfo?.status !== 'available'}
                                            className="px-3 py-1.5 text-xs font-medium rounded-md border border-gray-300 text-gray-700 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800"
                                        >
                                            {busyAction === 'logout' ? '登出中...' : '登出'}
                                        </button>
                                    </>
                                )}
                                <button
                                    type="button"
                                    onClick={() => loadAgentAuthStatus(agent.id)}
                                    disabled={loading || runtimeInfo?.status !== 'available'}
                                    className="px-3 py-1.5 text-xs font-medium rounded-md border border-gray-300 text-gray-700 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800"
                                >
                                    {loading ? '檢查中...' : '重新檢查'}
                                </button>
                            </div>

                            {status && (
                                <div className={`rounded-md border p-2 text-[11px] ${
                                    status.status === 'authenticated'
                                        ? 'border-green-200 dark:border-green-800 bg-green-50/60 dark:bg-green-900/10 text-green-700 dark:text-green-300'
                                        : status.status === 'manual_required'
                                            ? 'border-blue-200 dark:border-blue-800 bg-blue-50/60 dark:bg-blue-900/10 text-blue-700 dark:text-blue-300'
                                            : status.status === 'unavailable'
                                                ? 'border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/20 text-gray-600 dark:text-gray-300'
                                                : 'border-amber-200 dark:border-amber-800 bg-amber-50/60 dark:bg-amber-900/10 text-amber-700 dark:text-amber-300'
                                }`}>
                                    <div className="font-medium">
                                        Host auth status: {status.status}
                                    </div>
                                    {status.note && (
                                        <div className="mt-1">
                                            {status.note}
                                        </div>
                                    )}
                                    {status.output && (
                                        <pre className="mt-2 whitespace-pre-wrap break-words text-[11px] font-mono">
                                            {status.output}
                                        </pre>
                                    )}
                                    {status.error && (
                                        <div className="mt-1">
                                            {status.error}
                                        </div>
                                    )}
                                    {status.manual_command && (
                                        <div className="mt-2">
                                            Manual command: <code className="font-mono">{status.manual_command}</code>
                                        </div>
                                    )}
                                </div>
                            )}
                        </>
                    )}
                </div>
            </div>
        );
    };

    return (
        <div className="mb-5">
            <div className="mb-3">
                <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100">
                    🔑 CLI Agent Authentication
                </h3>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                    Configure provider-specific auth modes. Gemini supports Google Account (GCA) or API key; Codex and Claude can use pure API keys or host-managed sessions.
                </p>
            </div>

            <div className="flex border-b border-gray-200 dark:border-gray-700 mb-4">
                {CLI_AGENTS.map((agent) => (
                    <button
                        key={agent.id}
                        onClick={() => {
                            setActiveTab(agent.id);
                            setError(null);
                        }}
                        className={`
                            flex items-center gap-1.5 px-4 py-2 text-sm font-medium
                            border-b-2 transition-colors
                            ${activeTab === agent.id
                                ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                                : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
                            }
                        `}
                    >
                        <span>{agent.icon}</span>
                        {agent.label}
                        {hasConfiguredAuth(agent) && (
                            <span className="w-1.5 h-1.5 rounded-full bg-green-500 ml-1" />
                        )}
                    </button>
                ))}
            </div>

            <div className="space-y-4">
                <div className="flex items-center justify-between gap-3 flex-wrap">
                    {renderModeSwitcher(activeAgent)}

                    {activeTab === 'gemini' && (
                        <div className="flex items-center gap-4 text-xs flex-wrap">
                            <div className="flex items-center gap-2">
                                <span className="text-gray-500 dark:text-gray-400">Active mode:</span>
                                <span className="px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 font-medium">
                                    {currentAuthMode === 'gca' ? 'Google Account (GCA)'
                                        : currentAuthMode === 'vertex_ai' ? 'Vertex AI'
                                            : 'Gemini API Key'}
                                </span>
                            </div>
                            <div className="flex items-center gap-2">
                                <span className="text-gray-500 dark:text-gray-400">Agent model:</span>
                                <select
                                    value={agentModel}
                                    onChange={async (e) => {
                                        const newModel = e.target.value;
                                        setAgentModel(newModel);
                                        setSavingModel(true);
                                        try {
                                            await saveSetting('agent_cli_model', newModel);
                                            setSavedModel(true);
                                            setTimeout(() => setSavedModel(false), 2000);
                                        } catch {
                                            // ignore
                                        } finally {
                                            setSavingModel(false);
                                        }
                                    }}
                                    disabled={savingModel}
                                    className="px-2 py-0.5 text-xs rounded-md border
                                        border-gray-300 dark:border-gray-600
                                        bg-white dark:bg-gray-700
                                        text-gray-900 dark:text-gray-100
                                        focus:ring-2 focus:ring-blue-500 focus:border-blue-500
                                        disabled:opacity-50"
                                >
                                    <option value="gemini-3-pro">Gemini 3 Pro</option>
                                    <option value="gemini-3-flash">Gemini 3 Flash</option>
                                    <option value="gemini-2.5-pro">Gemini 2.5 Pro</option>
                                    <option value="gemini-2.5-flash">Gemini 2.5 Flash</option>
                                </select>
                                {savedModel && (
                                    <span className="text-green-600 dark:text-green-400">✓</span>
                                )}
                            </div>
                        </div>
                    )}
                </div>

                {activeTab === 'gemini' && activeMode === 'gca' && (
                    <GcaPoolPane
                        addingAccount={addingAccount}
                        boundGcaRuntimeId={boundGcaRuntimeId}
                        executorRuntimeId={executorRuntimeId}
                        pendingRuntimeId={pendingRuntimeId}
                        poolAccounts={poolAccounts}
                        savedBinding={savedBinding}
                        savingBinding={savingBinding}
                        workspaceGcaStatus={workspaceGcaStatus}
                        workspaceId={workspaceId}
                        onAddAccount={handleAddAccount}
                        onBoundGcaRuntimeIdChange={setBoundGcaRuntimeId}
                        onConnectAccount={handleConnectAccount}
                        onRemoveAccount={handleRemoveAccount}
                        onSaveWorkspaceBinding={handleSaveWorkspaceBinding}
                        onToggleEnabled={handleToggleEnabled}
                    />
                )}
                {activeMode === 'api' && renderApiKeyPane(activeAgent)}
                {activeTab === 'codex' && activeMode === 'host_session' && renderHostPane(activeAgent)}
                {activeTab === 'claude' && activeMode === 'host_token' && renderHostPane(activeAgent)}

                {error && (
                    <p className="text-xs text-red-600 dark:text-red-400">{error}</p>
                )}
            </div>
        </div>
    );
}
