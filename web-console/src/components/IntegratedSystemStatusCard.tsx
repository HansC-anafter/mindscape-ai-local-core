'use client';

import React from 'react';
import Link from 'next/link';
import { t } from '@/lib/i18n';

interface IntegratedSystemStatusProps {
  systemStatus: {
    llm_configured: boolean;
    llm_provider?: string;
    vector_db_connected: boolean;
    tools: Record<string, {
      connected: boolean;
      status: string;
      connection_count?: number;
    }>;
    critical_issues_count: number;
    has_issues: boolean;
  };
  workspace: {
    primary_project_id?: string;
    default_playbook_id?: string;
    default_locale?: string;
  };
  workspaceId: string;
  onRefresh?: () => void;
}

// Format provider name for display
const formatProviderName = (provider?: string): string => {
  if (!provider) return '';

  const providerMap: Record<string, string> = {
    'openai': 'OpenAI',
    'anthropic': 'Anthropic',
    'vertex-ai': 'Vertex AI',
    'vertex_ai': 'Vertex AI',
    'local': 'Local',
    'remote_crs': 'Remote CRS',
  };

  return providerMap[provider.toLowerCase()] || provider.charAt(0).toUpperCase() + provider.slice(1).replace(/-/g, ' ').replace(/_/g, ' ');
};

export default function IntegratedSystemStatusCard({
  systemStatus,
  workspace,
  workspaceId,
  onRefresh
}: IntegratedSystemStatusProps) {

  return (
    <div className="bg-surface-secondary dark:bg-gray-800 border dark:border-gray-700 rounded p-2 shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <h3 className="font-semibold text-primary dark:text-gray-100 text-xs">{t('systemStatusAndTools' as any)}</h3>
        {systemStatus.has_issues && (
          <span className="text-[10px] text-red-600 dark:text-red-400 font-medium">
            {systemStatus.critical_issues_count} {t('issuesCount' as any)}
          </span>
        )}
      </div>

      {/* Core System Status */}
      <div className="space-y-1.5 text-xs mb-2">
        <div className="flex items-center justify-between">
          <span className="text-secondary dark:text-gray-400 text-xs">{t('llmConnectionStatus' as any)}</span>
          <div className="flex items-center gap-1.5">
            {systemStatus.llm_configured ? (
              <svg className="w-3 h-3 text-green-500 dark:text-green-400" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
            ) : (
              <svg className="w-3 h-3 text-red-500 dark:text-red-400" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
              </svg>
            )}
            <span className={`text-xs ${systemStatus.llm_configured ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
              {systemStatus.llm_configured
                ? formatProviderName(systemStatus.llm_provider) || t('available' as any)
                : t('notConfigured' as any)}
            </span>
          </div>
        </div>

        <div className="flex items-center justify-between">
          <span className="text-secondary dark:text-gray-400 text-xs">{t('vectorDB' as any)}</span>
          <div className="flex items-center gap-1.5">
            <svg className="w-3 h-3 text-green-500 dark:text-green-400" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
            </svg>
            <span className={`text-xs ${systemStatus.vector_db_connected ? 'text-green-600 dark:text-green-400' : 'text-yellow-600 dark:text-yellow-400'}`}>
              {systemStatus.vector_db_connected ? t('connected' as any) : t('notConnected' as any)}
            </span>
          </div>
        </div>
      </div>


      {/* Tool Connections Details */}
      <div className="mt-2 pt-2 border-t dark:border-gray-700 space-y-1.5">
          <div className="text-[10px] text-secondary dark:text-gray-400 mb-1">{t('toolConnections' as any)}</div>
          {Object.entries(systemStatus.tools).map(([tool, status]) => (
            <div key={tool} className="flex items-center justify-between text-xs">
              <span className="text-secondary dark:text-gray-400 capitalize">{tool}</span>
              <div className="flex items-center gap-1.5">
                {status.connected ? (
                  <>
                    <svg className="w-3 h-3 text-green-500 dark:text-green-400" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                    <span className="text-xs text-green-600 dark:text-green-400">{t('connected' as any)}</span>
                  </>
                ) : (
                  <>
                    <svg className="w-3 h-3 text-gray-400 dark:text-gray-500" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                    </svg>
                    <Link
                      href="/settings"
                      className="text-xs text-accent dark:text-blue-400 hover:opacity-80 dark:hover:text-blue-300 underline"
                    >
                      {t('goToSettings' as any)}
                    </Link>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>

      {/* Workspace Settings (if any) */}
      {(workspace.primary_project_id || workspace.default_playbook_id || workspace.default_locale) && (
        <div className="mt-2 pt-2 border-t dark:border-gray-700">
          <div className="text-[10px] text-secondary dark:text-gray-400 mb-1">{t('workspaceSettingsStatus' as any)}</div>
          {workspace.primary_project_id && (
            <div className="mb-1.5">
              <div className="text-[10px] text-secondary dark:text-gray-400 mb-0.5">{t('primaryProject' as any)}</div>
              <div className="text-xs text-primary dark:text-gray-100">{workspace.primary_project_id}</div>
            </div>
          )}
          {workspace.default_playbook_id && (
            <div className="mb-1.5">
              <div className="text-[10px] text-secondary dark:text-gray-400 mb-0.5">{t('defaultPlaybook' as any)}</div>
              <div className="text-xs text-primary dark:text-gray-100">{workspace.default_playbook_id}</div>
            </div>
          )}
          {workspace.default_locale && (
            <div className="mb-1.5">
              <div className="text-[10px] text-secondary dark:text-gray-400 mb-0.5">{t('locale' as any)}</div>
              <div className="text-xs text-primary dark:text-gray-100">{workspace.default_locale}</div>
            </div>
          )}
        </div>
      )}

      {/* Footer Link */}
      <div className="mt-2 pt-2 border-t dark:border-gray-700">
        <Link
          href="/settings"
          className="text-[10px] text-accent dark:text-blue-400 hover:opacity-80 dark:hover:text-blue-300 underline"
        >
          {t('goToSettings' as any)} →
        </Link>
      </div>
    </div>
  );
}
