'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { t } from '@/lib/i18n';

interface SystemStatusNotificationProps {
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
}

export default function SystemStatusNotificationCard({
  systemStatus
}: SystemStatusNotificationProps) {
  const [dismissed, setDismissed] = useState(false);

  // 获取未连接的工具
  const disconnectedTools = Object.entries(systemStatus.tools || {})
    .filter(([_, status]) => !status.connected)
    .map(([tool, _]) => tool);

  // 如果没有未连接的工具，且核心系统正常，显示正常状态
  const isAllNormal = disconnectedTools.length === 0 &&
                      systemStatus.llm_configured &&
                      systemStatus.vector_db_connected;

  if (dismissed || isAllNormal) {
    return null;
  }

  return (
    <div className="bg-white border rounded p-2 shadow-sm relative">
      <button
        onClick={() => setDismissed(true)}
        className="absolute top-2 right-2 text-gray-400 hover:text-gray-600 text-xs"
        aria-label="关闭"
      >
        ✕
      </button>

      <div className="flex items-center gap-2 mb-2">
        <div className="w-2 h-2 rounded-full bg-green-500"></div>
        <h3 className="font-semibold text-xs text-gray-900">{t('systemStatusNormal' as any)}</h3>
      </div>

      {disconnectedTools.length > 0 && (
        <>
          <div className="text-[10px] text-gray-600 mb-2">
            {t('workspaceMissingSettings' as any)}
          </div>
          <ul className="space-y-1 mb-3">
            {disconnectedTools.map((tool) => (
              <li key={tool} className="text-xs text-gray-700">
                • {tool.charAt(0).toUpperCase() + tool.slice(1)} {t('notConnected' as any)}{' '}
                <Link
                  href="/settings"
                  className="text-blue-600 hover:text-blue-800 underline text-[10px]"
                >
                  {t('goToSettingsConfigure' as any)}
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}

      <div className="flex gap-2">
        <Link
          href="/settings?tab=llm"
          className="flex-1 px-2 py-1.5 bg-blue-600 text-white text-xs font-medium rounded text-center hover:bg-blue-700 transition-colors"
        >
          {t('goToSetAPIKey' as any)}
        </Link>
        <button
          onClick={() => setDismissed(true)}
          className="flex-1 px-2 py-1.5 bg-gray-200 text-gray-700 text-xs font-medium rounded hover:bg-gray-300 transition-colors"
        >
          {t('later' as any)}
        </button>
      </div>

      {systemStatus.llm_configured && systemStatus.vector_db_connected && (
        <div className="mt-2 pt-2 border-t flex items-center gap-1.5">
          <svg className="w-3 h-3 text-green-500" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
          </svg>
          <span className="text-[10px] text-green-600">{t('allSystemStatusNormal' as any)}</span>
        </div>
      )}
    </div>
  );
}
