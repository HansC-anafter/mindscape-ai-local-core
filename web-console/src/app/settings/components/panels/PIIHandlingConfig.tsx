'use client';

import React from 'react';
import { t } from '../../../../lib/i18n';

interface PIIHandlingConfigProps {
  piiEnabled: boolean;
  onChange: (enabled: boolean) => void;
}

export function PIIHandlingConfig({ piiEnabled, onChange }: PIIHandlingConfigProps) {
  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
      <div className="mb-3">
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-1">
          {t('piiHandling' as any)}
        </h4>
        <p className="text-xs text-gray-600 dark:text-gray-400">
          {t('piiHandlingDescription' as any)}
        </p>
      </div>

      <label className="flex items-center gap-3 p-3 border border-gray-200 dark:border-gray-700 rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700/50">
        <input
          type="checkbox"
          checked={piiEnabled}
          onChange={(e) => onChange(e.target.checked)}
          className="rounded"
        />
        <div className="flex-1">
          <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
            {t('enablePIIHandling' as any)}
          </div>
          <div className="text-xs text-gray-600 dark:text-gray-400 mt-1">
            {t('enablePIIHandlingDescription' as any)}
          </div>
        </div>
      </label>
    </div>
  );
}

