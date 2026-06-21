'use client';

import React from 'react';
import { AgentMarketplace, InstalledAgentsList } from './aiTeamGovernanceAgentSections';
import {
    ModelPolicySettings,
    NetworkPolicySettings,
    SecretsPolicySettings,
} from './aiTeamGovernancePolicySections';
import type { AITeamGovernancePanelProps } from './aiTeamGovernancePanelTypes';

export { AgentMarketplace, InstalledAgentsList };

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
