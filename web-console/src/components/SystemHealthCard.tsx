'use client';

import React from 'react';
import Link from 'next/link';
import { t } from '@/lib/i18n';

interface HealthIssue {
  type: string;
  severity: 'error' | 'warning' | 'info';
  message: string;
  action_url?: string;
  tool_type?: string;
}

interface SystemHealth {
  llm_configured: boolean;
  llm_provider?: string;
  llm_available: boolean;
  vector_db_connected: boolean;
  tools: Record<string, {
    connected: boolean;
    status: string;
    connection_count?: number;
    error?: string;
  }>;
  issues: HealthIssue[];
  overall_status: 'healthy' | 'unhealthy';
}

interface SystemHealthCardProps {
  health: SystemHealth;
  workspaceId: string;
  onDismiss?: () => void;
}

export default function SystemHealthCard({
  health,
  workspaceId,
  onDismiss
}: SystemHealthCardProps) {
  const errorIssues = health.issues.filter(i => i.severity === 'error');
  const warningIssues = health.issues.filter(i => i.severity === 'warning');
  const infoIssues = health.issues.filter(i => i.severity === 'info');

  if (health.overall_status === 'healthy' && health.issues.length === 0) {
    return null;
  }

  return (
    <div className="mb-4 p-4 bg-white border rounded-lg shadow-sm">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className={`w-3 h-3 rounded-full ${
            health.overall_status === 'healthy' ? 'bg-green-500' : 'bg-yellow-500'
          }`} />
          <h3 className="font-semibold text-gray-900">
            {health.overall_status === 'healthy' ? t('systemHealthNormal') : t('systemHealthStatus')}
          </h3>
        </div>
        {onDismiss && (
          <button
            onClick={onDismiss}
            className="text-gray-400 hover:text-gray-600 transition-colors"
            aria-label={t('close')}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        )}
      </div>

      {errorIssues.length > 0 && (
        <div className="mb-3">
          <div className="text-sm font-medium text-red-700 mb-2">{t('needsImmediateAction')}</div>
          <ul className="space-y-2">
            {errorIssues.map((issue, idx) => (
              <li key={idx} className="flex items-start gap-2">
                <svg className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <div className="flex-1">
                  <p className="text-sm text-red-700">{issue.message}</p>
                  {issue.action_url && (
                    <Link
                      href={issue.action_url}
                      className="text-xs text-blue-600 hover:text-blue-800 underline mt-1 inline-block"
                    >
                      {t('goToSettings')} →
                    </Link>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {warningIssues.length > 0 && (
        <div className="mb-3">
          <div className="text-sm font-medium text-yellow-700 mb-2">{t('recommendedAction')}</div>
          <ul className="space-y-2">
            {warningIssues.map((issue, idx) => (
              <li key={idx} className="flex items-start gap-2">
                <svg className="w-5 h-5 text-yellow-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <div className="flex-1">
                  <p className="text-sm text-yellow-700">{issue.message}</p>
                  {issue.action_url && (
                    <Link
                      href={issue.action_url}
                      className="text-xs text-blue-600 hover:text-blue-800 underline mt-1 inline-block"
                    >
                      {t('viewDetails')} →
                    </Link>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {infoIssues.length > 0 && errorIssues.length === 0 && warningIssues.length === 0 && (
        <div className="text-sm text-gray-600">
          <p className="mb-2">{t('systemHealthMissingConfig')}</p>
          <ul className="space-y-1 list-disc list-inside">
            {infoIssues.map((issue, idx) => (
              <li key={idx}>
                {issue.message}
                {issue.action_url && (
                  <Link
                    href={issue.action_url}
                    className="text-blue-600 hover:text-blue-800 underline ml-1"
                  >
                    {t('goToSettings')}
                  </Link>
                )}
              </li>
            ))}
          </ul>
          <div className="mt-3 flex gap-2">
            <Link
              href="/settings?tab=llm"
              className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors"
            >
              {t('configureApiKey')}
            </Link>
            <button
              onClick={onDismiss}
              className="px-4 py-2 bg-gray-200 text-gray-700 text-sm font-medium rounded-lg hover:bg-gray-300 transition-colors"
            >
              {t('later')}
            </button>
          </div>
        </div>
      )}

      {health.overall_status === 'healthy' && (
        <div className="text-sm text-green-700">
          <p>{t('allSystemsNormal')}</p>
        </div>
      )}
    </div>
  );
}
