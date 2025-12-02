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
import { VectorDBConnectionWizard } from './wizards/VectorDBConnectionWizard';
import { LocalFilesystemManager } from './wizards/LocalFilesystemManager';
import { ObsidianConfigWizard } from './wizards/ObsidianConfigWizard';
import { useTools } from '../hooks/useTools';
import { dispatchToolConfigUpdated } from '../../../lib/tool-status-events';

const TOOLS: Array<{
  toolType: string;
  name: string;
  description: string;
  icon: string;
}> = [
  {
    toolType: 'wordpress',
    name: 'WordPress',
    description: 'Connect to local or remote WordPress sites for content, SEO, and order management',
    icon: '🌐',
  },
  {
    toolType: 'notion',
    name: 'Notion',
    description: 'Connect to Notion for page search, content reading, and database queries (read-only mode)',
    icon: '📝',
  },
  {
    toolType: 'google_drive',
    name: 'Google Drive',
    description: 'Connect to Google Drive for file listing and content reading (read-only mode)',
    icon: '📁',
  },
  {
    toolType: 'local_files',
    name: 'Local File System',
    description: 'Access local folders for document collection and RAG',
    icon: '💾',
  },
  {
    toolType: 'vector_db',
    name: 'Vector Database (PostgreSQL / pgvector)',
    description: 'Store semantic vectors for mindscape and documents, used for search and RAG',
    icon: '🗄️',
  },
  {
    toolType: 'obsidian',
    name: 'Obsidian',
    description: 'Connect to local Obsidian vaults for research workflows and knowledge management',
    icon: '📚',
  },
  {
    toolType: 'canva',
    name: 'Canva',
    description: 'Design platform for creating visual content, templates, and graphics',
    icon: '🎨',
  },
];

export function ToolsPanel() {
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

      <Section
        title={t('toolsAndIntegrations')}
        description={t('toolsAndIntegrationsDescription')}
      >
        <ToolGrid>
          {TOOLS.map((tool) => {
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
