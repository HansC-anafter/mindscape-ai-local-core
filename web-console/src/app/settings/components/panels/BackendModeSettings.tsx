'use client';

import React from 'react';
import { t } from '../../../../lib/i18n';

interface BackendModeSettingsProps {
  mode: string;
  onModeChange: (mode: string) => void;
}

export function BackendModeSettings({ mode, onModeChange }: BackendModeSettingsProps) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
        {t('backendMode')}
      </label>
      <div className="space-y-2">
        <label className="flex items-center">
          <input
            type="radio"
            name="mode"
            value="local"
            checked={mode === 'local'}
            onChange={(e) => onModeChange(e.target.value)}
            className="mr-2"
          />
          <div>
            <span className="font-medium text-gray-900 dark:text-gray-100">{t('localLLM')}</span>
            <p className="text-sm text-gray-500 dark:text-gray-400">{t('localLLMDescription')}</p>
          </div>
        </label>
        <label className="flex items-center opacity-50">
          <input
            type="radio"
            name="mode"
            value="remote_crs"
            checked={mode === 'remote_crs'}
            onChange={(e) => onModeChange(e.target.value)}
            className="mr-2"
            disabled
          />
          <div>
            <span className="font-medium text-gray-900 dark:text-gray-100">{t('remoteAgentService')}</span>
            <p className="text-sm text-gray-500 dark:text-gray-400">{t('remoteAgentServiceDescription')} (Not available in local-only version)</p>
          </div>
        </label>
      </div>
    </div>
  );
}

