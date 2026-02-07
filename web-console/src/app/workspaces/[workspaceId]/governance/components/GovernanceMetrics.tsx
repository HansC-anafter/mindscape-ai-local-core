'use client';

import React, { useState, useEffect } from 'react';
import { t } from '@/lib/i18n';
import { getApiBaseUrl } from '../../../../../lib/api-url';

interface GovernanceMetricsData {
  period: 'day' | 'month';
  rejection_rate: {
    cost: number;
    node: number;
    policy: number;
    preflight: number;
    overall: number;
  };
  cost_trend: Array<{
    date: string;
    usage: number;
    quota: number;
    rejection_count: number;
  }>;
  violation_frequency: {
    policy?: {
      role_violation: number;
      data_domain_violation: number;
      pii_violation: number;
    };
    node?: {
      blacklist: number;
      risk_label: number;
      throttle: number;
    };
  };
  preflight_failure_reasons?: {
    missing_inputs: number;
    missing_credentials: number;
    environment_issues: number;
  };
}

interface GovernanceMetricsProps {
  workspaceId: string;
}

export function GovernanceMetrics({ workspaceId }: GovernanceMetricsProps) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<GovernanceMetricsData | null>(null);
  const [period, setPeriod] = useState<'day' | 'month'>('day');

  useEffect(() => {
    loadMetrics();
  }, [workspaceId, period]);

  const loadMetrics = async () => {
    try {
      setLoading(true);
      setError(null);

      const apiUrl = getApiBaseUrl();
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/governance/metrics?period=${period}`
      );

      if (!response.ok) {
        if (response.status === 404) {
          setError('Governance metrics are only available in Cloud environment');
        } else {
          throw new Error('Failed to load governance metrics');
        }
        return;
      }

      const metricsData = await response.json();
      setData(metricsData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load metrics');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="text-center py-8 text-secondary dark:text-gray-400">
        {t('loading' as any) || 'Loading...'}
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
        <p className="text-sm text-red-800 dark:text-red-300">{error}</p>
        <p className="text-xs text-red-600 dark:text-red-400 mt-2">
          Governance metrics are a Cloud-only feature. In Local-Core, you can view individual decisions but cannot see aggregated metrics.
        </p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="text-center py-8 text-secondary dark:text-gray-400">
        {t('noMetricsAvailable' as any) || 'No metrics available'}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-primary dark:text-gray-100">
          {t('governanceMetrics' as any) || 'Governance Metrics'}
        </h2>
        <div className="flex gap-2">
          <button
            onClick={() => setPeriod('day')}
            className={`px-3 py-1 text-xs rounded ${
              period === 'day'
                ? 'bg-blue-600 dark:bg-blue-700 text-white'
                : 'bg-surface-secondary dark:bg-gray-700 text-primary dark:text-gray-300'
            }`}
          >
            {t('day' as any) || 'Day'}
          </button>
          <button
            onClick={() => setPeriod('month')}
            className={`px-3 py-1 text-xs rounded ${
              period === 'month'
                ? 'bg-blue-600 dark:bg-blue-700 text-white'
                : 'bg-surface-secondary dark:bg-gray-700 text-primary dark:text-gray-300'
            }`}
          >
            {t('month' as any) || 'Month'}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
        <div className="bg-surface-accent dark:bg-gray-800 rounded-lg border border-default dark:border-gray-700 p-4">
          <div className="text-xs text-secondary dark:text-gray-400 mb-1">
            {t('overallRejectionRate' as any) || 'Overall Rejection Rate'}
          </div>
          <div className="text-2xl font-bold text-primary dark:text-gray-100">
            {(data.rejection_rate.overall * 100).toFixed(1)}%
          </div>
        </div>
        <div className="bg-surface-accent dark:bg-gray-800 rounded-lg border border-default dark:border-gray-700 p-4">
          <div className="text-xs text-secondary dark:text-gray-400 mb-1">
            {t('costRejectionRate' as any) || 'Cost Rejection Rate'}
          </div>
          <div className="text-2xl font-bold text-red-600 dark:text-red-400">
            {(data.rejection_rate.cost * 100).toFixed(1)}%
          </div>
        </div>
        <div className="bg-surface-accent dark:bg-gray-800 rounded-lg border border-default dark:border-gray-700 p-4">
          <div className="text-xs text-secondary dark:text-gray-400 mb-1">
            {t('nodeRejectionRate' as any) || 'Node Rejection Rate'}
          </div>
          <div className="text-2xl font-bold text-orange-600 dark:text-orange-400">
            {(data.rejection_rate.node * 100).toFixed(1)}%
          </div>
        </div>
        <div className="bg-surface-accent dark:bg-gray-800 rounded-lg border border-default dark:border-gray-700 p-4">
          <div className="text-xs text-secondary dark:text-gray-400 mb-1">
            {t('policyRejectionRate' as any) || 'Policy Rejection Rate'}
          </div>
          <div className="text-2xl font-bold text-purple-600 dark:text-purple-400">
            {(data.rejection_rate.policy * 100).toFixed(1)}%
          </div>
        </div>
        <div className="bg-surface-accent dark:bg-gray-800 rounded-lg border border-default dark:border-gray-700 p-4">
          <div className="text-xs text-secondary dark:text-gray-400 mb-1">
            {t('preflightRejectionRate' as any) || 'Preflight Rejection Rate'}
          </div>
          <div className="text-2xl font-bold text-yellow-600 dark:text-yellow-400">
            {(data.rejection_rate.preflight * 100).toFixed(1)}%
          </div>
        </div>
      </div>

      {data.cost_trend && data.cost_trend.length > 0 && (
        <div className="bg-surface-accent dark:bg-gray-800 rounded-lg border border-default dark:border-gray-700 p-4">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-4">
            {t('costTrend' as any) || 'Cost Trend'}
          </h3>
          <div className="space-y-2">
            {data.cost_trend.slice(-7).map((item, index) => {
              const usagePercentage = (item.usage / item.quota) * 100;
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
                      className="bg-blue-500 h-2 rounded-full"
                      style={{ width: `${Math.min(usagePercentage, 100)}%` }}
                    />
                  </div>
                  <div className="text-xs text-primary dark:text-gray-300 w-32 text-right">
                    ${item.usage.toFixed(2)} / ${item.quota.toFixed(2)}
                  </div>
                  {item.rejection_count > 0 && (
                    <div className="text-xs text-red-600 dark:text-red-400 w-16 text-right">
                      {item.rejection_count} rejections
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {data.violation_frequency && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {data.violation_frequency.policy && (
            <div className="bg-surface-accent dark:bg-gray-800 rounded-lg border border-default dark:border-gray-700 p-4">
              <h3 className="text-sm font-semibold text-primary dark:text-gray-100 mb-3">
                {t('policyViolations' as any) || 'Policy Violations'}
              </h3>
              <div className="space-y-2">
                <div className="flex justify-between">
                  <span className="text-xs text-secondary dark:text-gray-400">
                    {t('roleViolation' as any) || 'Role Violation'}
                  </span>
                  <span className="text-xs font-medium text-primary dark:text-gray-100">
                    {data.violation_frequency.policy.role_violation}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-xs text-secondary dark:text-gray-400">
                    {t('dataDomainViolation' as any) || 'Data Domain Violation'}
                  </span>
                  <span className="text-xs font-medium text-primary dark:text-gray-100">
                    {data.violation_frequency.policy.data_domain_violation}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-xs text-secondary dark:text-gray-400">
                    {t('piiViolation' as any) || 'PII Violation'}
                  </span>
                  <span className="text-xs font-medium text-primary dark:text-gray-100">
                    {data.violation_frequency.policy.pii_violation}
                  </span>
                </div>
              </div>
            </div>
          )}

          {data.violation_frequency.node && (
            <div className="bg-surface-accent dark:bg-gray-800 rounded-lg border border-default dark:border-gray-700 p-4">
              <h3 className="text-sm font-semibold text-primary dark:text-gray-100 mb-3">
                {t('nodeViolations' as any) || 'Node Violations'}
              </h3>
              <div className="space-y-2">
                <div className="flex justify-between">
                  <span className="text-xs text-secondary dark:text-gray-400">
                    {t('blacklist' as any) || 'Blacklist'}
                  </span>
                  <span className="text-xs font-medium text-primary dark:text-gray-100">
                    {data.violation_frequency.node.blacklist}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-xs text-secondary dark:text-gray-400">
                    {t('riskLabel' as any) || 'Risk Label'}
                  </span>
                  <span className="text-xs font-medium text-primary dark:text-gray-100">
                    {data.violation_frequency.node.risk_label}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-xs text-secondary dark:text-gray-400">
                    {t('throttle' as any) || 'Throttle'}
                  </span>
                  <span className="text-xs font-medium text-primary dark:text-gray-100">
                    {data.violation_frequency.node.throttle}
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {data.preflight_failure_reasons && (
        <div className="bg-surface-accent dark:bg-gray-800 rounded-lg border border-default dark:border-gray-700 p-4">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">
            {t('preflightFailureReasons' as any) || 'Preflight Failure Reasons'}
          </h3>
          <div className="space-y-2">
            <div className="flex justify-between">
              <span className="text-xs text-gray-600 dark:text-gray-400">
                {t('missingInputs' as any) || 'Missing Inputs'}
              </span>
              <span className="text-xs font-medium text-gray-900 dark:text-gray-100">
                {data.preflight_failure_reasons.missing_inputs}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-xs text-gray-600 dark:text-gray-400">
                {t('missingCredentials' as any) || 'Missing Credentials'}
              </span>
              <span className="text-xs font-medium text-gray-900 dark:text-gray-100">
                {data.preflight_failure_reasons.missing_credentials}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-xs text-gray-600 dark:text-gray-400">
                {t('environmentIssues' as any) || 'Environment Issues'}
              </span>
              <span className="text-xs font-medium text-gray-900 dark:text-gray-100">
                {data.preflight_failure_reasons.environment_issues}
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

