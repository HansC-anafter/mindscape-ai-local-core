'use client';

import React from 'react';
import { t } from '../../../lib/i18n';
import { Card } from './Card';
import { Section } from './Section';
import { NodeGovernanceSettings } from './panels/NodeGovernanceSettings';
import { PreflightSettings } from './panels/PreflightSettings';
import { GovernanceModeSettings } from './panels/GovernanceModeSettings';
import { CostGovernanceSettings } from './panels/CostGovernanceSettings';
import { PolicyServiceSettings } from './panels/PolicyServiceSettings';

interface GovernancePanelProps {
  activeSection?: string;
}

export function GovernancePanel({ activeSection }: GovernancePanelProps) {
  const renderContent = () => {
    switch (activeSection) {
      case 'node':
        return <NodeGovernanceSettings />;
      case 'preflight':
        return <PreflightSettings />;
      case 'mode':
        return <GovernanceModeSettings />;
      case 'cost':
        return <CostGovernanceSettings />;
      case 'policy':
        return <PolicyServiceSettings />;
      default:
        return (
          <div className="space-y-6">
            <Section title={t('nodeGovernance')} id="node">
              <NodeGovernanceSettings />
            </Section>
            <Section title={t('preflight')} id="preflight">
              <PreflightSettings />
            </Section>
            <Section title={t('governanceMode')} id="mode">
              <GovernanceModeSettings />
            </Section>
            <Section title={t('costGovernance')} id="cost">
              <CostGovernanceSettings />
            </Section>
            <Section title={t('policyService')} id="policy">
              <PolicyServiceSettings />
            </Section>
          </div>
        );
    }
  };

  return (
    <Card>
      <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-4">
        {t('governance')}
      </h2>
      <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">
        {t('governanceDescription')}
      </p>
      {renderContent()}
    </Card>
  );
}

