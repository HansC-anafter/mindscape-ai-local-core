'use client';

import React, { useState, useEffect } from 'react';
import { getApiBaseUrl } from '../../lib/api-url';
import { t } from '../../lib/i18n';

const API_URL = getApiBaseUrl();

interface WorkspaceStat {
  workspace_id: string;
  execution_count: number;
  success_count: number;
  failed_count: number;
  running_count: number;
  last_executed_at: string | null;
}

interface UsageStats {
  playbook_code: string;
  total_executions: number;
  total_workspaces: number;
  workspace_stats: WorkspaceStat[];
}

interface PlaybookUsageStatsProps {
  playbookCode: string;
}

export default function PlaybookUsageStats({ playbookCode }: PlaybookUsageStatsProps) {
  const [stats, setStats] = useState<UsageStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedWorkspaces, setExpandedWorkspaces] = useState<Set<string>>(new Set());

  useEffect(() => {
    const fetchStats = async () => {
      try {
        setLoading(true);
        setError(null);
        const apiUrl = API_URL.startsWith('http') ? API_URL : '';
        const response = await fetch(`${apiUrl}/api/v1/playbooks/${playbookCode}/usage-stats`);

        if (!response.ok) {
          throw new Error(`Failed to fetch usage stats: ${response.statusText}`);
        }

        const data = await response.json();
        setStats(data);
      } catch (err) {
        console.error('Failed to load usage stats:', err);
        setError(err instanceof Error ? err.message : 'Failed to load usage stats');
      } finally {
        setLoading(false);
      }
    };

    if (playbookCode) {
      fetchStats();
    }
  }, [playbookCode]);

  const toggleWorkspace = (workspaceId: string) => {
    setExpandedWorkspaces(prev => {
      const newSet = new Set(prev);
      if (newSet.has(workspaceId)) {
        newSet.delete(workspaceId);
      } else {
        newSet.add(workspaceId);
      }
      return newSet;
    });
  };

  const formatDate = (dateString: string | null) => {
    if (!dateString) return t('neverExecuted');
    try {
      const date = new Date(dateString);
      return date.toLocaleString('en-US', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch {
      return dateString;
    }
  };

  if (loading) {
    return (
      <div className="bg-surface-secondary dark:bg-gray-800 rounded-lg p-4">
        <div className="text-sm text-secondary dark:text-gray-400">{t('loadingUsageStats')}</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-surface-secondary dark:bg-gray-800 rounded-lg p-4">
        <div className="text-sm text-destructive dark:text-red-400">{t('errorLoadingStats', { error })}</div>
      </div>
    );
  }

  if (!stats || stats.total_executions === 0) {
    return (
      <div className="bg-surface-secondary dark:bg-gray-800 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-primary dark:text-gray-100 mb-2">{t('usageStats')}</h3>
        <div className="text-sm text-secondary dark:text-gray-400">{t('noExecutionYet')}</div>
      </div>
    );
  }

  return (
    <div className="bg-surface-secondary dark:bg-gray-800 rounded-lg p-4">
      <h3 className="text-sm font-semibold text-primary dark:text-gray-100 mb-4">{t('usageStats')}</h3>

      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="bg-surface-accent dark:bg-gray-700 rounded-lg p-3">
          <div className="text-xs text-secondary dark:text-gray-400 mb-1">{t('totalExecutions')}</div>
          <div className="text-lg font-semibold text-primary dark:text-gray-100">
            {stats.total_executions}
          </div>
        </div>
        <div className="bg-surface-accent dark:bg-gray-700 rounded-lg p-3">
          <div className="text-xs text-secondary dark:text-gray-400 mb-1">{t('totalWorkspaces')}</div>
          <div className="text-lg font-semibold text-primary dark:text-gray-100">
            {stats.total_workspaces}
          </div>
        </div>
        <div className="bg-surface-accent dark:bg-gray-700 rounded-lg p-3">
          <div className="text-xs text-secondary dark:text-gray-400 mb-1">{t('averageExecutions')}</div>
          <div className="text-lg font-semibold text-primary dark:text-gray-100">
            {stats.total_workspaces > 0
              ? Math.round(stats.total_executions / stats.total_workspaces * 10) / 10
              : 0}
          </div>
        </div>
      </div>

      <div className="space-y-2">
        <h4 className="text-xs font-medium text-primary dark:text-gray-300 mb-2">
          {t('workspaceExecutionStatus')}
        </h4>
        {stats.workspace_stats.length > 0 ? (
          <div className="space-y-2 max-h-96 overflow-y-auto">
            {stats.workspace_stats.map((wsStat) => {
              const isExpanded = expandedWorkspaces.has(wsStat.workspace_id);
              const successRate = wsStat.execution_count > 0
                ? Math.round((wsStat.success_count / wsStat.execution_count) * 100)
                : 0;

              return (
                <div
                  key={wsStat.workspace_id}
                  className="border border-default dark:border-gray-700 rounded-lg p-3 hover:bg-tertiary dark:hover:bg-gray-700/50 transition-colors"
                >
                  <button
                    onClick={() => toggleWorkspace(wsStat.workspace_id)}
                    className="w-full text-left flex items-center justify-between"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-primary dark:text-gray-100 truncate">
                        {wsStat.workspace_id}
                      </div>
                      <div className="text-xs text-secondary dark:text-gray-400 mt-1">
                        {t('executions', { count: wsStat.execution_count })}
                        {wsStat.execution_count > 0 && (
                          <span className="ml-2">
                            ({t('successCount', { count: wsStat.success_count })} / {t('failedCount', { count: wsStat.failed_count })}
                            {wsStat.running_count > 0 && ` / ${t('runningCount', { count: wsStat.running_count })}`})
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="ml-2 flex items-center gap-2">
                      {wsStat.execution_count > 0 && (
                        <div className="text-xs text-secondary dark:text-gray-400">
                          <span className={`font-medium ${
                            successRate >= 80 ? 'text-green-600 dark:text-green-400' :
                            successRate >= 50 ? 'text-yellow-600 dark:text-yellow-400' :
                            'text-red-600 dark:text-red-400'
                          }`}>
                            {successRate}%
                          </span>
                        </div>
                      )}
                      <span className="text-xs text-secondary dark:text-gray-400">
                        {isExpanded ? '▼' : '▶'}
                      </span>
                    </div>
                  </button>

                  {isExpanded && (
                    <div className="mt-3 pt-3 border-t border-default dark:border-gray-700 space-y-2">
                      <div className="grid grid-cols-2 gap-2 text-xs">
                        <div>
                          <span className="text-secondary dark:text-gray-400">{t('success')}:</span>
                          <span className="ml-1 font-medium text-green-600 dark:text-green-400">
                            {wsStat.success_count}
                          </span>
                        </div>
                        <div>
                          <span className="text-secondary dark:text-gray-400">{t('failed')}:</span>
                          <span className="ml-1 font-medium text-red-600 dark:text-red-400">
                            {wsStat.failed_count}
                          </span>
                        </div>
                        {wsStat.running_count > 0 && (
                          <div>
                            <span className="text-secondary dark:text-gray-400">{t('running')}:</span>
                            <span className="ml-1 font-medium text-blue-600 dark:text-blue-400">
                              {wsStat.running_count}
                            </span>
                          </div>
                        )}
                        <div>
                          <span className="text-secondary dark:text-gray-400">{t('lastExecuted')}:</span>
                          <span className="ml-1 font-medium text-primary dark:text-gray-300">
                            {formatDate(wsStat.last_executed_at)}
                          </span>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          <div className="text-sm text-secondary dark:text-gray-400 text-center py-4">
            {t('noWorkspaceExecutionRecords')}
          </div>
        )}
      </div>
    </div>
  );
}

