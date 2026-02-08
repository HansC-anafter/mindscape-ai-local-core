'use client';

import { useState, useEffect, useCallback } from 'react';
import { settingsApi } from '../utils/settingsApi';
import type { BackendConfig, ToolConnection, CapabilityPack } from '../types';

import { getApiBaseUrl } from '../../../lib/api-url';

const API_URL = getApiBaseUrl();

export interface SettingsContext {
  currentTab: string;
  currentSection?: string;
  configSnapshot: {
    backend: {
      mode: string;
      openai_configured: boolean;
      anthropic_configured: boolean;
      remote_crs_configured: boolean;
    };
    tools: {
      total: number;
      connected: number;
      configured: number;
      issues: Array<{
        tool_id: string;
        issue: string;
      }>;
    };
    packs: {
      installed: number;
      enabled: number;
    };
    services: {
      backend: 'healthy' | 'unhealthy' | 'unavailable';
      llm: 'configured' | 'not_configured';
      vector_db: 'connected' | 'not_connected';
      issues: Array<{
        type: string;
        severity: 'error' | 'warning' | 'info';
        message: string;
      }>;
    };
  };
}

export function useSettingsContext(currentTab: string, currentSection?: string) {
  const [context, setContext] = useState<SettingsContext | null>(null);
  const [loading, setLoading] = useState(true);

  const collectConfigState = useCallback(async () => {
    try {
      const profileId = 'default-user';
      const [backendConfig, tools, packs] = await Promise.all([
        settingsApi.get<BackendConfig>(`/api/v1/config/backend?profile_id=${profileId}`, { silent: true }),
        settingsApi.get<ToolConnection[]>(`/api/v1/tools/connections/?profile_id=${profileId}`, { silent: true }),
        settingsApi.get<CapabilityPack[]>('/api/v1/capability-packs/', { silent: true }),
      ]);

      let healthStatus = null;
      try {
        const workspaceId = typeof window !== 'undefined'
          ? localStorage.getItem('currentWorkspaceId')
          : null;
        if (workspaceId) {
          const healthResponse = await fetch(`${API_URL}/api/v1/workspaces/${workspaceId}/health`);
          if (healthResponse.ok) {
            healthStatus = await healthResponse.json();
          }
        } else {
          const generalHealth = await fetch(`${API_URL}/health`);
          if (generalHealth.ok) {
            healthStatus = await generalHealth.json();
          }
        }
      } catch (err) {
        console.error('Failed to fetch health status:', err);
      }

      const snapshot: SettingsContext['configSnapshot'] = {
        backend: {
          mode: backendConfig?.current_mode || 'local',
          openai_configured: backendConfig?.openai_api_key_configured || false,
          anthropic_configured: backendConfig?.anthropic_api_key_configured || false,
          remote_crs_configured: backendConfig?.remote_crs_configured || false,
        },
        tools: {
          total: Array.isArray(tools) ? tools.length : 0,
          connected: Array.isArray(tools) ? tools.filter(t => t.enabled).length : 0,
          configured: Array.isArray(tools) ? tools.length : 0,
          issues: Array.isArray(tools) ? tools.filter(t => !t.enabled).map(t => ({
            tool_id: t.id,
            issue: 'Not connected'
          })) : []
        },
        packs: {
          installed: Array.isArray(packs) ? packs.length : 0,
          enabled: Array.isArray(packs) ? packs.filter(p => p.enabled).length : 0,
        },
        services: {
          backend: healthStatus?.overall_status === 'healthy' ? 'healthy' : (healthStatus ? 'unhealthy' : 'unavailable'),
          // Check explicit flags first, then check providers array in available_backends
          llm: (
            backendConfig?.openai_api_key_configured ||
            backendConfig?.anthropic_api_key_configured ||
            backendConfig?.vertex_ai_configured ||
            (backendConfig?.available_backends?.local as any)?.providers?.includes('vertex-ai') ||
            (backendConfig?.available_backends?.local as any)?.providers?.includes('ollama')
          ) ? 'configured' : 'not_configured',
          vector_db: healthStatus?.vector_db_connected ? 'connected' : 'not_connected',
          issues: healthStatus?.issues || []
        }
      };

      setContext({
        currentTab,
        currentSection,
        configSnapshot: snapshot,
      });
    } catch (err) {
      console.error('Failed to collect config state:', err);
    } finally {
      setLoading(false);
    }
  }, [currentTab, currentSection]);

  useEffect(() => {
    collectConfigState();
    const interval = setInterval(collectConfigState, 30000);
    return () => clearInterval(interval);
  }, [collectConfigState]);

  return { context, loading, refresh: collectConfigState };
}

