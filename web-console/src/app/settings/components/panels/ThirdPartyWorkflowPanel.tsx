'use client';

import React, { useState, useEffect } from 'react';
import { t } from '../../../../lib/i18n';
import { Section } from '../Section';
import { InlineAlert } from '../InlineAlert';
import { WorkflowWizard } from '../wizards/WorkflowWizard';

interface WorkflowConnection {
  id: string;
  platform: 'zapier' | 'n8n' | 'make' | 'custom';
  name: string;
  status: 'connected' | 'disconnected' | 'error';
  webhook_url?: string;
  last_connected?: string;
  error?: string;
}

interface ThirdPartyWorkflowPanelProps {
  activeProvider?: string;
}

const WORKFLOW_PLATFORMS: Array<{
  id: string;
  name: string;
  description: string;
  icon: string;
}> = [
  {
    id: 'zapier',
    name: 'Zapier',
    description: 'Automate workflows between apps and services',
    icon: '⚡',
  },
  {
    id: 'n8n',
    name: 'n8n',
    description: 'Open-source workflow automation tool',
    icon: '🔄',
  },
  {
    id: 'make',
    name: 'Make',
    description: 'Visual automation platform (formerly Integromat)',
    icon: '🎨',
  },
  {
    id: 'custom',
    name: 'Custom Workflow',
    description: 'Configure a custom workflow integration',
    icon: '🔧',
  },
];

export function ThirdPartyWorkflowPanel({ activeProvider }: ThirdPartyWorkflowPanelProps) {
  const [connections, setConnections] = useState<WorkflowConnection[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showWizard, setShowWizard] = useState(false);
  const [selectedPlatform, setSelectedPlatform] = useState<string | undefined>(activeProvider);

  useEffect(() => {
    if (activeProvider && activeProvider !== selectedPlatform) {
      setSelectedPlatform(activeProvider);
      setShowWizard(true);
    }
  }, [activeProvider]);

  const handleAddWorkflow = (platform?: string) => {
    setSelectedPlatform(platform);
    setShowWizard(true);
  };

  const handleWizardSuccess = () => {
    setShowWizard(false);
    setSelectedPlatform(undefined);
  };

  const handleWizardClose = () => {
    setShowWizard(false);
    setSelectedPlatform(undefined);
  };

  if (showWizard) {
    return (
      <WorkflowWizard
        platform={selectedPlatform as 'zapier' | 'n8n' | 'make' | 'custom'}
        onClose={handleWizardClose}
        onSuccess={handleWizardSuccess}
      />
    );
  }

  return (
    <Section
      title={t('thirdPartyWorkflow')}
      description={t('thirdPartyWorkflowDescription') || 'Connect to workflow automation platforms to extend AI capabilities'}
    >
      {error && (
        <InlineAlert
          type="error"
          message={error}
          onDismiss={() => setError(null)}
          className="mb-4"
        />
      )}

      <div className="mb-4">
        <button
          onClick={() => handleAddWorkflow()}
          className="px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700"
        >
          {t('addWorkflow') || 'Add Workflow'}
        </button>
      </div>

      {loading ? (
        <div className="text-center py-12 text-gray-500">
          <p>{t('loading') || 'Loading...'}</p>
        </div>
      ) : connections.length === 0 ? (
        <div className="text-center py-12 text-gray-500">
          <p>{t('noWorkflows') || 'No workflow connections configured'}</p>
          <p className="text-sm mt-2">{t('addWorkflowToStart') || 'Click "Add Workflow" to get started'}</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {WORKFLOW_PLATFORMS.map((platform) => {
            const connection = connections.find(c => c.platform === platform.id);
            return (
              <div
                key={platform.id}
                className="p-4 border border-gray-300 rounded-lg hover:border-gray-500 cursor-pointer"
                onClick={() => handleAddWorkflow(platform.id)}
              >
                <div className="flex items-start space-x-3">
                  <span className="text-2xl">{platform.icon}</span>
                  <div className="flex-1">
                    <h3 className="font-semibold text-gray-900 mb-1">{platform.name}</h3>
                    <p className="text-sm text-gray-500">{platform.description}</p>
                    {connection && (
                      <p className="text-xs text-gray-400 mt-2">
                        {connection.status === 'connected'
                          ? `✅ ${t('connected') || 'Connected'}`
                          : `⚪ ${t('notConnected') || 'Not connected'}`}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Section>
  );
}

