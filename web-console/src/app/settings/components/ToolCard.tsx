'use client';

import React, { useState, useEffect, useRef } from 'react';
import { t } from '../../../lib/i18n';
import { Card } from './Card';
import { StatusPill } from './StatusPill';
import type { ToolStatus } from '../types';
import { settingsApi } from '../utils/settingsApi';
import { listenToToolConfigUpdated } from '../../../lib/tool-status-events';

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
  const [playbooks, setPlaybooks] = useState<PlaybookInfo[]>([]);
  const [loadingPlaybooks, setLoadingPlaybooks] = useState(false);
  const hasLoadedRef = useRef(false);

  // Load playbooks that use this tool dynamically
  const loadPlaybooks = React.useCallback(() => {
    if (status.status === 'connected' && !loadingPlaybooks) {
      setLoadingPlaybooks(true);
      settingsApi
        .get<PlaybookInfo[]>(`/api/v1/playbooks?uses_tool=${toolType}&scope=all`)
        .then((data) => {
          setPlaybooks(data);
          hasLoadedRef.current = true;
        })
        .catch((err) => {
          console.error(`Failed to load playbooks for tool ${toolType}:`, err);
          setPlaybooks([]);
        })
        .finally(() => {
          setLoadingPlaybooks(false);
        });
    }
  }, [toolType, status.status, loadingPlaybooks]);

  // Load playbooks when tool becomes connected
  useEffect(() => {
    if (status.status === 'connected' && !hasLoadedRef.current) {
      loadPlaybooks();
    } else if (status.status !== 'connected') {
      // Reset when tool is disconnected
      hasLoadedRef.current = false;
      setPlaybooks([]);
    }
  }, [status.status, loadPlaybooks]);

  // Listen to tool config updates to refresh playbooks
  useEffect(() => {
    const cleanup = listenToToolConfigUpdated(() => {
      // Reset and reload if tool is connected
      if (status.status === 'connected') {
        hasLoadedRef.current = false;
        loadPlaybooks();
      }
    }, toolType);

    return cleanup;
  }, [toolType, status.status, loadPlaybooks]);

  return (
    <Card hover>
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center space-x-3">
          <span className="text-2xl">{icon}</span>
          <div>
            <h3 className="font-semibold text-gray-900">{name}</h3>
            <p className="text-sm text-gray-500 mt-1">{description}</p>
          </div>
        </div>
      </div>

      {status.status === 'connected' && (
        <div className="mt-3 pt-3 border-t border-gray-200">
          <p className="text-xs text-gray-500 mb-2">{t('whichPlaybooksUseThisTool')}</p>
          {loadingPlaybooks ? (
            <div className="text-xs text-gray-400 italic">載入中...</div>
          ) : playbooks.length > 0 ? (
            <div className="flex flex-wrap gap-1">
              {playbooks.map((playbook) => (
                <span
                  key={playbook.playbook_code}
                  className="text-xs px-2 py-1 bg-blue-100 text-blue-700 rounded"
                  title={playbook.name}
                >
                  {playbook.playbook_code}
                </span>
              ))}
            </div>
          ) : (
            <div className="text-xs text-gray-400 italic">目前沒有使用此工具的 Playbook</div>
          )}
        </div>
      )}

      <div className="flex items-center justify-between mt-4 pt-4 border-t border-gray-200">
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
              className="text-sm px-3 py-1 text-purple-600 hover:text-purple-700 disabled:opacity-50"
            >
              {testing ? t('testing') : t('testConnection')}
            </button>
          )}
          <button
            onClick={onConfigure}
            className="text-sm px-3 py-1 bg-purple-600 text-white rounded hover:bg-purple-700"
          >
            {status.status === 'not_configured' ? t('configure') : t('manage')}
          </button>
        </div>
      </div>
    </Card>
  );
}
