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
    descriptionZh: string;
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
        icon: '🧠',
        description: 'Built-in Mindscape AI execution engine with Playbook support',
        descriptionZh: 'Mindscape 內建執行引擎，支援 Playbook、Tool 調用、多模型切換',
        status: 'built-in',
        riskTags: [
            { label: '系統內建', color: 'green' },
            { label: 'Governance 完整控制', color: 'green' },
            { label: '60+ 內建 Tool', color: 'green' },
        ],
        requirements: ['已內建'],
        features: ['Playbook 執行', 'Tool 調用', '模型切換', '對話記憶', '工作流編排'],
    },
    {
        id: 'moltbot',
        name: 'Moltbot',
        icon: '🔥',
        description: 'Lightweight local CLI Agent for quick tasks',
        descriptionZh: '輕量級本地 CLI Agent，適合快速任務執行',
        status: 'installed',
        riskTags: [
            { label: '沙箱隔離', color: 'green' },
            { label: '僅本地執行', color: 'green' },
        ],
        requirements: ['Python 3.10+', 'pip'],
        features: ['Shell 執行', '文件操作', '程式碼生成'],
    },
    {
        id: 'langgraph',
        name: 'LangGraph',
        icon: '🦜',
        description: 'LangChain Graph Agent for complex workflows',
        descriptionZh: 'LangChain 的 Graph Agent，適合複雜工作流',
        status: 'available',
        riskTags: [
            { label: '需要 API Key', color: 'yellow' },
            { label: '可連網', color: 'yellow' },
            { label: 'Tool 調用', color: 'orange' },
        ],
        requirements: ['Python 3.10+', 'Docker'],
        features: ['多步驟推理', '狀態管理', 'Tool 調用'],
    },
    {
        id: 'crewai',
        name: 'CrewAI',
        icon: '🚢',
        description: 'Multi-agent collaboration framework',
        descriptionZh: '多 Agent 協作框架，適合團隊任務分工',
        status: 'available',
        riskTags: [
            { label: '多 Agent 互動', color: 'yellow' },
            { label: '需要 API Key', color: 'yellow' },
            { label: '任務委派', color: 'orange' },
        ],
        requirements: ['Python 3.10+', 'Docker'],
        features: ['角色分工', '任務委派', '協作執行'],
    },
    {
        id: 'autogpt',
        name: 'AutoGPT',
        icon: '🤖',
        description: 'Autonomous task execution agent',
        descriptionZh: '自主任務執行 Agent，適合長時間自動化',
        status: 'available',
        riskTags: [
            { label: '自主決策', color: 'red' },
            { label: '可長時運行', color: 'orange' },
            { label: '網路搜尋', color: 'yellow' },
            { label: '文件讀寫', color: 'orange' },
        ],
        requirements: ['Python 3.10+', 'Docker', 'Redis'],
        features: ['自主規劃', '記憶管理', '網路搜尋'],
    },
    {
        id: 'open-interpreter',
        name: 'Open Interpreter',
        icon: '🔧',
        description: 'Code execution agent with natural language',
        descriptionZh: '自然語言程式碼執行 Agent',
        status: 'available',
        riskTags: [
            { label: '任意程式碼執行', color: 'red' },
            { label: '系統存取', color: 'red' },
            { label: '無沙箱', color: 'red' },
        ],
        requirements: ['Python 3.10+'],
        features: ['程式碼執行', '多語言支援', 'REPL 模式'],
    },
    {
        id: 'claude-computer-use',
        name: 'Claude Computer Use',
        icon: '🧠',
        description: 'Anthropic computer use capabilities',
        descriptionZh: 'Anthropic 電腦使用能力',
        status: 'coming-soon',
        riskTags: [
            { label: 'GUI 控制', color: 'red' },
            { label: '滑鼠鍵盤操作', color: 'red' },
            { label: '螢幕擷取', color: 'orange' },
            { label: '需要 Anthropic API', color: 'yellow' },
        ],
        requirements: ['Docker', 'Anthropic API'],
        features: ['滑鼠控制', '螢幕識別', 'GUI 操作'],
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
            onSendToAssistant(`幫我安裝 ${agentName}`);
        } else {
            // Fallback: call original onInstall if no assistant available
            onInstall?.(agentId);
        }
    };

    // Chat-First: Trigger assistant chat for configuration
    const handleConfigure = (agentId: string, agentName: string) => {
        if (onSendToAssistant) {
            onSendToAssistant(`幫我配置 ${agentName}`);
        } else {
            onConfigure?.(agentId);
        }
    };

    // Chat-First: View settings via assistant
    const handleViewSettings = (agentName: string) => {
        if (onSendToAssistant) {
            onSendToAssistant(`顯示 ${agentName} 的設定`);
        }
    };

    return (
        <div className="space-y-6">
            <div>
                <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
                    {t('installAgents' as any) || '安裝 AI 代理'}
                </h3>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
                    {t('installAgentsDescription' as any) || '瀏覽並安裝常見的 AI Agent 框架'}
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
                                <span className="text-2xl">{agent.icon}</span>
                                <h4 className="font-medium text-gray-900 dark:text-gray-100">
                                    {agent.name}
                                </h4>
                            </div>
                            {agent.status === 'installed' && (
                                <span className="text-xs px-2 py-1 bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300 rounded">
                                    ✓ 已安裝
                                </span>
                            )}
                            {agent.status === 'built-in' && (
                                <span className="text-xs px-2 py-1 bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300 rounded">
                                    ⚙️ 系統內建
                                </span>
                            )}
                            {agent.status === 'coming-soon' && (
                                <span className="text-xs px-2 py-1 bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400 rounded">
                                    即將推出
                                </span>
                            )}
                        </div>

                        {/* Description */}
                        <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                            {agent.descriptionZh}
                        </p>

                        {/* Risk Tags Block */}
                        <div className="p-2 bg-gray-50 dark:bg-gray-900/50 rounded-lg mb-3">
                            <div className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
                                {agent.status === 'built-in' ? '✅ 安全特性' : '⚠️ 風險標籤'}
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
                            需求: {agent.requirements.join(', ')}
                        </div>

                        {/* Actions */}
                        <div className="flex gap-2">
                            {agent.status === 'built-in' ? (
                                <button
                                    onClick={() => onConfigure?.(agent.id)}
                                    className="flex-1 px-3 py-1.5 text-sm border border-purple-400 text-purple-600 dark:border-purple-500 dark:text-purple-300 rounded hover:bg-purple-50 dark:hover:bg-purple-900/30 transition-colors"
                                >
                                    查看設定
                                </button>
                            ) : agent.status === 'installed' ? (
                                <button
                                    onClick={() => handleConfigure(agent.id, agent.name)}
                                    className="flex-1 px-3 py-1.5 text-sm border border-accent text-accent dark:border-purple-500 dark:text-purple-300 rounded hover:bg-accent-10 dark:hover:bg-purple-900/30 transition-colors"
                                >
                                    配置
                                </button>
                            ) : agent.status === 'available' ? (
                                <button
                                    onClick={() => handleInstall(agent.id, agent.name)}
                                    disabled={installing === agent.id}
                                    className="flex-1 px-3 py-1.5 text-sm bg-accent text-white dark:bg-purple-600 rounded hover:bg-accent-hover dark:hover:bg-purple-700 transition-colors disabled:opacity-50"
                                >
                                    {installing === agent.id ? '安裝中...' : '安裝'}
                                </button>
                            ) : (
                                <button
                                    disabled
                                    className="flex-1 px-3 py-1.5 text-sm bg-gray-200 text-gray-500 dark:bg-gray-700 dark:text-gray-500 rounded cursor-not-allowed"
                                >
                                    即將推出
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
                    {t('installedAgents' as any) || '已安裝代理'}
                </h3>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
                    {t('installedAgentsDescription' as any) || '管理已安裝的 AI 代理和檢視狀態'}
                </p>
            </div>

            {installedAgents.length === 0 ? (
                <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                    <p className="text-sm">尚未安裝任何 AI 代理</p>
                    <p className="text-xs mt-1">前往「安裝 AI 代理」開始安裝</p>
                </div>
            ) : (
                <div className="space-y-3">
                    {installedAgents.map((agent) => (
                        <div
                            key={agent.id}
                            className="flex items-center justify-between p-4 border dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800"
                        >
                            <div className="flex items-center gap-3">
                                <span className="text-2xl">{agent.icon}</span>
                                <div>
                                    <h4 className="font-medium text-gray-900 dark:text-gray-100">
                                        {agent.name}
                                    </h4>
                                    <p className="text-xs text-gray-500 dark:text-gray-400">
                                        {agent.descriptionZh}
                                    </p>
                                </div>
                            </div>
                            <div className="flex items-center gap-2">
                                <span className="text-xs px-2 py-1 bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300 rounded">
                                    運行中
                                </span>
                                <button className="px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
                                    配置
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
        { id: 'ollama', name: 'Ollama', type: 'local', icon: '🦙' },
        { id: 'llama-cpp', name: 'llama.cpp', type: 'local', icon: '🔧' },
        { id: 'openai', name: 'OpenAI', type: 'cloud', icon: '🤖' },
        { id: 'anthropic', name: 'Anthropic', type: 'cloud', icon: '🧠' },
        { id: 'vertex-ai', name: 'Vertex AI', type: 'cloud', icon: '☁️' },
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
                    {t('modelPolicy' as any) || '模型政策'}
                </h3>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
                    {t('modelPolicyDescription' as any) || '設定允許使用的模型提供者（白名單），限制本地或雲端模型'}
                </p>
            </div>

            {isLocalOnly && (
                <div className="p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg">
                    <div className="flex items-center gap-2 text-green-800 dark:text-green-300">
                        <span>🔒</span>
                        <span className="text-sm font-medium">本地模式已啟用</span>
                    </div>
                    <p className="text-xs text-green-700 dark:text-green-400 mt-1">
                        外部 Agent 只能使用本地模型，無法存取雲端 API
                    </p>
                </div>
            )}

            <div className="space-y-2">
                <h4 className="text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wide">
                    本地模型提供者
                </h4>
                {providers.filter(p => p.type === 'local').map(provider => (
                    <label
                        key={provider.id}
                        className="flex items-center justify-between p-3 border dark:border-gray-700 rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800"
                    >
                        <div className="flex items-center gap-2">
                            <span className="text-lg">{provider.icon}</span>
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
                    雲端模型提供者
                </h4>
                {providers.filter(p => p.type === 'cloud').map(provider => (
                    <label
                        key={provider.id}
                        className="flex items-center justify-between p-3 border dark:border-gray-700 rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800"
                    >
                        <div className="flex items-center gap-2">
                            <span className="text-lg">{provider.icon}</span>
                            <span className="text-sm text-gray-900 dark:text-gray-100">{provider.name}</span>
                            <span className="text-xs px-2 py-0.5 bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300 rounded">
                                雲端
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
                    儲存設定
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
                    {t('networkPolicy' as any) || '網路政策'}
                </h3>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
                    {t('networkPolicyDescription' as any) || '設定 Agent 可存取的外部網路端點（白名單）'}
                </p>
            </div>

            <div className="flex gap-2">
                <input
                    type="text"
                    value={newHost}
                    onChange={(e) => setNewHost(e.target.value)}
                    placeholder="例如: api.example.com"
                    className="flex-1 px-3 py-2 text-sm border dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                />
                <button
                    onClick={addHost}
                    className="px-4 py-2 bg-accent text-white rounded-lg hover:bg-accent-hover transition-colors"
                >
                    新增
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
                            移除
                        </button>
                    </div>
                ))}
            </div>

            <div className="pt-4 border-t dark:border-gray-700">
                <button className="px-4 py-2 bg-accent text-white rounded hover:bg-accent-hover transition-colors">
                    儲存設定
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
        { id: 'api.openai.com', name: 'OpenAI API', icon: '🤖' },
        { id: 'api.anthropic.com', name: 'Anthropic API', icon: '🧠' },
        { id: 'generativelanguage.googleapis.com', name: 'Google AI API', icon: '☁️' },
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
                    {t('secretsPolicy' as any) || '憑證政策'}
                </h3>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
                    {t('secretsPolicyDescription' as any) || '設定可注入憑證的 API 端點，控制外部服務存取'}
                </p>
            </div>

            <div className="p-3 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg">
                <div className="flex items-center gap-2 text-yellow-800 dark:text-yellow-300">
                    <span>⚠️</span>
                    <span className="text-sm font-medium">安全提示</span>
                </div>
                <p className="text-xs text-yellow-700 dark:text-yellow-400 mt-1">
                    啟用的 API 端點將允許外部 Agent 使用對應的 API 憑證。請謹慎選擇。
                </p>
            </div>

            <div className="space-y-2">
                {apis.map(api => (
                    <label
                        key={api.id}
                        className="flex items-center justify-between p-3 border dark:border-gray-700 rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800"
                    >
                        <div className="flex items-center gap-2">
                            <span className="text-lg">{api.icon}</span>
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
                        <span>🔒</span>
                        <span className="text-sm font-medium">隔離模式</span>
                    </div>
                    <p className="text-xs text-green-700 dark:text-green-400 mt-1">
                        目前未允許任何 API 憑證注入，外部 Agent 無法存取任何雲端服務
                    </p>
                </div>
            )}

            <div className="pt-4 border-t dark:border-gray-700">
                <button className="px-4 py-2 bg-accent text-white rounded hover:bg-accent-hover transition-colors">
                    儲存設定
                </button>
            </div>
        </div>
    );
}
