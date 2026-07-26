'use client';

import React from 'react';
import { useT } from '../../../../lib/i18n';
import { AVAILABLE_AGENTS } from './aiTeamGovernancePanelData';
import type { AgentMarketplaceProps, RiskTag } from './aiTeamGovernancePanelTypes';

function getRiskTagColor(color: RiskTag['color']): string {
    switch (color) {
        case 'green':
            return 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300 border-green-200 dark:border-green-800';
        case 'yellow':
            return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300 border-yellow-200 dark:border-yellow-800';
        case 'orange':
            return 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300 border-orange-200 dark:border-orange-800';
        case 'red':
            return 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300 border-red-200 dark:border-red-800';
        default:
            return 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300';
    }
}

export function AgentMarketplace({ onInstall, onConfigure, onSendToAssistant }: AgentMarketplaceProps) {
  const t = useT();
    const [installing] = React.useState<string | null>(null);

    const handleInstall = (agentId: string, agentName: string) => {
        if (onSendToAssistant) {
            onSendToAssistant(`Help me install ${agentName}`);
        } else {
            onInstall?.(agentId);
        }
    };

    const handleConfigure = (agentId: string, agentName: string) => {
        if (onSendToAssistant) {
            onSendToAssistant(`Help me configure ${agentName}`);
        } else {
            onConfigure?.(agentId);
        }
    };

    return (
        <div className="space-y-6">
            <div>
                <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
                    {t('installAgents' as any) || 'Install AI Agents'}
                </h3>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
                    {t('installAgentsDescription' as any) || 'Browse and install common AI agent frameworks'}
                </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {AVAILABLE_AGENTS.map((agent) => (
                    <div
                        key={agent.id}
                        className="border dark:border-gray-700 rounded-lg p-4 hover:border-accent dark:hover:border-purple-500 transition-colors bg-white dark:bg-gray-800"
                    >
                        <div className="flex items-start justify-between mb-2">
                            <div className="flex items-center gap-2">
                                <span className="flex h-8 w-8 items-center justify-center rounded bg-gray-100 text-xs font-semibold text-gray-700 dark:bg-gray-700 dark:text-gray-200">
                                    {agent.icon}
                                </span>
                                <h4 className="font-medium text-gray-900 dark:text-gray-100">
                                    {agent.name}
                                </h4>
                            </div>
                            {agent.status === 'installed' && (
                                <span className="text-xs px-2 py-1 bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300 rounded">
                                    Installed
                                </span>
                            )}
                            {agent.status === 'built-in' && (
                                <span className="text-xs px-2 py-1 bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300 rounded">
                                    Built in
                                </span>
                            )}
                            {agent.status === 'coming-soon' && (
                                <span className="text-xs px-2 py-1 bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400 rounded">
                                    Coming soon
                                </span>
                            )}
                        </div>

                        <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                            {agent.description}
                        </p>

                        <div className="p-2 bg-gray-50 dark:bg-gray-900/50 rounded-lg mb-3">
                            <div className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
                                {agent.status === 'built-in' ? 'Safety Features' : 'Risk Tags'}
                            </div>
                            <div className="flex flex-wrap gap-1">
                                {agent.riskTags.map((tag, idx) => (
                                    <span
                                        key={idx}
                                        className={`text-xs px-2 py-0.5 rounded border ${getRiskTagColor(tag.color)}`}
                                    >
                                        {tag.label}
                                    </span>
                                ))}
                            </div>
                        </div>

                        <div className="flex flex-wrap gap-1 mb-3">
                            {agent.features.map((feature, idx) => (
                                <span
                                    key={idx}
                                    className="text-xs px-2 py-0.5 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 rounded"
                                >
                                    {feature}
                                </span>
                            ))}
                        </div>

                        <div className="text-xs text-gray-500 dark:text-gray-500 mb-3">
                            Requirements: {agent.requirements.join(', ')}
                        </div>

                        <div className="flex gap-2">
                            {agent.status === 'built-in' ? (
                                <button
                                    onClick={() => onConfigure?.(agent.id)}
                                    className="flex-1 px-3 py-1.5 text-sm border border-purple-400 text-purple-600 dark:border-purple-500 dark:text-purple-300 rounded hover:bg-purple-50 dark:hover:bg-purple-900/30 transition-colors"
                                >
                                    View Settings
                                </button>
                            ) : agent.status === 'installed' ? (
                                <button
                                    onClick={() => handleConfigure(agent.id, agent.name)}
                                    className="flex-1 px-3 py-1.5 text-sm border border-accent text-accent dark:border-purple-500 dark:text-purple-300 rounded hover:bg-accent-10 dark:hover:bg-purple-900/30 transition-colors"
                                >
                                    Configure
                                </button>
                            ) : agent.status === 'available' ? (
                                <button
                                    onClick={() => handleInstall(agent.id, agent.name)}
                                    disabled={installing === agent.id}
                                    className="flex-1 px-3 py-1.5 text-sm bg-accent text-white dark:bg-purple-600 rounded hover:bg-accent-hover dark:hover:bg-purple-700 transition-colors disabled:opacity-50"
                                >
                                    {installing === agent.id ? 'Installing...' : 'Install'}
                                </button>
                            ) : (
                                <button
                                    disabled
                                    className="flex-1 px-3 py-1.5 text-sm bg-gray-200 text-gray-500 dark:bg-gray-700 dark:text-gray-500 rounded cursor-not-allowed"
                                >
                                    Coming soon
                                </button>
                            )}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}

export function InstalledAgentsList() {
  const t = useT();
    const installedAgents = AVAILABLE_AGENTS.filter(a => a.status === 'installed');

    return (
        <div className="space-y-6">
            <div>
                <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
                    {t('installedAgents' as any) || 'Installed Agents'}
                </h3>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
                    {t('installedAgentsDescription' as any) || 'Manage installed AI agents and inspect their status'}
                </p>
            </div>

            {installedAgents.length === 0 ? (
                <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                    <p className="text-sm">No AI agents are installed yet</p>
                    <p className="text-xs mt-1">Open Install AI Agents to get started</p>
                </div>
            ) : (
                <div className="space-y-3">
                    {installedAgents.map((agent) => (
                        <div
                            key={agent.id}
                            className="flex items-center justify-between p-4 border dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800"
                        >
                            <div className="flex items-center gap-3">
                                <span className="flex h-8 w-8 items-center justify-center rounded bg-gray-100 text-xs font-semibold text-gray-700 dark:bg-gray-700 dark:text-gray-200">
                                    {agent.icon}
                                </span>
                                <div>
                                    <h4 className="font-medium text-gray-900 dark:text-gray-100">
                                        {agent.name}
                                    </h4>
                                    <p className="text-xs text-gray-500 dark:text-gray-400">
                                        {agent.description}
                                    </p>
                                </div>
                            </div>
                            <div className="flex items-center gap-2">
                                <span className="text-xs px-2 py-1 bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300 rounded">
                                    Running
                                </span>
                                <button className="px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
                                    Configure
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
