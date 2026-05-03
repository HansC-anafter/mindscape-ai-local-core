'use client';

import React from 'react';
import { t } from '../../../../lib/i18n';

/**
 * Risk tag definition
 */
interface RiskTag {
    label: string;
    color: 'green' | 'yellow' | 'orange' | 'red';
    icon?: string;
}

/**
 * Agent definition for marketplace display
 */
interface AgentDefinition {
    id: string;
    name: string;
    icon: string;
    description: string;
    status: 'available' | 'installed' | 'coming-soon' | 'built-in';
    riskTags: RiskTag[];
    requirements: string[];
    features: string[];
}

/**
 * Available agents in the marketplace
 */
const AVAILABLE_AGENTS: AgentDefinition[] = [
    {
        id: 'mindscape-core',
        name: 'Mindscape Core',
        icon: 'MS',
        description: 'Built-in Mindscape AI execution engine with playbook, tool-calling, and model-routing support',
        status: 'built-in',
        riskTags: [
            { label: 'Built in', color: 'green' },
            { label: 'Governance controlled', color: 'green' },
            { label: 'Built-in tool access', color: 'green' },
        ],
        requirements: ['Built in'],
        features: ['Playbook execution', 'Tool calling', 'Model routing', 'Conversation memory', 'Workflow orchestration'],
    },
    {
        id: 'openclaw',
        name: 'OpenClaw',
        icon: 'OC',
        description: 'Lightweight local CLI Agent for quick tasks',
        status: 'installed',
        riskTags: [
            { label: 'Sandbox isolated', color: 'green' },
            { label: 'Local only', color: 'green' },
        ],
        requirements: ['Python 3.10+', 'pip'],
        features: ['Shell execution', 'File operations', 'Code generation'],
    },
    {
        id: 'langgraph',
        name: 'LangGraph',
        icon: 'LG',
        description: 'LangChain Graph Agent for complex workflows',
        status: 'available',
        riskTags: [
            { label: 'API key required', color: 'yellow' },
            { label: 'Network capable', color: 'yellow' },
            { label: 'Tool calling', color: 'orange' },
        ],
        requirements: ['Python 3.10+', 'Docker'],
        features: ['Multi-step reasoning', 'State management', 'Tool calling'],
    },
    {
        id: 'crewai',
        name: 'CrewAI',
        icon: 'CA',
        description: 'Multi-agent collaboration framework',
        status: 'available',
        riskTags: [
            { label: 'Multi-agent interaction', color: 'yellow' },
            { label: 'API key required', color: 'yellow' },
            { label: 'Task delegation', color: 'orange' },
        ],
        requirements: ['Python 3.10+', 'Docker'],
        features: ['Role assignment', 'Task delegation', 'Collaborative execution'],
    },
    {
        id: 'autogpt',
        name: 'AutoGPT',
        icon: 'AG',
        description: 'Autonomous task execution agent',
        status: 'available',
        riskTags: [
            { label: 'Autonomous decisions', color: 'red' },
            { label: 'Long-running execution', color: 'orange' },
            { label: 'Network search', color: 'yellow' },
            { label: 'File read/write', color: 'orange' },
        ],
        requirements: ['Python 3.10+', 'Docker', 'Redis'],
        features: ['Autonomous planning', 'Memory management', 'Network search'],
    },
    {
        id: 'open-interpreter',
        name: 'Open Interpreter',
        icon: 'OI',
        description: 'Code execution agent with natural language',
        status: 'available',
        riskTags: [
            { label: 'Arbitrary code execution', color: 'red' },
            { label: 'System access', color: 'red' },
            { label: 'No sandbox', color: 'red' },
        ],
        requirements: ['Python 3.10+'],
        features: ['Code execution', 'Multi-language support', 'REPL mode'],
    },
    {
        id: 'claude-computer-use',
        name: 'Claude Computer Use',
        icon: 'CU',
        description: 'Anthropic computer use capabilities',
        status: 'coming-soon',
        riskTags: [
            { label: 'GUI control', color: 'red' },
            { label: 'Mouse and keyboard input', color: 'red' },
            { label: 'Screen capture', color: 'orange' },
            { label: 'Anthropic API required', color: 'yellow' },
        ],
        requirements: ['Docker', 'Anthropic API'],
        features: ['Mouse control', 'Screen recognition', 'GUI operations'],
    },
];

interface AgentMarketplaceProps {
    onInstall?: (agentId: string) => void;
    onConfigure?: (agentId: string) => void;
    onSendToAssistant?: (message: string) => void;
}

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

/**
 * Agent Marketplace - Install AI Agents section
 */
export function AgentMarketplace({ onInstall, onConfigure, onSendToAssistant }: AgentMarketplaceProps) {
    const [installing, setInstalling] = React.useState<string | null>(null);

    // Chat-First: Trigger assistant chat instead of direct installation
    const handleInstall = (agentId: string, agentName: string) => {
        if (onSendToAssistant) {
            onSendToAssistant(`Help me install ${agentName}`);
        } else {
            // Fallback: call original onInstall if no assistant available
            onInstall?.(agentId);
        }
    };

    // Chat-First: Trigger assistant chat for configuration
    const handleConfigure = (agentId: string, agentName: string) => {
        if (onSendToAssistant) {
            onSendToAssistant(`Help me configure ${agentName}`);
        } else {
            onConfigure?.(agentId);
        }
    };

    // Chat-First: View settings via assistant
    const handleViewSettings = (agentName: string) => {
        if (onSendToAssistant) {
            onSendToAssistant(`Show settings for ${agentName}`);
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
                        {/* Header */}
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

                        {/* Description */}
                        <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                            {agent.description}
                        </p>

                        {/* Risk Tags Block */}
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

                        {/* Features */}
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

                        {/* Requirements */}
                        <div className="text-xs text-gray-500 dark:text-gray-500 mb-3">
                            Requirements: {agent.requirements.join(', ')}
                        </div>

                        {/* Actions */}
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

/**
 * Installed Agents - List of installed agents
 */
export function InstalledAgentsList() {
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

interface AITeamGovernancePanelProps {
    activeSection?: string;
    onSendToAssistant?: (message: string) => void;
}

/**
 * Main AI Team Governance Panel
 */
export function AITeamGovernancePanel({ activeSection, onSendToAssistant }: AITeamGovernancePanelProps) {
    const renderContent = () => {
        switch (activeSection) {
            case 'install-agents':
                return <AgentMarketplace onSendToAssistant={onSendToAssistant} />;
            case 'installed-agents':
                return <InstalledAgentsList />;
            case 'model-policy':
                return <ModelPolicySettings />;
            case 'network-policy':
                return <NetworkPolicySettings />;
            case 'secrets-policy':
                return <SecretsPolicySettings />;
            default:
                return <AgentMarketplace onSendToAssistant={onSendToAssistant} />;
        }
    };

    return (
        <div className="space-y-6">
            {renderContent()}
        </div>
    );
}

/**
 * Model Policy Settings
 */
function ModelPolicySettings() {
    const [allowedProviders, setAllowedProviders] = React.useState<string[]>(['ollama', 'llama-cpp']);
    const providers = [
        { id: 'ollama', name: 'Ollama', type: 'local', icon: 'OL' },
        { id: 'llama-cpp', name: 'llama.cpp', type: 'local', icon: 'LC' },
        { id: 'openai', name: 'OpenAI', type: 'cloud', icon: 'OA' },
        { id: 'anthropic', name: 'Anthropic', type: 'cloud', icon: 'AN' },
        { id: 'vertex-ai', name: 'Vertex AI', type: 'cloud', icon: 'VX' },
    ];

    const toggleProvider = (id: string) => {
        setAllowedProviders(prev =>
            prev.includes(id) ? prev.filter(p => p !== id) : [...prev, id]
        );
    };

    const isLocalOnly = allowedProviders.every(p =>
        providers.find(pr => pr.id === p)?.type === 'local'
    );

    return (
        <div className="space-y-6">
            <div>
                <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
                    {t('modelPolicy' as any) || 'Model Policy'}
                </h3>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
                    {t('modelPolicyDescription' as any) || 'Configure the allowlist of model providers available to external agents.'}
                </p>
            </div>

            {isLocalOnly && (
                <div className="p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg">
                    <div className="flex items-center gap-2 text-green-800 dark:text-green-300">
                        <span className="text-sm font-medium">Local-only mode is enabled</span>
                    </div>
                    <p className="text-xs text-green-700 dark:text-green-400 mt-1">
                        External agents can only use local models and cannot access cloud model APIs.
                    </p>
                </div>
            )}

            <div className="space-y-2">
                <h4 className="text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wide">
                    Local Model Providers
                </h4>
                {providers.filter(p => p.type === 'local').map(provider => (
                    <label
                        key={provider.id}
                        className="flex items-center justify-between p-3 border dark:border-gray-700 rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800"
                    >
                        <div className="flex items-center gap-2">
                            <span className="flex h-7 w-7 items-center justify-center rounded bg-gray-100 text-xs font-semibold text-gray-700 dark:bg-gray-700 dark:text-gray-200">
                                {provider.icon}
                            </span>
                            <span className="text-sm text-gray-900 dark:text-gray-100">{provider.name}</span>
                        </div>
                        <input
                            type="checkbox"
                            checked={allowedProviders.includes(provider.id)}
                            onChange={() => toggleProvider(provider.id)}
                            className="rounded border-gray-300 text-accent focus:ring-accent"
                        />
                    </label>
                ))}
            </div>

            <div className="space-y-2">
                <h4 className="text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wide">
                    Cloud Model Providers
                </h4>
                {providers.filter(p => p.type === 'cloud').map(provider => (
                    <label
                        key={provider.id}
                        className="flex items-center justify-between p-3 border dark:border-gray-700 rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800"
                    >
                        <div className="flex items-center gap-2">
                            <span className="flex h-7 w-7 items-center justify-center rounded bg-gray-100 text-xs font-semibold text-gray-700 dark:bg-gray-700 dark:text-gray-200">
                                {provider.icon}
                            </span>
                            <span className="text-sm text-gray-900 dark:text-gray-100">{provider.name}</span>
                            <span className="text-xs px-2 py-0.5 bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300 rounded">
                                Cloud
                            </span>
                        </div>
                        <input
                            type="checkbox"
                            checked={allowedProviders.includes(provider.id)}
                            onChange={() => toggleProvider(provider.id)}
                            className="rounded border-gray-300 text-accent focus:ring-accent"
                        />
                    </label>
                ))}
            </div>

            <div className="pt-4 border-t dark:border-gray-700">
                <button className="px-4 py-2 bg-accent text-white rounded hover:bg-accent-hover transition-colors">
                    Save Settings
                </button>
            </div>
        </div>
    );
}

/**
 * Network Policy Settings
 */
function NetworkPolicySettings() {
    const [allowedHosts, setAllowedHosts] = React.useState<string[]>([
        'pypi.org',
        'registry.npmjs.org',
        'github.com',
        'api.github.com',
    ]);
    const [newHost, setNewHost] = React.useState('');

    const addHost = () => {
        if (newHost && !allowedHosts.includes(newHost)) {
            setAllowedHosts([...allowedHosts, newHost]);
            setNewHost('');
        }
    };

    const removeHost = (host: string) => {
        setAllowedHosts(allowedHosts.filter(h => h !== host));
    };

    return (
        <div className="space-y-6">
            <div>
                <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
                    {t('networkPolicy' as any) || 'Network Policy'}
                </h3>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
                    {t('networkPolicyDescription' as any) || 'Configure the external network endpoints agents are allowed to access.'}
                </p>
            </div>

            <div className="flex gap-2">
                <input
                    type="text"
                    value={newHost}
                    onChange={(e) => setNewHost(e.target.value)}
                    placeholder="Example: api.example.com"
                    className="flex-1 px-3 py-2 text-sm border dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                />
                <button
                    onClick={addHost}
                    className="px-4 py-2 bg-accent text-white rounded-lg hover:bg-accent-hover transition-colors"
                >
                    Add
                </button>
            </div>

            <div className="space-y-2">
                {allowedHosts.map((host) => (
                    <div
                        key={host}
                        className="flex items-center justify-between p-3 border dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800"
                    >
                        <span className="text-sm text-gray-900 dark:text-gray-100">{host}</span>
                        <button
                            onClick={() => removeHost(host)}
                            className="text-sm text-red-600 dark:text-red-400 hover:text-red-800 dark:hover:text-red-300"
                        >
                            Remove
                        </button>
                    </div>
                ))}
            </div>

            <div className="pt-4 border-t dark:border-gray-700">
                <button className="px-4 py-2 bg-accent text-white rounded hover:bg-accent-hover transition-colors">
                    Save Settings
                </button>
            </div>
        </div>
    );
}

/**
 * Secrets Policy Settings
 */
function SecretsPolicySettings() {
    const [allowedApis, setAllowedApis] = React.useState<string[]>([]);
    const apis = [
        { id: 'api.openai.com', name: 'OpenAI API', icon: 'OA' },
        { id: 'api.anthropic.com', name: 'Anthropic API', icon: 'AN' },
        { id: 'generativelanguage.googleapis.com', name: 'Google AI API', icon: 'GA' },
    ];

    const toggleApi = (id: string) => {
        setAllowedApis(prev =>
            prev.includes(id) ? prev.filter(a => a !== id) : [...prev, id]
        );
    };

    return (
        <div className="space-y-6">
            <div>
                <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
                    {t('secretsPolicy' as any) || 'Secrets Policy'}
                </h3>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
                    {t('secretsPolicyDescription' as any) || 'Configure which API endpoints may receive injected credentials.'}
                </p>
            </div>

            <div className="p-3 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg">
                <div className="flex items-center gap-2 text-yellow-800 dark:text-yellow-300">
                    <span className="text-sm font-medium">Security Notice</span>
                </div>
                <p className="text-xs text-yellow-700 dark:text-yellow-400 mt-1">
                    Enabled API endpoints allow external agents to use the corresponding API credentials. Choose carefully.
                </p>
            </div>

            <div className="space-y-2">
                {apis.map(api => (
                    <label
                        key={api.id}
                        className="flex items-center justify-between p-3 border dark:border-gray-700 rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800"
                    >
                        <div className="flex items-center gap-2">
                            <span className="flex h-7 w-7 items-center justify-center rounded bg-gray-100 text-xs font-semibold text-gray-700 dark:bg-gray-700 dark:text-gray-200">
                                {api.icon}
                            </span>
                            <div>
                                <span className="text-sm text-gray-900 dark:text-gray-100">{api.name}</span>
                                <p className="text-xs text-gray-500 dark:text-gray-400">{api.id}</p>
                            </div>
                        </div>
                        <input
                            type="checkbox"
                            checked={allowedApis.includes(api.id)}
                            onChange={() => toggleApi(api.id)}
                            className="rounded border-gray-300 text-accent focus:ring-accent"
                        />
                    </label>
                ))}
            </div>

            {allowedApis.length === 0 && (
                <div className="p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg">
                    <div className="flex items-center gap-2 text-green-800 dark:text-green-300">
                        <span className="text-sm font-medium">Isolated Mode</span>
                    </div>
                    <p className="text-xs text-green-700 dark:text-green-400 mt-1">
                        No API credential injection is currently allowed, so external agents cannot access cloud services.
                    </p>
                </div>
            )}

            <div className="pt-4 border-t dark:border-gray-700">
                <button className="px-4 py-2 bg-accent text-white rounded hover:bg-accent-hover transition-colors">
                    Save Settings
                </button>
            </div>
        </div>
    );
}
