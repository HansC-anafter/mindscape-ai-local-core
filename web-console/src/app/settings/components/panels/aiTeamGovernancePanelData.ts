import type {
    AgentDefinition,
    ModelProviderOption,
    SecretsApiOption,
} from './aiTeamGovernancePanelTypes';

export const AVAILABLE_AGENTS: AgentDefinition[] = [
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

export const MODEL_PROVIDER_OPTIONS: ModelProviderOption[] = [
    { id: 'ollama', name: 'Ollama', type: 'local', icon: 'OL' },
    { id: 'llama-cpp', name: 'llama.cpp', type: 'local', icon: 'LC' },
    { id: 'openai', name: 'OpenAI', type: 'cloud', icon: 'OA' },
    { id: 'anthropic', name: 'Anthropic', type: 'cloud', icon: 'AN' },
    { id: 'vertex-ai', name: 'Vertex AI', type: 'cloud', icon: 'VX' },
];

export const DEFAULT_ALLOWED_PROVIDERS = ['ollama', 'llama-cpp'];

export const DEFAULT_ALLOWED_HOSTS = [
    'pypi.org',
    'registry.npmjs.org',
    'github.com',
    'api.github.com',
];

export const SECRETS_API_OPTIONS: SecretsApiOption[] = [
    { id: 'api.openai.com', name: 'OpenAI API', icon: 'OA' },
    { id: 'api.anthropic.com', name: 'Anthropic API', icon: 'AN' },
    { id: 'generativelanguage.googleapis.com', name: 'Google AI API', icon: 'GA' },
];
