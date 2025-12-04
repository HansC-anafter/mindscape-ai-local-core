'use client';

import React from 'react';
import { t } from '../../../../lib/i18n';
import { StatusPill } from '../StatusPill';
import type { BackendInfo } from '../../types';

interface BackendStatusSectionProps {
  availableBackends: Record<string, BackendInfo>;
}

export function BackendStatusSection({ availableBackends }: BackendStatusSectionProps) {
  return (
    <div>
      <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">{t('backendStatus')}</h3>
      <div className="space-y-2 text-sm">
        {Object.entries(availableBackends).map(([key, info]) => (
          <div key={key} className="flex items-center justify-between">
            <span className="text-gray-600 dark:text-gray-400">{info.name}</span>
            <StatusPill
              status={info.available ? 'enabled' : 'disabled'}
              label={info.available ? t('available') : t('notConfigured')}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

