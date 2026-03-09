'use client';

import React, { useState, useEffect, useCallback } from 'react';
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

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

interface CliAgent {
    id: string;
    label: string;
    settingsKey: string;           // system_settings key
    placeholder: string;
    guideUrl: string;
    guideSteps: string[];
    icon: string;                  // emoji
    authModeValue?: string;        // value for gemini_cli_auth_mode
}

/** Auth tab type — either an API-key agent or the GCA OAuth flow */
type AuthTab = 'gca' | 'gemini' | 'claude' | 'codex';

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

/* ------------------------------------------------------------------ */
/* Agent definitions                                                   */
/* ------------------------------------------------------------------ */

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
        authModeValue: 'gemini_api_key',
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
    },
];

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

interface CliApiKeysSectionProps {
    workspaceId?: string;
}

export default function CliApiKeysSection({ workspaceId }: CliApiKeysSectionProps) {
    const [activeTab, setActiveTab] = useState<AuthTab>('gemini');
    const [values, setValues] = useState<Record<string, string>>({});
    const [saving, setSaving] = useState<string | null>(null);
    const [saved, setSaved] = useState<string | null>(null);
    const [showKey, setShowKey] = useState<Record<string, boolean>>({});
    const [error, setError] = useState<string | null>(null);

    // Agent model state
    const [agentModel, setAgentModel] = useState<string>('gemini-3-pro');
    const [savingModel, setSavingModel] = useState(false);
    const [savedModel, setSavedModel] = useState(false);

    // GCA pool state
    const [poolAccounts, setPoolAccounts] = useState<PoolAccount[]>([]);
    const [addingAccount, setAddingAccount] = useState(false);
    const [pendingRuntimeId, setPendingRuntimeId] = useState<string | null>(null);
    const [currentAuthMode, setCurrentAuthMode] = useState<string>('gemini_api_key');
    const [executorRuntimeId, setExecutorRuntimeId] = useState<string | null>(null);
    const [boundGcaRuntimeId, setBoundGcaRuntimeId] = useState<string>('');
    const [workspaceGcaStatus, setWorkspaceGcaStatus] = useState<WorkspaceGcaStatus | null>(null);
    const [savingBinding, setSavingBinding] = useState(false);
    const [savedBinding, setSavedBinding] = useState(false);

    const loadSettings = useCallback(async () => {
        try {
            const base = getApiBaseUrl();
            const resp = await fetch(
                `${base}/api/v1/system-settings/category/gemini_cli`
            );
            if (!resp.ok) return;
            const settings: Array<{ key: string; value: string }> = await resp.json();
            const map: Record<string, string> = {};
            for (const s of settings) {
                if (s.key === 'gemini_cli_auth_mode') {
                    setCurrentAuthMode(s.value || 'gemini_api_key');
                }
                if (s.key === 'agent_cli_model') {
                    setAgentModel(s.value || 'gemini-3-pro');
                }
                if (s.value && s.value !== '***') {
                    map[s.key] = s.value;
                }
            }
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

    useEffect(() => {
        loadSettings();
        loadPoolAccounts();
        loadWorkspaceBinding();
        loadWorkspaceGcaStatus();

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
    }, [loadSettings, loadPoolAccounts, loadWorkspaceBinding, loadWorkspaceGcaStatus]);

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
            const base = getApiBaseUrl();
            // Save the API key
            const resp = await fetch(`${base}/api/v1/system-settings/${key}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ value: val }),
            });

            if (!resp.ok) {
                const errData = await resp.json().catch(() => ({}));
                throw new Error(
                    (errData as Record<string, string>).detail || 'Save failed'
                );
            }

            // If Gemini, also set auth_mode
            if (agent.authModeValue) {
                await fetch(
                    `${base}/api/v1/system-settings/gemini_cli_auth_mode`,
                    {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ value: agent.authModeValue }),
                    }
                );
                setCurrentAuthMode(agent.authModeValue);
            }

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
            await fetch(
                `${base}/api/v1/system-settings/gemini_cli_auth_mode`,
                {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ value: 'gca' }),
                }
            );
            setCurrentAuthMode('gca');

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
                const acct = poolAccounts.find(a => a.id === runtimeId);
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

    const activeAgent = CLI_AGENTS.find((a) => a.id === activeTab);

    const connectedCount = poolAccounts.filter(a => a.auth_status === 'connected').length;
    const savedBoundRuntimeId = workspaceGcaStatus?.policy_mode === 'pinned_runtime'
        ? (workspaceGcaStatus.preferred_runtime_id || '')
        : '';

    const allTabs: { id: AuthTab; label: string; icon: string; hasValue: boolean }[] = [
        {
            id: 'gca',
            label: `GCA Pool (${connectedCount})`,
            icon: '🔐',
            hasValue: connectedCount > 0,
        },
        ...CLI_AGENTS.map((a) => ({
            id: a.id as AuthTab,
            label: a.label,
            icon: a.icon,
            hasValue: !!values[a.settingsKey],
        })),
    ];

    return (
        <div className="mb-5">
            {/* Section header */}
            <div className="mb-3">
                <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100">
                    🔑 CLI Agent Authentication
                </h3>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                    Configure authentication for CLI agents. Choose Google Account (GCA)
                    for subscription-based access, or paste an API key for pay-per-token.
                </p>
            </div>


            {/* Tabs */}
            <div className="flex border-b border-gray-200 dark:border-gray-700 mb-4">
                {allTabs.map((tab) => (
                    <button
                        key={tab.id}
                        onClick={() => {
                            setActiveTab(tab.id);
                            setError(null);
                        }}
                        className={`
                            flex items-center gap-1.5 px-4 py-2 text-sm font-medium
                            border-b-2 transition-colors
                            ${activeTab === tab.id
                                ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                                : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
                            }
                        `}
                    >
                        <span>{tab.icon}</span>
                        {tab.label}
                        {tab.hasValue && (
                            <span className="w-1.5 h-1.5 rounded-full bg-green-500 ml-1" />
                        )}
                    </button>
                ))}
            </div>

            {/* Active mode + model indicator (Gemini-specific, inside tab content) */}
            {(activeTab === 'gca' || activeTab === 'gemini') && (
                <div className="mb-3 flex items-center gap-4 text-xs flex-wrap">
                    <div className="flex items-center gap-2">
                        <span className="text-gray-500 dark:text-gray-400">Active mode:</span>
                        <span className="px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 font-medium">
                            {currentAuthMode === 'gca' ? 'Google Account (GCA)'
                                : currentAuthMode === 'gemini_api_key' ? 'Gemini API Key'
                                    : currentAuthMode === 'vertex_ai' ? 'Vertex AI'
                                        : currentAuthMode}
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
                                    const base = getApiBaseUrl();
                                    const resp = await fetch(
                                        `${base}/api/v1/system-settings/agent_cli_model`,
                                        {
                                            method: 'PUT',
                                            headers: { 'Content-Type': 'application/json' },
                                            body: JSON.stringify({ value: newModel }),
                                        }
                                    );
                                    if (resp.ok) {
                                        setSavedModel(true);
                                        setTimeout(() => setSavedModel(false), 2000);
                                    }
                                } catch { /* ignore */ }
                                finally { setSavingModel(false); }
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

            {/* Active tab content */}
            <div className="space-y-4">
                {activeTab === 'gca' ? (
                    <>
                        {/* Pool info */}
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

                        {/* Account list */}
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
                                        {/* Status dot */}
                                        <span className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${isPending ? 'bg-amber-400 animate-pulse'
                                            : isCooling ? 'bg-amber-500'
                                                : acct.auth_status === 'connected' ? 'bg-green-500'
                                                    : 'bg-gray-400'
                                            }`} />

                                        {/* Account info */}
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

                                        {/* Actions */}
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

                        {/* Add account button */}
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
                ) : activeAgent ? (
                    /* ---- API Key Tabs ---- */
                    <>
                        {/* Guide */}
                        <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-3">
                            <p className="text-xs font-medium text-blue-700 dark:text-blue-300 mb-2">
                                How to get your {activeAgent.label} API Key:
                            </p>
                            <ol className="list-decimal list-inside space-y-1">
                                {activeAgent.guideSteps.map((step, i) => (
                                    <li
                                        key={i}
                                        className="text-xs text-blue-600 dark:text-blue-400"
                                    >
                                        {i === 0 ? (
                                            <>
                                                <a
                                                    href={activeAgent.guideUrl}
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

                        {/* Input */}
                        <div>
                            <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                                {activeAgent.label} API Key
                            </label>
                            <div className="flex gap-2">
                                <div className="relative flex-1">
                                    <input
                                        type={showKey[activeAgent.id] ? 'text' : 'password'}
                                        value={values[activeAgent.settingsKey] || ''}
                                        onChange={(e) =>
                                            setValues((prev) => ({
                                                ...prev,
                                                [activeAgent.settingsKey]: e.target.value,
                                            }))
                                        }
                                        placeholder={activeAgent.placeholder}
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
                                                [activeAgent.id]: !prev[activeAgent.id],
                                            }))
                                        }
                                        className="absolute right-2 top-1/2 -translate-y-1/2
                                            text-gray-400 hover:text-gray-600 dark:hover:text-gray-300
                                            text-xs"
                                    >
                                        {showKey[activeAgent.id] ? 'Hide' : 'Show'}
                                    </button>
                                </div>
                                <button
                                    onClick={() => handleSave(activeAgent)}
                                    disabled={saving === activeAgent.settingsKey}
                                    className={`
                                        px-4 py-2 text-sm font-medium rounded-md transition-colors
                                        ${saved === activeAgent.settingsKey
                                            ? 'bg-green-600 text-white'
                                            : 'bg-blue-600 hover:bg-blue-700 text-white'
                                        }
                                        disabled:opacity-50 disabled:cursor-not-allowed
                                        min-w-[70px]
                                    `}
                                >
                                    {saving === activeAgent.settingsKey
                                        ? '...'
                                        : saved === activeAgent.settingsKey
                                            ? '✓'
                                            : 'Save'}
                                </button>
                            </div>
                        </div>

                        {/* Status indicator */}
                        {values[activeAgent.settingsKey] && (
                            <div className="flex items-center gap-1.5 text-xs text-green-600 dark:text-green-400">
                                <span className="w-2 h-2 rounded-full bg-green-500" />
                                API key configured (global scope)
                            </div>
                        )}
                    </>
                ) : null}

                {/* Error */}
                {error && (
                    <p className="text-xs text-red-600 dark:text-red-400">{error}</p>
                )}
            </div>
        </div>
    );
}
