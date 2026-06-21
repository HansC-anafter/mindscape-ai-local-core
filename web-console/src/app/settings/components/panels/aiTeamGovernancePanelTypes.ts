export interface RiskTag {
    label: string;
    color: 'green' | 'yellow' | 'orange' | 'red';
    icon?: string;
}

export interface AgentDefinition {
    id: string;
    name: string;
    icon: string;
    description: string;
    status: 'available' | 'installed' | 'coming-soon' | 'built-in';
    riskTags: RiskTag[];
    requirements: string[];
    features: string[];
}

export interface AgentMarketplaceProps {
    onInstall?: (agentId: string) => void;
    onConfigure?: (agentId: string) => void;
    onSendToAssistant?: (message: string) => void;
}

export interface AITeamGovernancePanelProps {
    activeSection?: string;
    onSendToAssistant?: (message: string) => void;
}

export interface ModelProviderOption {
    id: string;
    name: string;
    type: 'local' | 'cloud';
    icon: string;
}

export interface SecretsApiOption {
    id: string;
    name: string;
    icon: string;
}
