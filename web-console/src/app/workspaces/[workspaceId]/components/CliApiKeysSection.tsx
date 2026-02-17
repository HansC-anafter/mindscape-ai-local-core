'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { getApiBaseUrl } from '@/lib/api-url';

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

export default function CliApiKeysSection() {
    const [activeTab, setActiveTab] = useState<AuthTab>('gemini');
    const [values, setValues] = useState<Record<string, string>>({});
    const [saving, setSaving] = useState<string | null>(null);
    const [saved, setSaved] = useState<string | null>(null);
    const [showKey, setShowKey] = useState<Record<string, boolean>>({});
    const [error, setError] = useState<string | null>(null);

    // GCA-specific state
    const [gcaStatus, setGcaStatus] = useState<'disconnected' | 'pending' | 'connected' | 'error'>('disconnected');
    const [gcaEmail, setGcaEmail] = useState<string | null>(null);
    const [gcaRuntimeId, setGcaRuntimeId] = useState<string | null>(null);
    const [currentAuthMode, setCurrentAuthMode] = useState<string>('gemini_api_key');

    // Load current values from backend
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
                // Sensitive values come back as "***" — preserve as placeholder
                if (s.value && s.value !== '***') {
                    map[s.key] = s.value;
                }
            }
            setValues((prev) => ({ ...prev, ...map }));
        } catch {
            // Silently ignore — form still works with empty values
        }
    }, []);

    // Load GCA auth status from dedicated gca-local runtime
    const loadGcaStatus = useCallback(async () => {
        try {
            const base = getApiBaseUrl();
            const resp = await fetch(`${base}/api/v1/runtime-environments`);
            if (!resp.ok) return;
            const data = await resp.json();
            const runtimes: Array<Record<string, any>> = data.runtimes || [];
            // Use the dedicated gca-local runtime (never touch site-hub)
            const gcaRuntime = runtimes.find(
                (r: Record<string, any>) => r.id === 'gca-local'
            );
            if (gcaRuntime) {
                setGcaRuntimeId(gcaRuntime.id);
                setGcaStatus(gcaRuntime.auth_status || 'disconnected');
                setGcaEmail(gcaRuntime.auth_identity || null);
            } else {
                setGcaRuntimeId('gca-local');
                setGcaStatus('disconnected');
            }
        } catch {
            // Ignore — GCA section will show disconnected
        }
    }, []);

    useEffect(() => {
        loadSettings();
        loadGcaStatus();

        // Listen for OAuth popup result
        const handleOAuthMessage = (event: MessageEvent) => {
            if (event.data?.type === 'RUNTIME_OAUTH_RESULT') {
                loadGcaStatus();
                loadSettings();
            }
        };
        window.addEventListener('message', handleOAuthMessage);
        return () => window.removeEventListener('message', handleOAuthMessage);
    }, [loadSettings, loadGcaStatus]);

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
            const resp = await fetch(`${base}/api/v1/system-settings/${key}?value=${encodeURIComponent(val)}`, {
                method: 'PUT',
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
                    `${base}/api/v1/system-settings/gemini_cli_auth_mode?value=${encodeURIComponent(agent.authModeValue)}`,
                    { method: 'PUT' }
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

    /** Set auth_mode to gca and open OAuth popup */
    const handleGcaConnect = async () => {
        setError(null);
        const base = getApiBaseUrl();

        // Set auth_mode to gca
        try {
            await fetch(
                `${base}/api/v1/system-settings/gemini_cli_auth_mode?value=gca`,
                { method: 'PUT' }
            );
            setCurrentAuthMode('gca');
        } catch {
            setError('Failed to set auth mode');
            return;
        }

        // Open OAuth popup for the dedicated gca-local runtime
        const runtimeId = 'gca-local';
        setGcaRuntimeId(runtimeId);

        // Open OAuth popup
        const w = 500, h = 600;
        const left = window.screenX + (window.innerWidth - w) / 2;
        const top = window.screenY + (window.innerHeight - h) / 2;
        window.open(
            `${base}/api/v1/runtime-oauth/${runtimeId}/authorize`,
            'oauth-popup',
            `width=${w},height=${h},left=${left},top=${top},popup=true`
        );

        setGcaStatus('pending');
        // Poll for auth completion
        const pollInterval = setInterval(async () => {
            await loadGcaStatus();
        }, 2000);
        // Stop polling after 5 minutes
        setTimeout(() => clearInterval(pollInterval), 300000);
    };

    /** Disconnect GCA auth */
    const handleGcaDisconnect = async () => {
        if (!gcaRuntimeId) return;
        setError(null);
        const base = getApiBaseUrl();
        try {
            await fetch(
                `${base}/api/v1/runtime-oauth/${gcaRuntimeId}/disconnect`,
                { method: 'POST' }
            );
            setGcaStatus('disconnected');
            setGcaEmail(null);
            loadGcaStatus();
        } catch {
            setError('Failed to disconnect');
        }
    };

    const activeAgent = CLI_AGENTS.find((a) => a.id === activeTab);

    // All tabs: GCA first, then API key agents
    const allTabs: { id: AuthTab; label: string; icon: string; hasValue: boolean }[] = [
        {
            id: 'gca',
            label: 'Google Account',
            icon: '🔐',
            hasValue: gcaStatus === 'connected',
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

            {/* Active mode indicator */}
            <div className="mb-3 flex items-center gap-2 text-xs">
                <span className="text-gray-500 dark:text-gray-400">Active mode:</span>
                <span className="px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 font-medium">
                    {currentAuthMode === 'gca' ? 'Google Account (GCA)'
                        : currentAuthMode === 'gemini_api_key' ? 'Gemini API Key'
                            : currentAuthMode === 'vertex_ai' ? 'Vertex AI'
                                : currentAuthMode}
                </span>
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

            {/* Active tab content */}
            <div className="space-y-4">
                {activeTab === 'gca' ? (
                    /* ---- GCA OAuth Tab ---- */
                    <>
                        {/* Guide */}
                        <div className="bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800 rounded-lg p-3">
                            <p className="text-xs font-medium text-emerald-700 dark:text-emerald-300 mb-2">
                                Google Account (GCA) — Subscription Mode
                            </p>
                            <ul className="space-y-1 text-xs text-emerald-600 dark:text-emerald-400">
                                <li>• Uses your Google account with Gemini CLI subscription</li>
                                <li>• No API key needed — authenticates via OAuth</li>
                                <li>• Runs on provisioned throughput (subscription quota, not per-token billing)</li>
                                <li>• Token stays on this device</li>
                            </ul>
                        </div>

                        {/* Connect / Status */}
                        <div className="flex items-center gap-3">
                            {gcaStatus === 'connected' ? (
                                <>
                                    <div className="flex items-center gap-2 flex-1">
                                        <span className="w-2.5 h-2.5 rounded-full bg-green-500" />
                                        <span className="text-sm text-green-700 dark:text-green-400 font-medium">
                                            Connected
                                        </span>
                                        {gcaEmail && (
                                            <span className="text-xs text-gray-500 dark:text-gray-400">
                                                ({gcaEmail})
                                            </span>
                                        )}
                                    </div>
                                    <button
                                        type="button"
                                        onClick={handleGcaDisconnect}
                                        className="text-xs px-3 py-1.5 rounded-md border border-red-300 dark:border-red-700 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                                    >
                                        Disconnect
                                    </button>
                                </>
                            ) : gcaStatus === 'pending' ? (
                                <div className="flex items-center gap-2 text-sm text-amber-600 dark:text-amber-400">
                                    <span className="animate-pulse">⌛</span>
                                    Waiting for authentication...
                                </div>
                            ) : (
                                <button
                                    type="button"
                                    onClick={handleGcaConnect}
                                    className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-md bg-blue-600 text-white hover:bg-blue-700 transition-colors"
                                >
                                    <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
                                        <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" />
                                        <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                                        <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
                                        <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
                                    </svg>
                                    Connect with Google
                                </button>
                            )}
                        </div>
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
