'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { t } from '@/lib/i18n';

interface SystemStatusProps {
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
  workspaceId: string;
  onRefresh?: () => void;
}

export default function SystemStatusCard({
  systemStatus,
  workspaceId,
  onRefresh
}: SystemStatusProps) {
  const [showDetails, setShowDetails] = useState(true);


  return (
    <div className="bg-white border rounded p-2 shadow-sm">
      <div className="flex items-center justify-between mb-2">
        <h3 className="font-semibold text-gray-900 text-xs">{t('systemStatusAndTools' as any)}</h3>
        <div className="flex items-center gap-1.5">
          {systemStatus.has_issues && (
            <span className="text-[10px] text-red-600 font-medium">
              {systemStatus.critical_issues_count} {t('issuesCount' as any)}
            </span>
          )}
          <button
            onClick={() => setShowDetails(!showDetails)}
            className="text-[10px] text-blue-600 hover:text-blue-800 underline"
          >
            {showDetails ? t('hideDetails' as any) : t('showDetails' as any)}
          </button>
        </div>
      </div>

      <div className="space-y-1.5 text-xs">
        <div className="flex items-center justify-between">
          <span className="text-gray-600 text-xs">{t('llmConnectionStatus' as any)}</span>
          <div className="flex items-center gap-1.5">
            <svg className="w-3 h-3 text-green-500" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
            </svg>
            <span className={`text-xs ${systemStatus.llm_configured ? 'text-green-600' : 'text-red-600'}`}>
              {systemStatus.llm_configured
                ? `${systemStatus.llm_provider || t('available' as any)}`
                : t('notConfigured' as any)}
            </span>
          </div>
        </div>

        <div className="flex items-center justify-between">
          <span className="text-gray-600 text-xs">{t('vectorDB' as any)}</span>
          <div className="flex items-center gap-1.5">
            <svg className="w-3 h-3 text-green-500" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
            </svg>
            <span className={`text-xs ${systemStatus.vector_db_connected ? 'text-green-600' : 'text-yellow-600'}`}>
              {systemStatus.vector_db_connected ? t('connected' as any) : t('notConnected' as any)}
            </span>
          </div>
        </div>

        {showDetails && (
          <div className="mt-2 pt-2 border-t space-y-1.5">
            <div className="text-[10px] text-gray-500 mb-1">{t('toolConnections' as any)}</div>
            {Object.entries(systemStatus.tools).map(([tool, status]) => (
              <div key={tool} className="flex items-center justify-between text-xs">
                <span className="text-gray-600 capitalize">{tool}</span>
                <div className="flex items-center gap-1.5">
                  {status.connected ? (
                    <>
                      <svg className="w-3 h-3 text-green-500" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                      </svg>
                      <span className="text-xs text-green-600">{t('connected' as any)}</span>
                    </>
                  ) : (
                    <>
                      <svg className="w-3 h-3 text-gray-400" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                      </svg>
                      <Link
                        href="/settings"
                        className="text-xs text-blue-600 hover:text-blue-800 underline"
                      >
                        {t('goToSettings' as any)}
                      </Link>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {systemStatus.has_issues && (
        <div className="mt-2 pt-2 border-t">
          <Link
            href="/settings?tab=llm"
            className="text-[10px] text-blue-600 hover:text-blue-800 underline"
          >
            {t('goToSettings' as any)} →
          </Link>
        </div>
      )}
    </div>
  );
}
