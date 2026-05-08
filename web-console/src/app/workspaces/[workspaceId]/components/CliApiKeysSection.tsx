'use client';

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
    AlertTriangle,
    Building2,
    CheckCircle2,
    Clock3,
    Plus,
    RefreshCw,
    ShieldCheck,
    UserRound,
    XCircle,
} from 'lucide-react';
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
    CodexAccountHomeTarget,
    CodexAccountHomeTargetsResponse,
    PoolAccount,
    WorkspaceAgentInfo,
    WorkspaceAgentListResponse,
    WorkspaceExecutorPolicyPayload,
    WorkspaceGcaStatus,
} from './cliApiKeys/types';

interface CliApiKeysSectionProps {
    workspaceId?: string;
}

type CodexTargetActionMessage = {
    kind: 'success' | 'error' | 'info';
    text: string;
};

const CODEX_LOGIN_TIMEOUT_MS = 120_000;
const CODEX_LOGOUT_TIMEOUT_MS = 45_000;

const fetchWithTimeout = async (
    input: RequestInfo | URL,
    init: RequestInit,
    timeoutMs: number
) => {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
    try {
        return await fetch(input, {
            ...init,
            signal: controller.signal,
        });
    } finally {
        window.clearTimeout(timeoutId);
    }
};

const isAbortError = (value: unknown) => value instanceof Error && value.name === 'AbortError';

const errorMessageFromPayload = (
    payload: unknown,
    fallback: string
) => {
    if (payload && typeof payload === 'object') {
        const record = payload as Record<string, unknown>;
        const detail = record.detail;
        if (typeof detail === 'string' && detail.trim()) return detail;
        const error = record.error;
        if (typeof error === 'string' && error.trim()) return error;
        const note = record.note;
        if (typeof note === 'string' && note.trim()) return note;
    }
    return fallback;
};

const codexAccountHomesRoot = (targets: CodexAccountHomeTarget[]) => {
    const home = targets.find((target) => target.codex_home)?.codex_home || '';
    const marker = '/accounts/';
    const markerIndex = home.indexOf(marker);
    if (markerIndex >= 0) {
        return home.slice(0, markerIndex + marker.length - 1);
    }
    return '/Users/shock/.mindscape/runtime/codex-home-pool/accounts';
};

const newCodexAccountHomePath = (targets: CodexAccountHomeTarget[]) => {
    const suffix = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
        ? crypto.randomUUID().replace(/-/g, '').slice(0, 16)
        : `${Date.now().toString(16)}${Math.random().toString(16).slice(2, 8)}`;
    return `${codexAccountHomesRoot(targets)}/acct-${suffix}`;
};

const codexAccountHomeEnv = (codexHome: string) => ({
    CODEX_HOME: codexHome,
    HOME: codexHome,
    XDG_CONFIG_HOME: `${codexHome}/.config`,
    XDG_DATA_HOME: `${codexHome}/.local/share`,
    XDG_STATE_HOME: `${codexHome}/.local/state`,
    codex_seed_kind: 'account_home',
});

const shortRuntimeId = (value: string | null | undefined) => {
    const raw = value || '';
    return raw.replace(/^runtime-codex_cli-/, 'codex:');
};

const shortKey = (value: string | null | undefined) => {
    const raw = value || '';
    return raw.length > 14 ? `${raw.slice(0, 8)}...${raw.slice(-6)}` : raw;
};

const codexStatusMeta = (target: CodexAccountHomeTarget) => {
    const errorCode = target.last_probe_error_code || target.last_error_code;
    if (target.probe_state === 'available') {
        return {
            label: 'Available',
            detail: 'External probe passed',
            icon: CheckCircle2,
            badge: 'border-green-200 bg-green-50 text-green-700 dark:border-green-800 dark:bg-green-900/20 dark:text-green-300',
            row: 'border-green-200 dark:border-green-800 bg-green-50/50 dark:bg-green-900/10',
        };
    }
    if (target.probe_state === 'quota_limited' || errorCode === '429') {
        return {
            label: 'Quota limited',
            detail: errorCode || '429',
            icon: Clock3,
            badge: 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300',
            row: 'border-amber-200 dark:border-amber-800 bg-amber-50/40 dark:bg-amber-900/10',
        };
    }
    if (target.probe_state === 'auth_failed' || errorCode) {
        return {
            label: 'Auth failed',
            detail: errorCode || 'auth_failed',
            icon: XCircle,
            badge: 'border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300',
            row: 'border-red-200 dark:border-red-800 bg-red-50/40 dark:bg-red-900/10',
        };
    }
    return {
        label: 'Unknown',
        detail: 'Not probed',
        icon: AlertTriangle,
        badge: 'border-gray-200 bg-gray-50 text-gray-600 dark:border-gray-700 dark:bg-gray-900/30 dark:text-gray-300',
        row: 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800',
    };
};

const codexScopeMeta = (target: CodexAccountHomeTarget) => {
    const scopeType = (target.account_scope_type || '').toLowerCase();
    if (scopeType === 'personal') {
        return {
            label: target.account_scope_label || 'Personal',
            sublabel: target.account_plan_type || 'personal',
            icon: UserRound,
            badge: 'border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-800 dark:bg-sky-900/20 dark:text-sky-300',
        };
    }
    if (scopeType === 'workspace') {
        return {
            label: target.account_scope_label || target.account_organization_title || 'Workspace',
            sublabel: [target.account_scope_role, target.account_plan_type].filter(Boolean).join(' / ') || 'workspace',
            icon: Building2,
            badge: 'border-violet-200 bg-violet-50 text-violet-700 dark:border-violet-800 dark:bg-violet-900/20 dark:text-violet-300',
        };
    }
    return {
        label: 'Unknown scope',
        sublabel: target.account_plan_type || 'unclassified',
        icon: ShieldCheck,
        badge: 'border-gray-200 bg-gray-50 text-gray-600 dark:border-gray-700 dark:bg-gray-900/30 dark:text-gray-300',
    };
};

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
    const [codexAccountHomes, setCodexAccountHomes] = useState<CodexAccountHomeTarget[]>([]);
    const [codexTargetsLoading, setCodexTargetsLoading] = useState(false);
    const [codexTargetActionLoading, setCodexTargetActionLoading] = useState<Record<string, string | null>>({});
    const [codexTargetActionMessages, setCodexTargetActionMessages] = useState<Record<string, CodexTargetActionMessage>>({});
    const [showCodexHomeCreator, setShowCodexHomeCreator] = useState(false);
    const [newCodexHome, setNewCodexHome] = useState('');
    const [addingCodexHome, setAddingCodexHome] = useState(false);
    const [addCodexHomeMessage, setAddCodexHomeMessage] = useState<CodexTargetActionMessage | null>(null);

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
            const resp = await fetch(
                `${base}/api/v1/settings/model-route-registry/workspace-executor?workspace_id=${encodeURIComponent(workspaceId)}`
            );
            if (!resp.ok) return;
            const data: WorkspaceExecutorPolicyPayload = await resp.json();
            const targetRuntimeId = data.primary_executor_runtime
                || data.resolved_executor_runtime
                || null;
            setExecutorRuntimeId(targetRuntimeId);
            const preferred = data.surfaces?.gemini_cli?.preferred_runtime_id
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

    const loadCodexAccountHomes = useCallback(async () => {
        const codexAgent = agentMap.codex;
        if (!workspaceId || !codexAgent?.runtimeAgentId) {
            setCodexAccountHomes([]);
            return;
        }
        setCodexTargetsLoading(true);
        try {
            const base = getApiBaseUrl();
            const resp = await fetch(
                `${base}/api/v1/workspaces/${workspaceId}/agents/${codexAgent.runtimeAgentId}/account-homes`
            );
            if (!resp.ok) {
                const payload = await resp.json().catch(() => ({}));
                throw new Error((payload as Record<string, string>).detail || 'Failed to load Codex account homes');
            }
            const data: CodexAccountHomeTargetsResponse = await resp.json();
            setCodexAccountHomes(data.targets || []);
        } catch (e: unknown) {
            setCodexAccountHomes([]);
            setError(e instanceof Error ? e.message : 'Failed to load Codex account homes');
        } finally {
            setCodexTargetsLoading(false);
        }
    }, [agentMap, workspaceId]);

    const openCodexHomeCreator = useCallback(() => {
        setNewCodexHome((prev) => prev.trim() || newCodexAccountHomePath(codexAccountHomes));
        setAddCodexHomeMessage(null);
        setShowCodexHomeCreator(true);
    }, [codexAccountHomes]);

    const handleAddCodexHome = useCallback(async () => {
        if (!workspaceId) {
            setAddCodexHomeMessage({ kind: 'error', text: 'Workspace context is required.' });
            return;
        }
        const codexHome = newCodexHome.trim().replace(/\/+$/, '');
        if (!codexHome) {
            setAddCodexHomeMessage({ kind: 'error', text: 'Account-home path is required.' });
            return;
        }
        setAddingCodexHome(true);
        setAddCodexHomeMessage(null);
        setError(null);
        try {
            const base = getApiBaseUrl();
            const resp = await fetch(`${base}/api/v1/auth/cli-runtime/register-host-session`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    workspace_id: workspaceId,
                    surface: 'codex_cli',
                    runtime_name: `Codex account home ${codexHome.split('/').filter(Boolean).slice(-1)[0] || ''}`.trim(),
                    metadata: codexAccountHomeEnv(codexHome),
                }),
            });
            const payload = await resp.json().catch(() => ({}));
            if (!resp.ok) {
                throw new Error(errorMessageFromPayload(payload, 'Failed to add Codex account home'));
            }
            setNewCodexHome('');
            setShowCodexHomeCreator(false);
            setAddCodexHomeMessage({
                kind: 'success',
                text: 'Account home added. Use Login on the new row.',
            });
            await loadCodexAccountHomes();
        } catch (e: unknown) {
            const message = e instanceof Error ? e.message : 'Failed to add Codex account home';
            setAddCodexHomeMessage({ kind: 'error', text: message });
            setError(message);
        } finally {
            setAddingCodexHome(false);
        }
    }, [loadCodexAccountHomes, newCodexHome, workspaceId]);

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
    }, [loadAgentAuthStatus, loadCodexAccountHomes, saveSetting]);

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
    }, [loadWorkspaceBinding, loadWorkspaceGcaStatus, workspaceId]);

    const handleAgentAuthAction = useCallback(async (
        agentId: Extract<AgentTab, 'codex'>,
        action: 'login' | 'logout',
        target?: CodexAccountHomeTarget
    ) => {
        const agent = agentMap[agentId];
        if (!workspaceId || !agent.runtimeAgentId) {
            setError('Workspace runtime context is required for host-session actions.');
            return;
        }
        if (!target || (!target.runtime_id && !target.account_key && !target.codex_home)) {
            setError('Select a Codex account-home target before login or logout.');
            return;
        }
        const targetKey = target.runtime_id || target.account_key || target.codex_home;
        setCodexTargetActionLoading((prev) => ({ ...prev, [targetKey]: action }));
        setCodexTargetActionMessages((prev) => ({
            ...prev,
            [targetKey]: {
                kind: 'info',
                text: action === 'login'
                    ? 'Login started. Complete the browser flow for this account-home target.'
                    : 'Logout started for this account-home target.',
            },
        }));
        setError(null);
        try {
            const base = getApiBaseUrl();
            const resp = await fetchWithTimeout(
                `${base}/api/v1/workspaces/${workspaceId}/agents/${agent.runtimeAgentId}/${action}`,
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        runtime_id: target.runtime_id,
                        account_key: target.account_key,
                        codex_home: target.codex_home,
                    }),
                },
                action === 'login' ? CODEX_LOGIN_TIMEOUT_MS : CODEX_LOGOUT_TIMEOUT_MS
            );
            const payload = await resp.json().catch(() => ({
                agent_id: agent.runtimeAgentId!,
                workspace_id: workspaceId,
                action,
                success: false,
                output: '',
                error: `${action} failed`,
            }));
            if (!resp.ok) {
                throw new Error(errorMessageFromPayload(payload, `Failed to ${action}`));
            }
            const typedPayload = payload as AgentAuthActionResponse;
            if (typedPayload.success === false) {
                throw new Error(errorMessageFromPayload(typedPayload, `Failed to ${action}`));
            }
            setCodexTargetActionMessages((prev) => ({
                ...prev,
                [targetKey]: {
                    kind: 'success',
                    text: action === 'login'
                        ? 'Login command completed. Refreshing this account-home status.'
                        : 'Logout command completed. Refreshing this account-home status.',
                },
            }));
            setCodexTargetActionLoading((prev) => ({ ...prev, [targetKey]: null }));
            if (action === 'login') {
                setCodexAccountHomes((prev) => prev.map((item) => {
                    const itemKey = item.runtime_id || item.account_key || item.codex_home;
                    if (itemKey !== targetKey) return item;
                    return {
                        ...item,
                        probe_state: 'unknown',
                        last_probe_error_code: null,
                        last_error_code: null,
                    };
                }));
            }
            await loadAgentAuthStatus(agentId);
            await loadCodexAccountHomes();
        } catch (e: unknown) {
            const message = isAbortError(e)
                ? `${action === 'login' ? 'Login' : 'Logout'} request timed out or was interrupted. The row was unlocked; refresh homes to re-check the account state.`
                : e instanceof Error
                    ? e.message
                    : `Failed to ${action}`;
            setCodexTargetActionMessages((prev) => ({
                ...prev,
                [targetKey]: {
                    kind: 'error',
                    text: message,
                },
            }));
            setError(message);
        } finally {
            setCodexTargetActionLoading((prev) => ({ ...prev, [targetKey]: null }));
        }
    }, [agentMap, loadAgentAuthStatus, loadCodexAccountHomes, workspaceId]);

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
                                ? 'Saved'
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
                                    <button
                                        type="button"
                                        onClick={() => loadCodexAccountHomes()}
                                        disabled={codexTargetsLoading}
                                        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border border-gray-300 text-gray-700 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800"
                                    >
                                        <RefreshCw className={`h-3.5 w-3.5 ${codexTargetsLoading ? 'animate-spin' : ''}`} />
                                        {codexTargetsLoading ? 'Refreshing homes...' : 'Refresh Homes'}
                                    </button>
                                )}
                                <button
                                    type="button"
                                    onClick={() => loadAgentAuthStatus(agent.id)}
                                    disabled={loading || runtimeInfo?.status !== 'available'}
                                    className="px-3 py-1.5 text-xs font-medium rounded-md border border-gray-300 text-gray-700 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800"
                                >
                                    {loading ? 'Checking...' : 'Refresh'}
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

                            {agent.id === 'codex' && (
                                <div className="space-y-3">
                                    <div className="flex items-start justify-between gap-3">
                                        <div>
                                            <div className="text-xs font-semibold text-gray-800 dark:text-gray-200">
                                                Account homes
                                            </div>
                                            <div className="mt-1 text-[11px] leading-4 text-gray-500 dark:text-gray-400">
                                                Scope is read from OpenAI token claims. Login is rejected when the selected row and returned account identity do not match.
                                            </div>
                                        </div>
                                        <div className="flex shrink-0 items-center gap-2">
                                            <button
                                                type="button"
                                                onClick={openCodexHomeCreator}
                                                className="inline-flex items-center gap-1.5 rounded-md bg-gray-900 px-2.5 py-1.5 text-[11px] font-medium text-white hover:bg-gray-800 dark:bg-gray-100 dark:text-gray-900 dark:hover:bg-white"
                                            >
                                                <Plus className="h-3.5 w-3.5" />
                                                Add Home
                                            </button>
                                            <span className="rounded-full border border-gray-200 px-2 py-0.5 text-[11px] font-medium text-gray-600 dark:border-gray-700 dark:text-gray-300">
                                                {codexAccountHomes.length} targets
                                            </span>
                                        </div>
                                    </div>

                                    {showCodexHomeCreator && (
                                        <div className="rounded-md border border-blue-200 bg-blue-50/60 p-3 dark:border-blue-800 dark:bg-blue-900/10">
                                            <label className="block text-[11px] font-semibold text-blue-800 dark:text-blue-200">
                                                New account-home path
                                            </label>
                                            <div className="mt-2 flex flex-col gap-2 lg:flex-row">
                                                <input
                                                    type="text"
                                                    value={newCodexHome}
                                                    onChange={(event) => setNewCodexHome(event.target.value)}
                                                    className="min-w-0 flex-1 rounded-md border border-blue-200 bg-white px-3 py-2 font-mono text-xs text-gray-900 outline-none focus:border-blue-500 dark:border-blue-800 dark:bg-gray-950 dark:text-gray-100"
                                                />
                                                <div className="flex items-center gap-2">
                                                    <button
                                                        type="button"
                                                        onClick={() => setNewCodexHome(newCodexAccountHomePath(codexAccountHomes))}
                                                        disabled={addingCodexHome}
                                                        className="rounded-md border border-blue-200 bg-white px-3 py-2 text-xs font-medium text-blue-700 hover:bg-blue-50 disabled:opacity-50 dark:border-blue-800 dark:bg-gray-950 dark:text-blue-300 dark:hover:bg-blue-900/20"
                                                    >
                                                        Generate
                                                    </button>
                                                    <button
                                                        type="button"
                                                        onClick={handleAddCodexHome}
                                                        disabled={addingCodexHome || !newCodexHome.trim()}
                                                        className="rounded-md bg-blue-600 px-3 py-2 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                                                    >
                                                        {addingCodexHome ? 'Adding...' : 'Create'}
                                                    </button>
                                                    <button
                                                        type="button"
                                                        onClick={() => setShowCodexHomeCreator(false)}
                                                        disabled={addingCodexHome}
                                                        className="rounded-md border border-gray-300 bg-white px-3 py-2 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-300 dark:hover:bg-gray-900"
                                                    >
                                                        Cancel
                                                    </button>
                                                </div>
                                            </div>
                                        </div>
                                    )}

                                    {addCodexHomeMessage && (
                                        <div className={`rounded-md border px-3 py-2 text-[11px] ${
                                            addCodexHomeMessage.kind === 'success'
                                                ? 'border-green-200 bg-green-50 text-green-700 dark:border-green-800 dark:bg-green-900/20 dark:text-green-300'
                                                : addCodexHomeMessage.kind === 'error'
                                                    ? 'border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300'
                                                    : 'border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-300'
                                        }`}>
                                            {addCodexHomeMessage.text}
                                        </div>
                                    )}

                                    {codexAccountHomes.length === 0 ? (
                                        <p className="text-xs text-gray-500 dark:text-gray-400">
                                            {codexTargetsLoading ? 'Loading account homes...' : 'No account-home targets found.'}
                                        </p>
                                    ) : (
                                        <div className="space-y-2.5">
                                            {codexAccountHomes.map((target) => {
                                                const targetKey = target.runtime_id || target.account_key || target.codex_home;
                                                const targetAction = codexTargetActionLoading[targetKey];
                                                const actionMessage = codexTargetActionMessages[targetKey];
                                                const errorCode = target.last_probe_error_code || target.last_error_code;
                                                const statusMeta = codexStatusMeta(target);
                                                const StatusIcon = statusMeta.icon;
                                                const scopeMeta = codexScopeMeta(target);
                                                const ScopeIcon = scopeMeta.icon;
                                                const tokenState = target.has_refresh
                                                    ? 'refresh token present'
                                                    : target.has_access
                                                        ? 'access token only'
                                                        : 'no token material';
                                                const homeName = target.codex_home.split('/').filter(Boolean).slice(-1)[0] || target.codex_home;
                                                return (
                                                    <div
                                                        key={targetKey}
                                                        className={`rounded-md border p-3 ${statusMeta.row}`}
                                                    >
                                                        <div className="grid gap-3 lg:grid-cols-[minmax(0,1.7fr)_minmax(150px,0.65fr)_minmax(170px,0.75fr)_auto] lg:items-start">
                                                            <div className="min-w-0 space-y-1">
                                                                <div className="flex flex-wrap items-center gap-2">
                                                                    <div className="truncate text-sm font-semibold text-gray-900 dark:text-gray-100">
                                                                        {target.login_email || target.runtime_id}
                                                                    </div>
                                                                    <span className="rounded-full border border-gray-200 bg-white px-2 py-0.5 text-[11px] font-mono text-gray-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-400">
                                                                        {homeName}
                                                                    </span>
                                                                </div>
                                                                <div className="font-mono text-[11px] text-gray-500 dark:text-gray-400">
                                                                    {shortRuntimeId(target.runtime_id)}
                                                                </div>
                                                                {target.account_key && (
                                                                    <div className="font-mono text-[11px] text-gray-600 dark:text-gray-300" title={target.account_key}>
                                                                        account_key {shortKey(target.account_key)}
                                                                    </div>
                                                                )}
                                                            </div>

                                                            <div className={`inline-flex min-w-0 items-center gap-2 rounded-md border px-2.5 py-2 text-xs ${scopeMeta.badge}`}>
                                                                <ScopeIcon className="h-4 w-4 shrink-0" />
                                                                <div className="min-w-0">
                                                                    <div className="truncate font-semibold">
                                                                        {scopeMeta.label}
                                                                    </div>
                                                                    <div className="truncate text-[11px] opacity-80">
                                                                        {scopeMeta.sublabel}
                                                                    </div>
                                                                </div>
                                                            </div>

                                                            <div className={`inline-flex min-w-0 items-center gap-2 rounded-md border px-2.5 py-2 text-xs ${statusMeta.badge}`}>
                                                                <StatusIcon className="h-4 w-4 shrink-0" />
                                                                <div className="min-w-0">
                                                                    <div className="truncate font-semibold">
                                                                        {statusMeta.label}
                                                                    </div>
                                                                    <div className="truncate text-[11px] opacity-80">
                                                                        {statusMeta.detail}
                                                                    </div>
                                                                </div>
                                                            </div>

                                                            <div className="flex items-center gap-1.5 lg:justify-end">
                                                                <button
                                                                    type="button"
                                                                    onClick={() => handleAgentAuthAction('codex', 'login', target)}
                                                                    disabled={!!targetAction}
                                                                    className="px-3 py-1.5 text-xs font-medium rounded-md bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
                                                                >
                                                                    {targetAction === 'login' ? 'Logging in...' : 'Login'}
                                                                </button>
                                                                <button
                                                                    type="button"
                                                                    onClick={() => handleAgentAuthAction('codex', 'logout', target)}
                                                                    disabled={!!targetAction}
                                                                    className="px-3 py-1.5 text-xs font-medium rounded-md border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-300 dark:hover:bg-gray-800"
                                                                >
                                                                    {targetAction === 'logout' ? 'Logging out...' : 'Logout'}
                                                                </button>
                                                            </div>
                                                        </div>
                                                        <div className="mt-3 grid gap-2 text-[11px] text-gray-500 dark:text-gray-400 sm:grid-cols-2 lg:grid-cols-4">
                                                            <span>
                                                                {tokenState}
                                                            </span>
                                                            {target.last_probe_success_at && (
                                                                <span>
                                                                    passed {target.last_probe_success_at}
                                                                </span>
                                                            )}
                                                            {errorCode && (
                                                                <span className="text-amber-700 dark:text-amber-300">
                                                                    error {errorCode}
                                                                </span>
                                                            )}
                                                            {target.cooldown_until && (
                                                                <span>
                                                                    cooldown {target.cooldown_until}
                                                                </span>
                                                            )}
                                                            {target.account_organization_id && (
                                                                <span className="truncate font-mono" title={target.account_organization_id}>
                                                                    org {shortKey(target.account_organization_id)}
                                                                </span>
                                                            )}
                                                        </div>
                                                        {actionMessage && (
                                                            <div className={`mt-3 rounded-md border px-3 py-2 text-[11px] ${
                                                                actionMessage.kind === 'success'
                                                                    ? 'border-green-200 bg-green-50 text-green-700 dark:border-green-800 dark:bg-green-900/20 dark:text-green-300'
                                                                    : actionMessage.kind === 'error'
                                                                        ? 'border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300'
                                                                        : 'border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-300'
                                                            }`}>
                                                                {actionMessage.text}
                                                            </div>
                                                        )}
                                                    </div>
                                                );
                                            })}
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
                    CLI Agent Authentication
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
                                    <span className="text-green-600 dark:text-green-400">Saved</span>
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
