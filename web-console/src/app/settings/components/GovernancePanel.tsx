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
            <Section title={t('nodeGovernance' as any)}>
              <NodeGovernanceSettings />
            </Section>
            <Section title={t('preflight' as any)}>
              <PreflightSettings />
            </Section>
            <Section title={t('governanceMode' as any)}>
              <GovernanceModeSettings />
            </Section>
            <Section title={t('costGovernance' as any)}>
              <CostGovernanceSettings />
            </Section>
            <Section title={t('policyService' as any)}>
              <PolicyServiceSettings />
            </Section>
          </div>
        );
    }
  };

  return (
    <Card>
      <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-4">
        {t('governance' as any)}
      </h2>
      <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">
        {t('governanceDescription' as any)}
      </p>
      {renderContent()}
    </Card>
  );
}
