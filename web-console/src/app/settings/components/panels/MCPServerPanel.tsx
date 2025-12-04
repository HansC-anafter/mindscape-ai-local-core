'use client';

import React, { useState, useEffect } from 'react';
import { t } from '../../../../lib/i18n';
import { settingsApi } from '../../utils/settingsApi';
import { Section } from '../Section';
import { InlineAlert } from '../InlineAlert';
import { MCPServerWizard } from '../wizards/MCPServerWizard';
import { MCPServerCard } from '../MCPServerCard';

interface MCPServer {
  id: string;
  name: string;
  transport: 'stdio' | 'http';
  status: 'connected' | 'disconnected' | 'error';
  tools_count?: number;
  last_connected?: string;
  error?: string;
}

interface MCPServerPanelProps {
  activeProvider?: string;
}

export function MCPServerPanel({ activeProvider }: MCPServerPanelProps) {
  const [servers, setServers] = useState<MCPServer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showWizard, setShowWizard] = useState(false);
  const [selectedProvider, setSelectedProvider] = useState<string | undefined>(activeProvider);
  const [editingServer, setEditingServer] = useState<MCPServer | null>(null);

  useEffect(() => {
    loadServers();
  }, []);

  useEffect(() => {
    if (activeProvider && activeProvider !== selectedProvider) {
      setSelectedProvider(activeProvider);
      setShowWizard(true);
    }
  }, [activeProvider]);

  const loadServers = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await settingsApi.get<{
        success: boolean;
        servers: MCPServer[];
        count: number;
      }>('/api/v1/tools/mcp/servers');
      setServers(response.servers || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load MCP servers');
    } finally {
      setLoading(false);
    }
  };

  const handleAddServer = () => {
    setSelectedProvider(undefined);
    setShowWizard(true);
  };

  const handleImportClaude = async () => {
    try {
      const response = await settingsApi.post<{
        success: boolean;
        imported_count: number;
        servers: MCPServer[];
      }>('/api/v1/tools/mcp/import-claude-config');
      await loadServers();
      if (response.imported_count > 0) {
        // Show success message
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to import Claude config');
    }
  };

  const handleWizardSuccess = () => {
    setShowWizard(false);
    setSelectedProvider(undefined);
    loadServers();
  };

  const handleWizardClose = () => {
    setShowWizard(false);
    setSelectedProvider(undefined);
    setEditingServer(null);
  };

  const handleEdit = (server: MCPServer) => {
    setEditingServer(server);
    setShowWizard(true);
  };

  const handleDelete = async (serverId: string) => {
    try {
      await settingsApi.delete(`/api/v1/tools/mcp/servers/${serverId}`);
      await loadServers();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete MCP server');
      throw err;
    }
  };

  if (showWizard) {
    return (
      <MCPServerWizard
        provider={selectedProvider}
        editingServer={editingServer}
        onClose={handleWizardClose}
        onSuccess={handleWizardSuccess}
      />
    );
  }

  return (
    <Section
      title={t('mcpServer')}
      description={t('mcpServerDescription') || 'Configure Model Context Protocol servers to extend AI capabilities'}
    >
      {error && (
        <InlineAlert
          type="error"
          message={error}
          onDismiss={() => setError(null)}
          className="mb-4"
        />
      )}

      <div className="mb-4 flex space-x-3">
        <button
          onClick={handleAddServer}
          className="px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700"
        >
          {t('addMCPServer') || 'Add MCP Server'}
        </button>
        <button
          onClick={handleImportClaude}
          className="px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700"
        >
          {t('importClaudeConfig') || 'Import from Claude Desktop'}
        </button>
      </div>

      {loading ? (
        <div className="text-center py-12 text-gray-500">
          <p>{t('loading') || 'Loading...'}</p>
        </div>
      ) : servers.length === 0 ? (
        <div className="text-center py-12 text-gray-500">
          <p>{t('noMCPServers') || 'No MCP servers configured'}</p>
          <p className="text-sm mt-2">{t('addMCPServerToStart') || 'Click "Add MCP Server" to get started'}</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {servers.map((server) => (
            <MCPServerCard
              key={server.id}
              server={server}
              onRefresh={loadServers}
              onEdit={handleEdit}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}
    </Section>
  );
}

