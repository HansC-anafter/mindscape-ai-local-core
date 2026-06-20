'use client';

import React, { useCallback, useMemo, useState } from 'react';

import { ApiKeyPane } from './cliApiKeys/ApiKeyPane';
import { GcaPoolPane } from './cliApiKeys/GcaPoolPane';
import { HostSessionPane } from './cliApiKeys/HostSessionPane';
import { ModeSwitcher } from './cliApiKeys/ModeSwitcher';
import { useCliApiKeysSettingsController } from './cliApiKeys/useCliApiKeysSettingsController';
import { useCodexAccountHomesController } from './cliApiKeys/useCodexAccountHomesController';
import {
    CLI_AGENTS,
    AgentTab,
    CliAgent,
} from './cliApiKeys/types';

interface CliApiKeysSectionProps {
    workspaceId?: string;
    initialAgentTab?: AgentTab;
}

export default function CliApiKeysSection({ workspaceId, initialAgentTab = 'gemini' }: CliApiKeysSectionProps) {
    const [error, setError] = useState<string | null>(null);
    const agentMap = useMemo(
        () => Object.fromEntries(CLI_AGENTS.map((agent) => [agent.id, agent])) as Record<AgentTab, CliAgent>,
        []
    );

    const codexController = useCodexAccountHomesController({
        agentMap,
        setError,
        workspaceId,
    });
    const settingsController = useCliApiKeysSettingsController({
        initialAgentTab,
        loadAgentAuthStatus: codexController.loadAgentAuthStatus,
        loadCodexAccountHomes: codexController.loadCodexAccountHomes,
        loadWorkspaceAgents: codexController.loadWorkspaceAgents,
        setError,
        workspaceId,
    });

    const {
        activeTab,
        addingAccount,
        agentModel,
        agentModes,
        boundGcaRuntimeId,
        configuredKeys,
        connectedCount,
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
    } = settingsController;
    const {
        addCodexHomeMessage,
        addingCodexHome,
        authStatusLoading,
        authStatuses,
        codexAccountHomes,
        codexTargetActionLoading,
        codexTargetActionMessages,
        codexTargetsLoading,
        generateCodexHomePath,
        handleAddCodexHome,
        handleAgentAuthAction,
        handleCodexProbe,
        handleDeleteCodexHome,
        loadAgentAuthStatus,
        loadCodexAccountHomes,
        newCodexHome,
        openCodexHomeCreator,
        setNewCodexHome,
        setShowCodexHomeCreator,
        showCodexHomeCreator,
        workspaceAgents,
    } = codexController;

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
                        className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                            activeTab === agent.id
                                ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                                : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
                        }`}
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
                    <ModeSwitcher
                        activeMode={activeMode}
                        agent={activeAgent}
                        onModeChange={(mode) => handleModeChange(activeAgent, mode)}
                    />

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
                                    className="px-2 py-0.5 text-xs rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:opacity-50"
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
                {activeMode === 'api' && (
                    <ApiKeyPane
                        agent={activeAgent}
                        configured={!!configuredKeys[activeAgent.settingsKey]}
                        saved={saved === activeAgent.settingsKey}
                        saving={saving === activeAgent.settingsKey}
                        showKey={!!showKey[activeAgent.id]}
                        value={values[activeAgent.settingsKey] || ''}
                        onSave={() => handleSave(activeAgent)}
                        onToggleShowKey={() =>
                            setShowKey((prev) => ({
                                ...prev,
                                [activeAgent.id]: !prev[activeAgent.id],
                            }))
                        }
                        onValueChange={(value) =>
                            setValues((prev) => ({
                                ...prev,
                                [activeAgent.settingsKey]: value,
                            }))
                        }
                    />
                )}
                {activeTab === 'codex' && activeMode === 'host_session' && (
                    <HostSessionPane
                        addCodexHomeMessage={addCodexHomeMessage}
                        addingCodexHome={addingCodexHome}
                        agent={activeAgent}
                        codexAccountHomes={codexAccountHomes}
                        codexTargetActionLoading={codexTargetActionLoading}
                        codexTargetActionMessages={codexTargetActionMessages}
                        codexTargetsLoading={codexTargetsLoading}
                        loading={!!authStatusLoading[activeAgent.id]}
                        newCodexHome={newCodexHome}
                        runtimeInfo={activeAgent.runtimeAgentId ? workspaceAgents[activeAgent.runtimeAgentId] : null}
                        showCodexHomeCreator={showCodexHomeCreator}
                        status={authStatuses[activeAgent.id]}
                        workspaceId={workspaceId}
                        onAddCodexHome={handleAddCodexHome}
                        onAgentAuthAction={handleAgentAuthAction}
                        onCancelCodexHomeCreator={() => setShowCodexHomeCreator(false)}
                        onCodexProbe={handleCodexProbe}
                        onDeleteCodexHome={handleDeleteCodexHome}
                        onGenerateCodexHome={generateCodexHomePath}
                        onLoadAgentAuthStatus={loadAgentAuthStatus}
                        onLoadCodexAccountHomes={loadCodexAccountHomes}
                        onNewCodexHomeChange={setNewCodexHome}
                        onOpenCodexHomeCreator={openCodexHomeCreator}
                    />
                )}
                {activeTab === 'claude' && activeMode === 'host_token' && (
                    <HostSessionPane
                        addCodexHomeMessage={null}
                        addingCodexHome={false}
                        agent={activeAgent}
                        codexAccountHomes={[]}
                        codexTargetActionLoading={{}}
                        codexTargetActionMessages={{}}
                        codexTargetsLoading={false}
                        loading={!!authStatusLoading[activeAgent.id]}
                        newCodexHome=""
                        runtimeInfo={activeAgent.runtimeAgentId ? workspaceAgents[activeAgent.runtimeAgentId] : null}
                        showCodexHomeCreator={false}
                        status={authStatuses[activeAgent.id]}
                        workspaceId={workspaceId}
                        onAddCodexHome={() => undefined}
                        onAgentAuthAction={handleAgentAuthAction}
                        onCancelCodexHomeCreator={() => undefined}
                        onCodexProbe={handleCodexProbe}
                        onDeleteCodexHome={handleDeleteCodexHome}
                        onGenerateCodexHome={() => undefined}
                        onLoadAgentAuthStatus={loadAgentAuthStatus}
                        onLoadCodexAccountHomes={loadCodexAccountHomes}
                        onNewCodexHomeChange={() => undefined}
                        onOpenCodexHomeCreator={() => undefined}
                    />
                )}

                {error && (
                    <p className="text-xs text-red-600 dark:text-red-400">{error}</p>
                )}
            </div>
        </div>
    );
}
