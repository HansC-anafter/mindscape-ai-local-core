'use client';

import { useState, useEffect, useCallback } from 'react';
import { t } from '../../../lib/i18n';
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
  label: t('statusNotConfigured'),
  icon: '⚠️',
});

export function useTools(): UseToolsReturn {
  const [loading, setLoading] = useState(false);
  const [connections, setConnections] = useState<ToolConnection[]>([]);
  const [tools, setTools] = useState<RegisteredTool[]>([]);
  const [vectorDBConfig, setVectorDBConfig] = useState<VectorDBConfig | null>(null);
  const [testingConnection, setTestingConnection] = useState<string | null>(null);
  const [toolsStatus, setToolsStatus] = useState<Record<string, ToolStatusInfo>>({});
  const [vectorDBConnected, setVectorDBConnected] = useState<boolean | null>(null);
  const [unsplashConfigured, setUnsplashConfigured] = useState<boolean | null>(null);

  const loadTools = useCallback(async () => {
    setLoading(true);
    try {
      const profileId = 'default-user';
      const [connData, toolsData] = await Promise.all([
        settingsApi.get<ToolConnection[]>(`/api/v1/tools/connections/?profile_id=${profileId}`, { silent: true }),
        settingsApi.get<RegisteredTool[]>('/api/v1/tools?enabled_only=false').catch((err) => {
          console.debug('Failed to load tools:', err);
          return [];
        }),
      ]);
      setConnections(connData || []);
      setTools(toolsData || []);
    } catch (err) {
      console.debug('Failed to load tools:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadVectorDBConfig = useCallback(async () => {
    try {
      const data = await settingsApi.get<VectorDBConfig>('/api/v1/vector-db/config', { silent: true });
      // If data is empty (501/404 handled by settingsApi), use default config
      if (data && Object.keys(data).length > 0) {
        setVectorDBConfig({
          ...data,
          enabled: data.enabled !== undefined ? data.enabled : true,
        });
      } else {
        // 501 (Not Implemented) is expected when vector DB adapter is not configured
        // Silently fallback to default config
        setVectorDBConfig({ mode: 'local', enabled: true });
      }
    } catch (err) {
      // Fallback to default config on any error
      setVectorDBConfig({ mode: 'local', enabled: true });
    }
  }, []);

  const loadToolsStatus = useCallback(async () => {
    try {
      const response = await settingsApi.get<{ tools: Record<string, ToolStatusInfo> }>('/api/v1/tools/status');
      setToolsStatus(response.tools || {});
    } catch (err) {
      console.debug('Failed to load tools status:', err);
      setToolsStatus({});
    }
  }, []);

  const loadVectorDBHealthStatus = useCallback(async () => {
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const response = await fetch(`${apiUrl}/health`);
      if (response.ok) {
        const health = await response.json();
        // Check both top-level and components.vector_db_connected
        const connected = health.vector_db_connected ?? health.components?.vector_db_connected ?? false;
        console.debug('Vector DB health status:', connected, health);
        setVectorDBConnected(connected);
      } else {
        console.debug('Health endpoint returned non-OK status:', response.status);
        setVectorDBConnected(null);
      }
    } catch (err) {
      console.debug('Failed to load vector DB health status:', err);
      setVectorDBConnected(null);
    }
  }, []);

  const loadUnsplashConfig = useCallback(async () => {
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const workspaceId = typeof window !== 'undefined' ? window.location.pathname.match(/\/workspaces\/([^\/]+)/)?.[1] : null;
      if (!workspaceId) {
        setUnsplashConfigured(null);
        return;
      }
      const response = await fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}/web-generation/unsplash/config`);
      if (response.ok) {
        const config = await response.json();
        setUnsplashConfigured(config.configured || false);
      } else if (response.status === 404) {
        setUnsplashConfigured(false);
      } else {
        setUnsplashConfigured(null);
      }
    } catch (err) {
      console.debug('Failed to load Unsplash config:', err);
      setUnsplashConfigured(null);
    }
  }, []);

  // Load vector DB health status on mount
  useEffect(() => {
    loadVectorDBHealthStatus();
    loadUnsplashConfig();
  }, [loadVectorDBHealthStatus, loadUnsplashConfig]);

  // Listen to tool status change events for real-time updates
  useEffect(() => {
    const cleanupStatus = listenToToolStatusChanged(() => {
      // Refresh tool status when any tool status changes
      loadToolsStatus();
      loadVectorDBHealthStatus();
    });

    const cleanupConfig = listenToToolConfigUpdated(() => {
      // Refresh all tool data when config is updated
      loadTools();
      loadVectorDBConfig();
      loadToolsStatus();
      loadVectorDBHealthStatus();
      loadUnsplashConfig();
    });

    return () => {
      cleanupStatus();
      cleanupConfig();
    };
  }, [loadTools, loadVectorDBConfig, loadToolsStatus, loadVectorDBHealthStatus]);

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
      // For vector_db, prioritize health check over tools status API
      if (toolType === 'vector_db') {
        // Use actual connection status from health check if available
        // Priority: health check > tools status API > config
        if (vectorDBConnected !== null) {
          if (vectorDBConnected) {
            return { status: 'connected', label: t('statusConnected'), icon: '✅' };
          } else {
            return { status: 'not_configured', label: t('statusNotConnected'), icon: '⚠️' };
          }
        }
        // Fallback to tools status API
        const statusInfo = toolsStatus[toolType];
        if (statusInfo) {
          if (statusInfo.status === 'connected') {
            return { status: 'connected', label: t('statusConnected'), icon: '✅' };
          } else if (statusInfo.status === 'registered_but_not_connected') {
            return { status: 'registered_but_not_connected', label: t('statusNotConnected'), icon: '⚠️' };
          } else if (statusInfo.status === 'unavailable') {
            return { status: 'unavailable', label: t('statusNotSupported'), icon: '🔴' };
          }
        }
        // Fallback to config-based status
        if (!vectorDBConfig) {
          return { status: 'not_configured', label: t('statusNotConfigured'), icon: '⚠️' };
        }
        if (vectorDBConfig.enabled) {
          return { status: 'connected', label: t('statusEnabled'), icon: '✅' };
        }
        return { status: 'inactive', label: t('statusDisabled'), icon: '🔌' };
      }

      // For Unsplash, check workspace settings
      if (toolType === 'unsplash') {
        if (unsplashConfigured === true) {
          return { status: 'connected', label: t('statusConnected'), icon: '✅' };
        } else if (unsplashConfigured === false) {
          return { status: 'not_configured', label: t('statusNotConfigured'), icon: '⚠️' };
        }
        return getDefaultToolStatus();
      }

      // For other tools, check tools status API first
      const statusInfo = toolsStatus[toolType];
      if (statusInfo) {
        if (statusInfo.status === 'connected') {
          return { status: 'connected', label: t('statusConnected'), icon: '✅' };
        } else if (statusInfo.status === 'registered_but_not_connected') {
          return { status: 'registered_but_not_connected', label: t('statusNotConnected'), icon: '⚠️' };
        } else if (statusInfo.status === 'unavailable') {
          return { status: 'unavailable', label: t('statusNotSupported'), icon: '🔴' };
        }
      }

      if (toolType === 'obsidian') {
        return { status: 'local', label: t('statusLocalMode'), icon: '🔌' };
      }

      const conn = connections.find((c) => c.tool_type === toolType);
      if (!conn) {
        return { status: 'not_configured', label: t('statusNotConfigured'), icon: '⚠️' };
      }
      if (conn.enabled) {
        return { status: 'connected', label: t('statusConnected'), icon: '✅' };
      }
      return { status: 'inactive', label: t('statusDisabled'), icon: '🔌' };
    },
    [connections, vectorDBConfig, toolsStatus, vectorDBConnected, unsplashConfigured]
  );

  const getToolStatusForPack = useCallback(
    (toolType: string): ToolStatus => {
      const status = getToolStatus(toolType);
      if (toolType === 'wordpress') {
        return { ...status, label: t('statusLocalMode'), icon: '🔌' };
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
