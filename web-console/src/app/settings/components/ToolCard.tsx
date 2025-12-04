'use client';

import React, { useState, useEffect, useRef } from 'react';
import { t } from '../../../lib/i18n';
import { Card } from './Card';
import { StatusPill } from './StatusPill';
import type { ToolStatus } from '../types';
import { settingsApi } from '../utils/settingsApi';

interface ToolCardProps {
  toolType: string;
  name: string;
  description: string;
  icon: string;
  status: ToolStatus;
  onConfigure: () => void;
  onTest?: () => void;
  testing?: boolean;
}

interface PlaybookInfo {
  playbook_code: string;
  name: string;
}

export function ToolCard({
  toolType,
  name,
  description,
  icon,
  status,
  onConfigure,
  onTest,
  testing = false,
}: ToolCardProps) {
  const [playbookCount, setPlaybookCount] = useState<number | null>(null);
  const [loadingCount, setLoadingCount] = useState(false);
  const hasLoadedRef = useRef(false);

  useEffect(() => {
    if (status.status === 'connected' && !hasLoadedRef.current) {
      setLoadingCount(true);
      settingsApi
        .get<PlaybookInfo[]>(`/api/v1/playbooks?uses_tool=${toolType}&scope=all`, { silent: true })
        .then((data) => {
          const count = Array.isArray(data) ? data.length : 0;
          console.log(`[ToolCard] Loaded playbook count for ${toolType}:`, count, data);
          setPlaybookCount(count);
          hasLoadedRef.current = true;
        })
        .catch((err) => {
          console.error(`[ToolCard] Failed to load playbook count for tool ${toolType}:`, err);
          setPlaybookCount(0);
          hasLoadedRef.current = true;
        })
        .finally(() => {
          setLoadingCount(false);
        });
    } else if (status.status !== 'connected') {
      hasLoadedRef.current = false;
      setPlaybookCount(null);
      setLoadingCount(false);
    }
  }, [toolType, status.status]);

  const formatPlaybookCount = (count: number) => {
    const template = t('playbooksUsingThisTool');
    if (template.includes('{count}')) {
      const plural = count !== 1 ? 's' : '';
      const verb = count !== 1 ? 'use' : 'uses';
      return template
        .replace('{count}', count.toString())
        .replace('{plural}', plural)
        .replace('{verb}', verb);
    }
    return template.replace('{count}', count.toString());
  };

  return (
    <Card hover className="flex flex-col h-full">
      <div className="flex items-start mb-4 flex-shrink-0">
        <div className="flex items-start space-x-3 flex-1 min-w-0">
          <span className="text-2xl flex-shrink-0">{icon}</span>
          <div className="flex-1 min-w-0">
            <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-1.5 leading-tight">{name}</h3>
            <p className="text-sm text-gray-500 dark:text-gray-400 leading-relaxed">{description}</p>
            {status.status === 'connected' && (
              <>
                {loadingCount ? (
                  <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">{t('loading')}</p>
                ) : playbookCount !== null && playbookCount > 0 ? (
                  <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">{formatPlaybookCount(playbookCount)}</p>
                ) : null}
              </>
            )}
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between mt-auto pt-4 border-t border-gray-200 dark:border-gray-700 flex-shrink-0">
        <StatusPill
          status={status.status}
          label={status.label}
          icon={status.icon}
        />
        <div className="flex space-x-2">
          {status.status === 'connected' && onTest && (
            <button
              onClick={onTest}
              disabled={testing}
              className="text-sm px-3 py-1 text-gray-600 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 disabled:opacity-50 whitespace-nowrap"
            >
              {testing ? t('testing') : t('testConnection')}
            </button>
          )}
          <button
            onClick={onConfigure}
            className="text-sm px-3 py-1 bg-gray-600 dark:bg-gray-700 text-white rounded hover:bg-gray-700 dark:hover:bg-gray-600 whitespace-nowrap"
          >
            {status.status === 'not_configured' ? t('configure') : t('manage')}
          </button>
        </div>
      </div>
    </Card>
  );
}
