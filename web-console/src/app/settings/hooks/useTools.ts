'use client';

import { useState, useEffect, useCallback } from 'react';
import { settingsApi } from '../utils/settingsApi';
import type { ToolConnection, RegisteredTool, VectorDBConfig, ToolStatus, ToolStatusInfo } from '../types';
import {
  listenToToolStatusChanged,
  listenToToolConfigUpdated,
} from '../../../lib/tool-status-events';

interface UseToolsReturn {
  loading: boolean;
  connections: ToolConnection[];
  tools: RegisteredTool[];
  vectorDBConfig: VectorDBConfig | null;
  testingConnection: string | null;
  toolsStatus: Record<string, ToolStatusInfo>;
  loadTools: () => Promise<void>;
  loadVectorDBConfig: () => Promise<void>;
  loadToolsStatus: () => Promise<void>;
  testConnection: (connectionId: string) => Promise<void>;
  testVectorDB: () => Promise<string>;
  getToolStatus: (toolType: string) => ToolStatus;
  getToolStatusForPack: (toolType: string) => ToolStatus;
}

const getDefaultToolStatus = (): ToolStatus => ({
  status: 'not_configured',
  label: 'Not configured',
  icon: '⚠️',
});

export function useTools(): UseToolsReturn {
  const [loading, setLoading] = useState(false);
  const [connections, setConnections] = useState<ToolConnection[]>([]);
  const [tools, setTools] = useState<RegisteredTool[]>([]);
  const [vectorDBConfig, setVectorDBConfig] = useState<VectorDBConfig | null>(null);
  const [testingConnection, setTestingConnection] = useState<string | null>(null);
  const [toolsStatus, setToolsStatus] = useState<Record<string, ToolStatusInfo>>({});

  const loadTools = useCallback(async () => {
    setLoading(true);
    try {
      const [connData, toolsData] = await Promise.all([
        settingsApi.get<ToolConnection[]>('/api/v1/tools/connections').catch(() => []),
        settingsApi.get<RegisteredTool[]>('/api/v1/tools?enabled_only=false').catch(() => []),
      ]);
      setConnections(connData);
      setTools(toolsData);
    } catch (err) {
      console.error('Failed to load tools:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadVectorDBConfig = useCallback(async () => {
    try {
      const data = await settingsApi.get<VectorDBConfig>('/api/v1/vector-db/config');
      setVectorDBConfig({
        ...data,
        enabled: data.enabled !== undefined ? data.enabled : true,
      });
    } catch (err) {
      console.error('Failed to load vector DB config:', err);
      setVectorDBConfig({ mode: 'local', enabled: true });
    }
  }, []);

  const loadToolsStatus = useCallback(async () => {
    try {
      const response = await settingsApi.get<{ tools: Record<string, ToolStatusInfo> }>('/api/v1/tools/status');
      setToolsStatus(response.tools || {});
    } catch (err) {
      console.error('Failed to load tools status:', err);
      setToolsStatus({});
    }
  }, []);

  // Listen to tool status change events for real-time updates
  useEffect(() => {
    const cleanupStatus = listenToToolStatusChanged(() => {
      // Refresh tool status when any tool status changes
      loadToolsStatus();
    });

    const cleanupConfig = listenToToolConfigUpdated(() => {
      // Refresh all tool data when config is updated
      loadTools();
      loadVectorDBConfig();
      loadToolsStatus();
    });

    return () => {
      cleanupStatus();
      cleanupConfig();
    };
  }, [loadTools, loadVectorDBConfig, loadToolsStatus]);

  const testConnection = useCallback(
    async (connectionId: string) => {
      setTestingConnection(connectionId);
      try {
        const conn = connections.find((c) => c.id === connectionId);
        if (!conn) return;

        if (conn.tool_type === 'wordpress' && conn.wp_url) {
          await settingsApi.post('/api/v1/tools/wordpress/discover', {
            connection_id: connectionId,
            name: conn.name,
            wp_url: conn.wp_url,
            wp_username: conn.wp_username || 'admin',
            wp_application_password: '',
          });
        }
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : 'Connection test failed';
        throw new Error(errorMessage);
      } finally {
        setTestingConnection(null);
      }
    },
    [connections]
  );

  const testVectorDB = useCallback(async (): Promise<string> => {
    setTestingConnection('vector_db');
    try {
      const result = await settingsApi.post<{
        database?: string;
        pgvector_installed?: boolean;
        pgvector_version?: string;
        dimension_check?: boolean;
        dimension?: number;
        dimension_error?: string;
      }>('/api/v1/vector-db/test');

      const details = [
        `✅ Successfully connected to ${result.database || 'PostgreSQL'}`,
        result.pgvector_installed
          ? `✅ pgvector installed (version ${result.pgvector_version || 'unknown'})`
          : '❌ pgvector extension not found',
        result.dimension_check
          ? `✅ Main collections dimension = ${result.dimension} (compatible with current embedding model)`
          : result.dimension_error || '⚠️ Dimension check failed',
      ]
        .filter(Boolean)
        .join('\n');

      return details;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Vector DB test failed';
      throw new Error(errorMessage);
    } finally {
      setTestingConnection(null);
    }
  }, []);

  const getToolStatus = useCallback(
    (toolType: string): ToolStatus => {
      // Check new tools status API first
      const statusInfo = toolsStatus[toolType];
      if (statusInfo) {
        if (statusInfo.status === 'connected') {
          return { status: 'connected', label: 'Connected', icon: '✅' };
        } else if (statusInfo.status === 'registered_but_not_connected') {
          return { status: 'registered_but_not_connected', label: 'Not connected', icon: '⚠️' };
        } else if (statusInfo.status === 'unavailable') {
          return { status: 'unavailable', label: 'Not supported', icon: '🔴' };
        }
      }

      // Fallback to legacy logic
      if (toolType === 'vector_db') {
        if (!vectorDBConfig) {
          return { status: 'not_configured', label: 'Not configured', icon: '⚠️' };
        }
        if (vectorDBConfig.enabled) {
          return { status: 'connected', label: 'Enabled', icon: '✅' };
        }
        return { status: 'inactive', label: 'Disabled', icon: '🔌' };
      }

      if (toolType === 'obsidian') {
        return { status: 'local', label: 'Local mode', icon: '🔌' };
      }

      const conn = connections.find((c) => c.tool_type === toolType);
      if (!conn) {
        return { status: 'not_configured', label: 'Not configured', icon: '⚠️' };
      }
      if (conn.enabled) {
        return { status: 'connected', label: 'Connected', icon: '✅' };
      }
      return { status: 'inactive', label: 'Disabled', icon: '🔌' };
    },
    [connections, vectorDBConfig, toolsStatus]
  );

  const getToolStatusForPack = useCallback(
    (toolType: string): ToolStatus => {
      const status = getToolStatus(toolType);
      if (toolType === 'wordpress') {
        return { ...status, label: 'Local mode', icon: '🔌' };
      }
      return status;
    },
    [getToolStatus]
  );

  return {
    loading,
    connections,
    tools,
    vectorDBConfig,
    testingConnection,
    toolsStatus,
    loadTools,
    loadVectorDBConfig,
    loadToolsStatus,
    testConnection,
    testVectorDB,
    getToolStatus,
    getToolStatusForPack,
  };
}
