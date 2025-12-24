'use client';

import React from 'react';
import { t } from '../../../../lib/i18n';

interface ThrottleConfigProps {
  throttle: {
    write_operation_limit: number;
    queue_strategy: 'reject' | 'queue';
  };
  onChange: (throttle: { write_operation_limit: number; queue_strategy: 'reject' | 'queue' }) => void;
}

export function ThrottleConfig({ throttle, onChange }: ThrottleConfigProps) {
  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
      <div className="mb-3">
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-1">
          {t('throttleConfiguration')}
        </h4>
        <p className="text-xs text-gray-600 dark:text-gray-400">
          {t('throttleConfigurationDescription')}
        </p>
      </div>

      <div className="space-y-4">
        <div>
          <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
            {t('writeOperationLimit')}
          </label>
          <input
            type="number"
            min="1"
            value={throttle.write_operation_limit}
            onChange={(e) =>
              onChange({
                ...throttle,
                write_operation_limit: parseInt(e.target.value, 10) || 1,
              })
            }
            className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
          />
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            {t('writeOperationLimitDescription')}
          </p>
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
            {t('queueStrategy')}
          </label>
          <select
            value={throttle.queue_strategy}
            onChange={(e) =>
              onChange({
                ...throttle,
                queue_strategy: e.target.value as 'reject' | 'queue',
              })
            }
            className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
          >
            <option value="reject">{t('reject')}</option>
            <option value="queue">{t('queue')}</option>
          </select>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            {t('queueStrategyDescription')}
          </p>
        </div>
      </div>
    </div>
  );
}

