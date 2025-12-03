'use client';

import React, { useState, useEffect } from 'react';
import { t } from '../../../lib/i18n';
import { Section } from './Section';
import { ToolGrid } from './ToolGrid';
import { ToolCard } from './ToolCard';
import { RegisteredToolList } from './RegisteredToolList';
import { InlineAlert } from './InlineAlert';
import { WordPressConnectionWizard } from './wizards/WordPressConnectionWizard';
import { NotionConnectionWizard } from './wizards/NotionConnectionWizard';
import { GoogleDriveConnectionWizard } from './wizards/GoogleDriveConnectionWizard';
import { SlackConnectionWizard } from './wizards/SlackConnectionWizard';
import { AirtableConnectionWizard } from './wizards/AirtableConnectionWizard';
import { GoogleSheetsConnectionWizard } from './wizards/GoogleSheetsConnectionWizard';
import { GitHubConnectionWizard } from './wizards/GitHubConnectionWizard';
import { VectorDBConnectionWizard } from './wizards/VectorDBConnectionWizard';
import { LocalFilesystemManager } from './wizards/LocalFilesystemManager';
import { ObsidianConfigWizard } from './wizards/ObsidianConfigWizard';
import { MCPServerPanel } from './panels/MCPServerPanel';
import { ThirdPartyWorkflowPanel } from './panels/ThirdPartyWorkflowPanel';
import { useTools } from '../hooks/useTools';
import { dispatchToolConfigUpdated } from '../../../lib/tool-status-events';

interface ToolsPanelProps {
  activeSection?: string;
  activeProvider?: string;
}

// System tools - local/system-level tools
const getSystemTools = (t: (key: string) => string): Array<{
  toolType: string;
  name: string;
  description: string;
  icon: string;
}> => [
  {
    toolType: 'local_files',
    name: 'Local File System',
    description: t('toolLocalFilesDescription'),
    icon: '💾',
  },
  {
    toolType: 'vector_db',
    name: 'Vector Database (PostgreSQL / pgvector)',
    description: t('toolVectorDBDescription'),
    icon: '🗄️',
  },
  {
    toolType: 'obsidian',
    name: 'Obsidian',
    description: t('toolObsidianDescription'),
    icon: '📚',
  },
];

// External SaaS tools - third-party cloud services
// Tool names are brand names and don't need i18n, only descriptions do
const getExternalSaaSTools = (t: (key: string) => string): Array<{
  toolType: string;
  name: string;
  description: string;
  icon: string;
}> => [
  {
    toolType: 'wordpress',
    name: 'WordPress',
    description: t('toolWordPressDescription'),
    icon: '🌐',
  },
  {
    toolType: 'notion',
    name: 'Notion',
    description: t('toolNotionDescription'),
    icon: '📝',
  },
  {
    toolType: 'google_drive',
    name: 'Google Drive',
    description: t('toolGoogleDriveDescription'),
    icon: '📁',
  },
  {
    toolType: 'canva',
    name: 'Canva',
    description: t('toolCanvaDescription'),
    icon: '🎨',
  },
  {
    toolType: 'slack',
    name: 'Slack',
    description: t('toolSlackDescription'),
    icon: '💬',
  },
  {
    toolType: 'airtable',
    name: 'Airtable',
    description: t('toolAirtableDescription'),
    icon: '📊',
  },
  {
    toolType: 'google_sheets',
    name: 'Google Sheets',
    description: t('toolGoogleSheetsDescription'),
    icon: '📈',
  },
  {
    toolType: 'github',
    name: 'GitHub',
    description: t('toolGitHubDescription'),
    icon: '💻',
  },
];

interface ToolsPanelProps {
  activeSection?: string;
  activeProvider?: string;
}

export function ToolsPanel({ activeSection, activeProvider }: ToolsPanelProps = {}) {
  const {
    loading,
    connections,
    tools,
    vectorDBConfig,
    testingConnection,
    loadTools,
    loadVectorDBConfig,
    loadToolsStatus,
    testConnection,
    testVectorDB,
    getToolStatus,
  } = useTools();

  const [selectedTool, setSelectedTool] = useState<string | null>(null);
  const [testSuccess, setTestSuccess] = useState<string | null>(null);
  const [testError, setTestError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<string | null>(null);

  useEffect(() => {
    loadTools();
    loadVectorDBConfig();
    loadToolsStatus();
    // loadVectorDBHealthStatus is called in useTools hook's useEffect
    // But we also call it here to ensure it's loaded when component mounts
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    fetch(`${apiUrl}/health`)
      .then(res => res.ok ? res.json() : null)
      .then(health => {
        if (health) {
          const connected = health.vector_db_connected ?? health.components?.vector_db_connected ?? false;
          // Force update by calling loadVectorDBHealthStatus through the hook
          // This is a workaround to ensure state is updated
        }
      })
      .catch(err => console.debug('Failed to load health status in ToolsPanel:', err));
  }, [loadTools, loadVectorDBConfig, loadToolsStatus]);

  const handleTestConnection = async (connectionId: string) => {
    setTestError(null);
    setTestSuccess(null);
    try {
      await testConnection(connectionId);
      setTestSuccess(t('connectionTestSuccessful'));
      // Refresh tool status after successful test
      loadToolsStatus();
      dispatchToolConfigUpdated();
    } catch (err) {
      setTestError(
        `${t('testFailed')}: ${err instanceof Error ? err.message : 'Unknown error'}`
      );
    }
  };

  const handleTestVectorDB = async () => {
    setTestError(null);
    setTestResult(null);
    try {
      const details = await testVectorDB();
      setTestResult(`${t('testResults')}:\n\n${details}`);
      // Refresh tool status after successful test
      loadToolsStatus();
      dispatchToolConfigUpdated('vector_db');
    } catch (err) {
      setTestError(
        `${t('testFailed')}: ${err instanceof Error ? err.message : 'Unknown error'}`
      );
    }
  };

  const handleWizardSuccess = (toolType?: string) => {
    setSelectedTool(null);
    loadTools();
    loadVectorDBConfig();
    loadToolsStatus();
    // Dispatch event to notify other components
    dispatchToolConfigUpdated(toolType);
  };

  return (
    <div className="space-y-6">
      {testSuccess && (
        <InlineAlert
          type="success"
          message={testSuccess}
          onDismiss={() => setTestSuccess(null)}
        />
      )}

      {testError && (
        <InlineAlert
          type="error"
          message={testError}
          onDismiss={() => setTestError(null)}
        />
      )}

      {testResult && (
        <InlineAlert
          type="info"
          message={testResult}
          onDismiss={() => setTestResult(null)}
          className="whitespace-pre-line"
        />
      )}

      {!activeSection && (
        <div className="text-center py-12 text-gray-500 dark:text-gray-400">
          <p>{t('toolsAndIntegrations')}</p>
          <p className="text-sm mt-2">{t('selectToolsSection')}</p>
        </div>
      )}

      {activeSection === 'system-tools' && (
      <Section
          title={t('systemTools')}
          description={t('systemToolsDescription')}
      >
        <ToolGrid>
            {getSystemTools(t).map((tool) => {
            const status = getToolStatus(tool.toolType);
            const isLocal = tool.toolType === 'local_files';
            const localStatus = isLocal
              ? { status: 'local' as const, label: 'Local mode', icon: '🔌' }
              : status;

            return (
              <ToolCard
                key={tool.toolType}
                toolType={tool.toolType}
                name={tool.name}
                description={tool.description}
                icon={tool.icon}
                status={localStatus}
                onConfigure={() => setSelectedTool(tool.toolType)}
                onTest={
                  tool.toolType === 'vector_db'
                    ? handleTestVectorDB
                    : tool.toolType === 'obsidian'
                      ? undefined
                      : tool.toolType !== 'local_files' && status.status === 'connected'
                        ? () => {
                            const conn = connections.find((c) => c.tool_type === tool.toolType);
                            if (conn) handleTestConnection(conn.id);
                          }
                        : undefined
                }
                testing={testingConnection === tool.toolType || testingConnection !== null}
              />
            );
          })}
        </ToolGrid>
      </Section>
      )}

      {activeSection === 'external-saas-tools' && (
        <Section
          title={t('externalSAASTools')}
          description={t('externalSAASToolsDescription')}
        >
          <ToolGrid>
            {getExternalSaaSTools(t).map((tool) => {
              const status = getToolStatus(tool.toolType);
              return (
                <ToolCard
                  key={tool.toolType}
                  toolType={tool.toolType}
                  name={tool.name}
                  description={tool.description}
                  icon={tool.icon}
                  status={status}
                  onConfigure={() => setSelectedTool(tool.toolType)}
                  onTest={
                    status.status === 'connected'
                      ? () => {
                          const conn = connections.find((c) => c.tool_type === tool.toolType);
                          if (conn) handleTestConnection(conn.id);
                        }
                      : undefined
                  }
                  testing={testingConnection === tool.toolType || testingConnection !== null}
                />
              );
            })}
          </ToolGrid>
        </Section>
      )}

      {activeSection === 'mcp-server' && (
        <MCPServerPanel activeProvider={activeProvider} />
      )}

      {activeSection === 'third-party-workflow' && (
        <ThirdPartyWorkflowPanel activeProvider={activeProvider} />
      )}

      {selectedTool === 'wordpress' && (
        <WordPressConnectionWizard onClose={() => setSelectedTool(null)} onSuccess={() => handleWizardSuccess('wordpress')} />
      )}

      {selectedTool === 'notion' && (
        <NotionConnectionWizard onClose={() => setSelectedTool(null)} onSuccess={() => handleWizardSuccess('notion')} />
      )}

      {selectedTool === 'google_drive' && (
        <GoogleDriveConnectionWizard
          onClose={() => setSelectedTool(null)}
          onSuccess={() => handleWizardSuccess('google_drive')}
        />
      )}

      {selectedTool === 'slack' && (
        <SlackConnectionWizard
          onClose={() => setSelectedTool(null)}
          onSuccess={() => handleWizardSuccess('slack')}
        />
      )}

      {selectedTool === 'airtable' && (
        <AirtableConnectionWizard
          onClose={() => setSelectedTool(null)}
          onSuccess={() => handleWizardSuccess('airtable')}
        />
      )}

      {selectedTool === 'google_sheets' && (
        <GoogleSheetsConnectionWizard
          onClose={() => setSelectedTool(null)}
          onSuccess={() => handleWizardSuccess('google_sheets')}
        />
      )}

      {selectedTool === 'github' && (
        <GitHubConnectionWizard
          onClose={() => setSelectedTool(null)}
          onSuccess={() => handleWizardSuccess('github')}
        />
      )}

      {selectedTool === 'vector_db' && (
        <VectorDBConnectionWizard
          config={vectorDBConfig}
          onClose={() => setSelectedTool(null)}
          onSuccess={() => handleWizardSuccess('vector_db')}
        />
      )}

      {selectedTool === 'local_files' && (
        <LocalFilesystemManager
          onClose={() => setSelectedTool(null)}
          onSuccess={() => handleWizardSuccess('local_files')}
        />
      )}

      {selectedTool === 'obsidian' && (
        <ObsidianConfigWizard
          config={null}
          onClose={() => setSelectedTool(null)}
          onSuccess={() => handleWizardSuccess('obsidian')}
        />
      )}

      <RegisteredToolList tools={tools} />
    </div>
  );
}
