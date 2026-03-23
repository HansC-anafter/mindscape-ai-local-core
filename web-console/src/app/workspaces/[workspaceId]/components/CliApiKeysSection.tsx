'use client';

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { getApiBaseUrl } from '@/lib/api-url';
import { parseServerTimestamp } from '@/lib/time';

interface PoolAccount {
    id: string;
    email: string | null;
    auth_status: string;
    pool_enabled: boolean;
    pool_priority: number;
    cooldown_until: string | null;
    last_used_at: string | null;
    last_error_code: string | null;
}

interface ExecutorSpec {
    runtime_id: string;
    display_name: string;
    is_primary: boolean;
    config?: Record<string, any>;
    priority: number;
}

interface WorkspaceGcaStatus {
    requested_workspace_id: string;
    effective_workspace_id: string;
    auth_workspace_id: string | null;
    source_workspace_id: string | null;
    selection_reason: string;
    selection_trace: Array<Record<string, any>>;
    policy_mode: 'pinned_runtime' | 'pool_rotation';
    preferred_runtime_id: string | null;
    resolved_runtime_id: string | null;
    resolved_email: string | null;
    resolved_status: 'available' | 'cooldown' | 'unavailable';
    cooldown_until: string | null;
    next_reset_at: string | null;
    available_count: number;
    cooling_count: number;
    pool_count: number;
    error: string | null;
}

interface WorkspaceAgentInfo {
    id: string;
    name: string;
    description: string;
    status: 'available' | 'unavailable' | 'error';
    version: string;
    risk_level: string;
    cli_command?: string | null;
    transport?: string | null;
    reason?: string | null;
}

interface WorkspaceAgentListResponse {
    agents: WorkspaceAgentInfo[];
}

interface AgentAuthStatusResponse {
    agent_id: string;
    workspace_id: string;
    available: boolean;
    transport?: string | null;
    reason?: string | null;
    mode: string;
    status: string;
    note?: string | null;
    output?: string | null;
    error?: string | null;
    login_supported: boolean;
    logout_supported: boolean;
    manual_command?: string | null;
}

interface AgentAuthActionResponse {
    agent_id: string;
    workspace_id: string;
    action: string;
    success: boolean;
    output: string;
    error?: string | null;
    note?: string | null;
}

type AgentTab = 'gemini' | 'claude' | 'codex';
type AgentMode = 'api' | 'gca' | 'host_session' | 'host_token';

interface ModeOption {
    value: AgentMode;
    label: string;
}

interface CliAgent {
    id: AgentTab;
    label: string;
    settingsKey: string;
    placeholder: string;
    guideUrl: string;
    guideSteps: string[];
    icon: string;
    modeSettingKey: string;
    modeOptions: ModeOption[];
    runtimeAgentId?: string;
}

const CLI_AGENTS: CliAgent[] = [
    {
        id: 'gemini',
        label: 'Gemini CLI',
        settingsKey: 'gemini_api_key',
        placeholder: 'AIzaSy...',
        guideUrl: 'https://aistudio.google.com/apikey',
        guideSteps: [
            'Open Google AI Studio',
            'Click "Create API Key"',
            'Select or create a GCP project',
            'Copy the generated key and paste it below',
        ],
        icon: '✦',
        modeSettingKey: 'gemini_cli_auth_mode',
        modeOptions: [
            { value: 'gca', label: 'Google Account (GCA)' },
            { value: 'api', label: '純 API' },
        ],
    },
    {
        id: 'claude',
        label: 'Claude Code',
        settingsKey: 'claude_api_key',
        placeholder: 'sk-ant-...',
        guideUrl: 'https://console.anthropic.com/settings/keys',
        guideSteps: [
            'Open Anthropic Console',
            'Go to Settings → API Keys',
            'Click "Create Key" and copy it',
            'Paste the key below',
        ],
        icon: '◈',
        modeSettingKey: 'claude_code_cli_auth_mode',
        modeOptions: [
            { value: 'host_token', label: 'Host Token' },
            { value: 'api', label: '純 API' },
        ],
        runtimeAgentId: 'claude_code_cli',
    },
    {
        id: 'codex',
        label: 'Codex CLI',
        settingsKey: 'openai_api_key',
        placeholder: 'sk-...',
        guideUrl: 'https://platform.openai.com/api-keys',
        guideSteps: [
            'Open OpenAI Platform',
            'Go to API Keys page',
            'Click "Create new secret key"',
            'Copy and paste the key below',
        ],
        icon: '⬡',
        modeSettingKey: 'codex_cli_auth_mode',
        modeOptions: [
            { value: 'host_session', label: 'Host Session' },
            { value: 'api', label: '純 API' },
        ],
        runtimeAgentId: 'codex_cli',
    },
];

const DEFAULT_AGENT_MODES: Record<AgentTab, AgentMode> = {
    gemini: 'api',
    claude: 'api',
    codex: 'api',
};

function formatServerDateTime(value: string | null): string {
    const parsed = parseServerTimestamp(value);
    if (!parsed) return 'Unknown';
    return parsed.toLocaleString([], {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
    });
}

function formatTimeRemaining(value: string | null): string | null {
    const parsed = parseServerTimestamp(value);
    if (!parsed) return null;
    const diffMs = parsed.getTime() - Date.now();
    if (diffMs <= 0) return 'ready now';
    const totalMinutes = Math.ceil(diffMs / 60000);
    const hours = Math.floor(totalMinutes / 60);
    const minutes = totalMinutes % 60;
    if (hours > 0 && minutes > 0) return `in ${hours}h ${minutes}m`;
    if (hours > 0) return `in ${hours}h`;
    return `in ${minutes}m`;
}

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

    const renderGcaPane = () => (
        <>
            <div className="bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800 rounded-lg p-3">
                <p className="text-xs font-medium text-emerald-700 dark:text-emerald-300 mb-1">
                    GCA Multi-Account Pool
                </p>
                <p className="text-xs text-emerald-600 dark:text-emerald-400">
                    Add multiple Google accounts for automatic rotation. Workspace status below reflects backend pool selection and cooldown resets after observed 429s; it does not read the external IDE quota dashboard directly.
                </p>
            </div>

            {workspaceId && (
                <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-3 space-y-2">
                    <p className="text-xs font-medium text-blue-700 dark:text-blue-300">
                        Workspace GCA policy
                    </p>
                    <p className="text-xs text-blue-600 dark:text-blue-400">
                        By default, this workspace uses the enabled GCA pool with automatic rotation. Only pick a specific account if you want to pin this workspace to one runtime for debugging or cost isolation. Discoverable workspaces without their own override can fall back to the initiating or dispatch workspace, with trace metadata recorded per task.
                    </p>
                    <div className="flex items-center gap-2 flex-wrap">
                        <select
                            value={boundGcaRuntimeId}
                            onChange={async (e) => {
                                const nextValue = e.target.value;
                                const previousValue = boundGcaRuntimeId;
                                setBoundGcaRuntimeId(nextValue);
                                const ok = await handleSaveWorkspaceBinding(nextValue);
                                if (!ok) {
                                    setBoundGcaRuntimeId(previousValue);
                                }
                            }}
                            disabled={!executorRuntimeId || savingBinding}
                            className="min-w-[220px] px-2 py-1.5 text-xs rounded-md border
                                border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700
                                text-gray-900 dark:text-gray-100"
                        >
                            <option value="">Use enabled pool rotation</option>
                            {poolAccounts.map((acct) => (
                                <option key={acct.id} value={acct.id}>
                                    Pin to {acct.email || acct.id} ({acct.id})
                                </option>
                            ))}
                        </select>
                        <span className="text-[11px] text-gray-500 dark:text-gray-400">
                            Executor: {executorRuntimeId || 'not bound'}
                            {workspaceGcaStatus?.policy_mode === 'pinned_runtime'
                                ? ` · saved: pinned ${workspaceGcaStatus.preferred_runtime_id || 'unknown'}`
                                : workspaceGcaStatus
                                    ? ' · saved: rotation enabled'
                                    : ''}
                        </span>
                        {savingBinding && (
                            <span className="text-[11px] px-2 py-1 rounded bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300">
                                Saving...
                            </span>
                        )}
                        {!savingBinding && savedBinding && (
                            <span className="text-[11px] px-2 py-1 rounded bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300">
                                Saved
                            </span>
                        )}
                    </div>
                    {workspaceGcaStatus && (
                        <div className={`rounded-md border p-2 text-[11px] ${
                            workspaceGcaStatus.error
                                ? 'border-amber-200 dark:border-amber-800 bg-amber-50/60 dark:bg-amber-900/10 text-amber-700 dark:text-amber-300'
                                : 'border-blue-200 dark:border-blue-800 bg-white/70 dark:bg-gray-900/20 text-blue-700 dark:text-blue-300'
                        }`}>
                            <div className="font-medium">
                                Backend pool resolution
                            </div>
                            <div className="mt-1">
                                Policy: {workspaceGcaStatus.policy_mode === 'pinned_runtime'
                                    ? `Pinned to ${workspaceGcaStatus.preferred_runtime_id || 'unknown'}`
                                    : 'Enabled pool rotation'}
                            </div>
                            <div>
                                Selected now: {workspaceGcaStatus.resolved_runtime_id
                                    ? `${workspaceGcaStatus.resolved_email || workspaceGcaStatus.resolved_runtime_id} (${workspaceGcaStatus.resolved_runtime_id})`
                                    : 'No eligible account'}
                            </div>
                            <div>
                                Status: {workspaceGcaStatus.resolved_status}
                                {workspaceGcaStatus.cooldown_until
                                    ? ` · resets ${formatServerDateTime(workspaceGcaStatus.cooldown_until)} (${formatTimeRemaining(workspaceGcaStatus.cooldown_until)})`
                                    : ''}
                            </div>
                            <div>
                                Pool health: {workspaceGcaStatus.available_count} available / {workspaceGcaStatus.cooling_count} cooling / {workspaceGcaStatus.pool_count} total
                                {workspaceGcaStatus.next_reset_at
                                    ? ` · next reset ${formatServerDateTime(workspaceGcaStatus.next_reset_at)} (${formatTimeRemaining(workspaceGcaStatus.next_reset_at)})`
                                    : ''}
                            </div>
                            <div>
                                Resolution: {workspaceGcaStatus.selection_reason}
                                {workspaceGcaStatus.effective_workspace_id && workspaceGcaStatus.effective_workspace_id !== workspaceId
                                    ? ` · effective workspace ${workspaceGcaStatus.effective_workspace_id}`
                                    : ''}
                            </div>
                            {workspaceGcaStatus.error && (
                                <div className="mt-1">
                                    {workspaceGcaStatus.error}
                                </div>
                            )}
                        </div>
                    )}
                </div>
            )}

            <div className="space-y-2">
                {poolAccounts.length === 0 && !addingAccount && (
                    <p className="text-xs text-gray-500 dark:text-gray-400 py-2">
                        No accounts in pool. Add a Google account to get started.
                    </p>
                )}
                {poolAccounts.map((acct) => {
                    const isCooling = acct.cooldown_until && (parseServerTimestamp(acct.cooldown_until)?.getTime() ?? 0) > Date.now();
                    const isPending = pendingRuntimeId === acct.id;
                    return (
                        <div
                            key={acct.id}
                            className={`flex items-center gap-3 p-2.5 rounded-lg border transition-colors ${!acct.pool_enabled
                                ? 'border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 opacity-60'
                                : isCooling
                                    ? 'border-amber-200 dark:border-amber-800 bg-amber-50/50 dark:bg-amber-900/10'
                                    : acct.auth_status === 'connected'
                                        ? 'border-green-200 dark:border-green-800 bg-green-50/30 dark:bg-green-900/10'
                                        : 'border-gray-200 dark:border-gray-700'
                            }`}
                        >
                            <span className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${isPending ? 'bg-amber-400 animate-pulse'
                                : isCooling ? 'bg-amber-500'
                                    : acct.auth_status === 'connected' ? 'bg-green-500'
                                        : 'bg-gray-400'
                            }`} />

                            <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2">
                                    <span className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                                        {acct.email || acct.id}
                                    </span>
                                    {isCooling && (
                                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300">
                                            Cooldown
                                        </span>
                                    )}
                                    {acct.last_error_code === '429' && !isCooling && acct.auth_status === 'connected' && (
                                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300">
                                            Recovered
                                        </span>
                                    )}
                                </div>
                                <span className="text-[10px] text-gray-400 dark:text-gray-500 font-mono">
                                    {acct.id}
                                </span>
                                <div className="text-[10px] text-gray-500 dark:text-gray-400 mt-0.5">
                                    {isCooling
                                        ? `Backend cooldown resets ${formatServerDateTime(acct.cooldown_until)} (${formatTimeRemaining(acct.cooldown_until)})`
                                        : acct.last_error_code === '429'
                                            ? 'Previous 429 cleared; backend cooldown is inactive.'
                                            : acct.auth_status === 'connected'
                                                ? 'Available now for pool rotation.'
                                                : 'Authenticate this account before it can join the pool.'}
                                </div>
                            </div>

                            <div className="flex items-center gap-1.5 flex-shrink-0">
                                {acct.auth_status !== 'connected' && !isPending && (
                                    <button
                                        type="button"
                                        onClick={() => handleConnectAccount(acct.id)}
                                        className="text-[11px] px-2 py-1 rounded border border-blue-300 dark:border-blue-700 text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors"
                                    >
                                        Connect
                                    </button>
                                )}
                                {isPending && (
                                    <span className="text-[11px] text-amber-600 dark:text-amber-400 animate-pulse">
                                        Waiting...
                                    </span>
                                )}
                                <button
                                    type="button"
                                    onClick={() => handleToggleEnabled(acct.id, !acct.pool_enabled)}
                                    title={acct.pool_enabled ? 'Disable' : 'Enable'}
                                    className={`w-8 h-4 rounded-full relative transition-colors ${acct.pool_enabled
                                        ? 'bg-green-500'
                                        : 'bg-gray-300 dark:bg-gray-600'
                                    }`}
                                >
                                    <span className={`absolute top-0.5 w-3 h-3 rounded-full bg-white shadow transition-transform ${acct.pool_enabled ? 'left-[18px]' : 'left-0.5'
                                    }`} />
                                </button>
                                <button
                                    type="button"
                                    onClick={() => handleRemoveAccount(acct.id)}
                                    className="text-[11px] px-1.5 py-1 rounded text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                                    title="Remove"
                                >
                                    ✕
                                </button>
                            </div>
                        </div>
                    );
                })}
            </div>

            <button
                type="button"
                onClick={handleAddAccount}
                disabled={addingAccount}
                className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-md bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
                <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" />
                    <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                    <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
                    <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
                </svg>
                {addingAccount ? 'Adding...' : 'Add Google Account'}
            </button>
        </>
    );

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

                {activeTab === 'gemini' && activeMode === 'gca' && renderGcaPane()}
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
