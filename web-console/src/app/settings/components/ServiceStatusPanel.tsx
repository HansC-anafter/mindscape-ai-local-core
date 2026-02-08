'use client';

import React, { useState, useEffect } from 'react';
import { t } from '../../../lib/i18n';
import { getApiBaseUrl } from '../../../lib/api-url';

interface ServiceStatus {
  status: 'healthy' | 'unhealthy' | 'unavailable';
  available: boolean;
  error?: string;
  [key: string]: any;
}

interface HealthStatus {
  backend?: ServiceStatus;
  ocr_service?: ServiceStatus;
  llm_configured: boolean;
  llm_provider?: string;
  llm_available: boolean;
  vector_db_connected: boolean;
  tools: Record<string, ServiceStatus>;
  issues: Array<{
    type: string;
    severity: 'error' | 'warning' | 'info';
    message: string;
    action_url?: string;
  }>;
  overall_status: 'healthy' | 'unhealthy';
}

export function ServiceStatusPanel() {
  const [healthStatus, setHealthStatus] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const fetchHealthStatus = async () => {
    try {
      setLoading(true);
      setError(null);

      const apiUrl = getApiBaseUrl();

      // Try to get workspace ID from URL or localStorage
      let workspaceId: string | null = null;
      if (typeof window !== 'undefined') {
        const urlParams = new URLSearchParams(window.location.search);
        workspaceId = urlParams.get('workspace_id') || localStorage.getItem('currentWorkspaceId');
      }

      // If no workspace ID found, try to get first available workspace
      if (!workspaceId) {
        try {
          // Try to get list of workspaces (requires owner_user_id, but we can try with a default)
          // For now, skip workspace-specific health check if no workspace ID
          // Use general health endpoint instead
          const generalHealthResponse = await fetch(`${apiUrl}/health`, {
            method: 'GET',
            headers: {
              'Content-Type': 'application/json',
            },
          });

          if (generalHealthResponse.ok) {
            const generalHealth = await generalHealthResponse.json();
            // Use the detailed health check data if available
            setHealthStatus({
              backend: generalHealth.components?.backend ? {
                status: generalHealth.components.backend === 'healthy' ? 'healthy' : 'unhealthy',
                available: true,
              } : {
                status: 'healthy',
                available: true,
              },
              llm_configured: generalHealth.llm_configured || false,
              llm_available: generalHealth.llm_available || false,
              llm_provider: generalHealth.llm_provider,
              vector_db_connected: generalHealth.vector_db_connected || false,
              tools: {},
              issues: generalHealth.issues || [{
                type: 'workspace_not_selected',
                severity: 'info',
                message: t('workspaceNotSelected' as any),
              }],
              overall_status: generalHealth.status || 'healthy',
            });
            setLastUpdated(new Date());
            return;
          }
        } catch (e) {
          // Fall through to error handling
        }
      }

      // If we have a workspace ID, try workspace-specific health check
      if (workspaceId) {
        const response = await fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}/health`, {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
          },
        });

        if (!response.ok) {
          // If workspace not found, show info message instead of error
          if (response.status === 404) {
            setHealthStatus({
              backend: {
                status: 'unavailable',
                available: false,
                error: 'Workspace not found',
              },
              llm_configured: false,
              llm_available: false,
              vector_db_connected: false,
              tools: {},
              issues: [{
                type: 'workspace_not_found',
                severity: 'warning',
                message: t('workspaceNotFound', { workspaceId: workspaceId || '' }),
              }],
              overall_status: 'unhealthy',
            });
            setLastUpdated(new Date());
            return;
          }
          throw new Error(`Health check failed: ${response.statusText}`);
        }

        const data = await response.json();
        setHealthStatus(data);
        setLastUpdated(new Date());
      } else {
        // No workspace ID and general health also failed
        throw new Error(t('noWorkspaceSelected' as any));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch health status');
      console.error('Health check error:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHealthStatus();
  }, []);

  useEffect(() => {
    if (!autoRefresh) return;

    const interval = setInterval(() => {
      fetchHealthStatus();
    }, 30000);

    return () => clearInterval(interval);
  }, [autoRefresh]);

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'healthy':
      case 'ok':
        return 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300 border-green-200 dark:border-green-800';
      case 'unhealthy':
      case 'warning':
        return 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300 border-yellow-200 dark:border-yellow-800';
      case 'unavailable':
      case 'error':
        return 'bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300 border-red-200 dark:border-red-800';
      default:
        return 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-300 border-gray-200 dark:border-gray-600';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'healthy':
      case 'ok':
        return '✓';
      case 'unhealthy':
      case 'warning':
        return '⚠';
      case 'unavailable':
      case 'error':
        return '✗';
      default:
        return '?';
    }
  };

  const ServiceCard = ({
    title,
    status,
    details
  }: {
    title: string;
    status: ServiceStatus | undefined;
    details?: Record<string, any>
  }) => {
    if (!status) return null;

    const statusValue = status.status || (status.available ? 'healthy' : 'unavailable');
    const statusColor = getStatusColor(statusValue);
    const statusIcon = getStatusIcon(statusValue);

    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 shadow-sm">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">{title}</h3>
          <span className={`px-2 py-1 rounded text-xs font-medium border ${statusColor}`}>
            {statusIcon} {statusValue}
          </span>
        </div>
        {status.error && (
          <p className="text-xs text-red-600 dark:text-red-400 mt-1">{status.error}</p>
        )}
        {details && Object.keys(details).length > 0 && (
          <div className="mt-2 space-y-1">
            {Object.entries(details).map(([key, value]) => (
              <div key={key} className="text-xs text-gray-600 dark:text-gray-400">
                <span className="font-medium">{key}:</span> {String(value)}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  if (loading && !healthStatus) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-gray-500 dark:text-gray-400">{t('loadingServiceStatus' as any)}</div>
      </div>
    );
  }

  if (error && !healthStatus) {
    return (
      <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
        <p className="text-red-800 dark:text-red-300 font-medium">{t('failedToLoadServiceStatus' as any)}</p>
        <p className="text-red-600 dark:text-red-400 text-sm mt-1">{error}</p>
        <button
          onClick={fetchHealthStatus}
          className="mt-3 px-4 py-2 bg-red-600 dark:bg-red-700 text-white rounded-md text-sm hover:bg-red-700 dark:hover:bg-red-600"
        >
          {t('retry' as any)}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header with refresh controls */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">{t('serviceStatus' as any)}</h2>
          {lastUpdated && (
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              {t('lastUpdated' as any)} {lastUpdated.toLocaleTimeString()}
            </p>
          )}
        </div>
        <div className="flex items-center space-x-3">
          <label className="flex items-center text-sm text-gray-600 dark:text-gray-400">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="mr-2"
            />
            {t('autoRefreshInterval' as any)}
          </label>
          <button
            onClick={fetchHealthStatus}
            disabled={loading}
            className="px-4 py-2 bg-gray-600 dark:bg-gray-700 text-white rounded-md text-sm hover:bg-gray-700 dark:hover:bg-gray-600 disabled:opacity-50"
          >
            {loading ? t('refreshing' as any) : t('refresh' as any)}
          </button>
        </div>
      </div>

      {/* Overall Status */}
      {healthStatus && (
        <div className={`rounded-lg border p-4 ${
          healthStatus.overall_status === 'healthy'
            ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800'
            : 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800'
        }`}>
          <div className="flex items-center">
            <span className={`text-2xl mr-2 ${
              healthStatus.overall_status === 'healthy' ? 'text-green-600 dark:text-green-400' : 'text-yellow-600 dark:text-yellow-400'
            }`}>
              {healthStatus.overall_status === 'healthy' ? '✓' : '⚠'}
            </span>
            <div>
              <p className="font-medium text-gray-900 dark:text-gray-100">
                {t('overallStatus' as any)} {healthStatus.overall_status.toUpperCase()}
              </p>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                {healthStatus.overall_status === 'healthy'
                  ? t('allServicesOperational' as any)
                  : t('someServicesHaveIssues' as any)}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Service Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {healthStatus?.backend && (
          <ServiceCard
            title={t('backendAPI' as any)}
            status={healthStatus.backend}
            details={{
              url: healthStatus.backend.url,
            }}
          />
        )}

        {healthStatus?.ocr_service && (
          <ServiceCard
            title={t('ocrService' as any)}
            status={healthStatus.ocr_service}
            details={{
              gpu_available: healthStatus.ocr_service.gpu_available ? 'Yes' : 'No',
              gpu_enabled: healthStatus.ocr_service.gpu_enabled ? 'Yes' : 'No',
            }}
          />
        )}

        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 shadow-sm">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">{t('llmConfiguration' as any)}</h3>
            <span className={`px-2 py-1 rounded text-xs font-medium border ${
              healthStatus?.llm_available
                ? 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300 border-green-200 dark:border-green-800'
                : 'bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300 border-red-200 dark:border-red-800'
            }`}>
              {healthStatus?.llm_available ? `✓ ${t('configured' as any)}` : `✗ ${t('notConfigured' as any)}`}
            </span>
          </div>
          {healthStatus?.llm_provider && (
            <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">
              {t('provider' as any)} {healthStatus.llm_provider}
            </p>
          )}
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 shadow-sm">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">{t('vectorDB' as any)}</h3>
            <span className={`px-2 py-1 rounded text-xs font-medium border ${
              healthStatus?.vector_db_connected
                ? 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300 border-green-200 dark:border-green-800'
                : 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300 border-yellow-200 dark:border-yellow-800'
            }`}>
              {healthStatus?.vector_db_connected ? `✓ ${t('connected' as any)}` : `⚠ ${t('notConnected' as any)}`}
            </span>
          </div>
        </div>
      </div>

      {/* Tool Connections */}
      {healthStatus?.tools && Object.keys(healthStatus.tools).length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-3">{t('toolConnections' as any)}</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {Object.entries(healthStatus.tools).map(([toolName, toolStatus]) => (
              <ServiceCard
                key={toolName}
                title={toolName.charAt(0).toUpperCase() + toolName.slice(1).replace('_', ' ')}
                status={toolStatus as ServiceStatus}
                details={{
                  connections: toolStatus.connection_count || 0,
                }}
              />
            ))}
          </div>
        </div>
      )}

      {/* Issues */}
      {healthStatus?.issues && healthStatus.issues.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-3">{t('issuesAndRecommendations' as any)}</h3>
          <div className="space-y-2">
            {healthStatus.issues.map((issue, index) => (
              <div
                key={index}
                className={`rounded-lg border p-3 ${
                  issue.severity === 'error'
                    ? 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800'
                    : issue.severity === 'warning'
                    ? 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800'
                    : 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800'
                }`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <p className={`text-sm font-medium ${
                      issue.severity === 'error'
                        ? 'text-red-800 dark:text-red-300'
                        : issue.severity === 'warning'
                        ? 'text-yellow-800 dark:text-yellow-300'
                        : 'text-blue-800 dark:text-blue-300'
                    }`}>
                      {issue.message}
                    </p>
                  </div>
                  {issue.action_url && (
                    <a
                      href={issue.action_url}
                      className="ml-3 text-xs text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-300 underline"
                    >
                      {t('fix' as any)}
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
