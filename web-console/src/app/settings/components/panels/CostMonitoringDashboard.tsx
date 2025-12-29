'use client';

import React, { useState, useEffect } from 'react';
import { t } from '../../../../lib/i18n';
import { Card } from '../Card';
import { InlineAlert } from '../InlineAlert';
import { useParams } from 'next/navigation';
import { getApiBaseUrl } from '../../../../lib/api-url';

interface CostMonitoringData {
  current_usage: number;
  quota: number;
  usage_percentage: number;
  period: 'day' | 'month';
  trend: Array<{
    date: string;
    usage: number;
    quota: number;
  }>;
  breakdown: {
    by_playbook?: Record<string, number>;
    by_model?: Record<string, number>;
  };
}

export function CostMonitoringDashboard() {
  const params = useParams();
  const workspaceId = params?.workspaceId as string;
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<CostMonitoringData | null>(null);
  const [period, setPeriod] = useState<'day' | 'month'>('day');

  useEffect(() => {
    if (!workspaceId) {
      setError('Workspace ID not available');
      setLoading(false);
      return;
    }

    loadCostData();
  }, [workspaceId, period]);

  const loadCostData = async () => {
    try {
      setLoading(true);
      setError(null);

      const apiUrl = getApiBaseUrl();
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/governance/cost/monitoring?period=${period}`
      );

      if (!response.ok) {
        if (response.status === 404) {
          setError('Cost monitoring is only available in Cloud environment');
        } else {
          throw new Error('Failed to load cost monitoring data');
        }
        return;
      }

      const costData = await response.json();
      setData(costData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load cost data');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <Card>
        <div className="text-center py-8 text-secondary dark:text-gray-400">{t('loading')}</div>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <InlineAlert type="error" message={error} onDismiss={() => setError(null)} />
        <p className="text-sm text-secondary dark:text-gray-400 mt-4">
          Cost monitoring is a Cloud-only feature. In Local-Core, you can configure cost quotas but cannot track historical usage.
        </p>
      </Card>
    );
  }

  if (!data) {
    return (
      <Card>
        <div className="text-center py-8 text-secondary dark:text-gray-400">
          No cost data available
        </div>
      </Card>
    );
  }

  const usagePercentage = data.usage_percentage || (data.current_usage / data.quota) * 100;
  const isWarning = usagePercentage >= 80 && usagePercentage < 95;
  const isCritical = usagePercentage >= 95;

  return (
    <Card>
      <div className="mb-4">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-lg font-semibold text-primary dark:text-gray-100">
            {t('costMonitoring')}
          </h3>
          <div className="flex gap-2">
            <button
              onClick={() => setPeriod('day')}
              className={`px-3 py-1 text-xs rounded ${
                period === 'day'
                  ? 'bg-accent dark:bg-blue-700 text-white'
                  : 'bg-surface-secondary dark:bg-gray-700 text-primary dark:text-gray-300'
              }`}
            >
              {t('day')}
            </button>
            <button
              onClick={() => setPeriod('month')}
              className={`px-3 py-1 text-xs rounded ${
                period === 'month'
                  ? 'bg-accent dark:bg-blue-700 text-white'
                  : 'bg-surface-secondary dark:bg-gray-700 text-primary dark:text-gray-300'
              }`}
            >
              {t('month')}
            </button>
          </div>
        </div>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          {t('costMonitoringDescription')}
        </p>
      </div>

      <div className="space-y-6">
        <div className="border border-default dark:border-gray-700 rounded-lg p-4">
          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="text-xs text-secondary dark:text-gray-400 mb-1">
                Current Usage ({period === 'day' ? 'Today' : 'This Month'})
              </div>
              <div className="text-2xl font-bold text-primary dark:text-gray-100">
                ${data.current_usage.toFixed(2)}
              </div>
            </div>
            <div className="text-right">
              <div className="text-xs text-secondary dark:text-gray-400 mb-1">Quota</div>
              <div className="text-2xl font-bold text-primary dark:text-gray-100">
                ${data.quota.toFixed(2)}
              </div>
            </div>
          </div>

          <div className="mb-2">
            <div className="flex justify-between text-xs mb-1">
              <span className="text-secondary dark:text-gray-400">Usage</span>
              <span
                className={`font-medium ${
                  isCritical
                    ? 'text-red-600 dark:text-red-400'
                    : isWarning
                    ? 'text-yellow-600 dark:text-yellow-400'
                    : 'text-primary dark:text-gray-100'
                }`}
              >
                {usagePercentage.toFixed(1)}%
              </span>
            </div>
            <div className="w-full bg-surface-secondary dark:bg-gray-700 rounded-full h-3">
              <div
                className={`h-3 rounded-full ${
                  isCritical ? 'bg-red-500' : isWarning ? 'bg-yellow-500' : 'bg-accent dark:bg-blue-500'
                }`}
                style={{ width: `${Math.min(usagePercentage, 100)}%` }}
              />
            </div>
          </div>
        </div>

        {data.trend && data.trend.length > 0 && (
          <div className="border border-default dark:border-gray-700 rounded-lg p-4">
            <h4 className="text-sm font-semibold text-primary dark:text-gray-100 mb-3">
              {t('costTrend')}
            </h4>
            <div className="space-y-2">
              {data.trend.slice(-7).map((item, index) => {
                const itemPercentage = (item.usage / item.quota) * 100;
                return (
                  <div key={index} className="flex items-center gap-3">
                    <div className="text-xs text-gray-600 dark:text-gray-400 w-20">
                      {new Date(item.date).toLocaleDateString('en-US', {
                        month: 'short',
                        day: 'numeric',
                      })}
                    </div>
                    <div className="flex-1 bg-surface-secondary dark:bg-gray-700 rounded-full h-2">
                      <div
                        className="bg-accent dark:bg-blue-500 h-2 rounded-full"
                        style={{ width: `${Math.min(itemPercentage, 100)}%` }}
                      />
                    </div>
                    <div className="text-xs text-primary dark:text-gray-300 w-24 text-right">
                      ${item.usage.toFixed(2)} / ${item.quota.toFixed(2)}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {data.breakdown && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {data.breakdown.by_playbook && Object.keys(data.breakdown.by_playbook).length > 0 && (
              <div className="border border-default dark:border-gray-700 rounded-lg p-4">
                <h4 className="text-sm font-semibold text-primary dark:text-gray-100 mb-3">
                  {t('costByPlaybook')}
                </h4>
                <div className="space-y-2">
                  {Object.entries(data.breakdown.by_playbook)
                    .sort(([, a], [, b]) => b - a)
                    .slice(0, 5)
                    .map(([playbook, cost]) => (
                      <div key={playbook} className="flex justify-between items-center">
                        <span className="text-xs text-primary dark:text-gray-300 truncate">
                          {playbook}
                        </span>
                        <span className="text-xs font-medium text-primary dark:text-gray-100">
                          ${(cost as number).toFixed(2)}
                        </span>
                      </div>
                    ))}
                </div>
              </div>
            )}

            {data.breakdown.by_model && Object.keys(data.breakdown.by_model).length > 0 && (
              <div className="border border-default dark:border-gray-700 rounded-lg p-4">
                <h4 className="text-sm font-semibold text-primary dark:text-gray-100 mb-3">
                  {t('costByModel')}
                </h4>
                <div className="space-y-2">
                  {Object.entries(data.breakdown.by_model)
                    .sort(([, a], [, b]) => b - a)
                    .slice(0, 5)
                    .map(([model, cost]) => (
                      <div key={model} className="flex justify-between items-center">
                        <span className="text-xs text-primary dark:text-gray-300 truncate">
                          {model}
                        </span>
                        <span className="text-xs font-medium text-primary dark:text-gray-100">
                          ${(cost as number).toFixed(2)}
                        </span>
                      </div>
                    ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}

