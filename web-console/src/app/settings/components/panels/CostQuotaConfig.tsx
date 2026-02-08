'use client';

import React from 'react';
import { t } from '../../../../lib/i18n';

interface CostQuotaConfigProps {
  settings: {
    daily_quota: number;
    single_execution_limit: number;
    risk_level_quotas: {
      read: number;
      write: number;
      publish: number;
    };
    model_price_overrides: Record<string, number>;
  };
  onChange: (settings: {
    daily_quota: number;
    single_execution_limit: number;
    risk_level_quotas: {
      read: number;
      write: number;
      publish: number;
    };
    model_price_overrides: Record<string, number>;
  }) => void;
}

export function CostQuotaConfig({ settings, onChange }: CostQuotaConfigProps) {
  return (
    <div className="space-y-4">
      <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-4">
          {t('quotaSettings' as any)}
        </h4>

        <div className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('dailyQuota' as any)}
            </label>
            <input
              type="number"
              min="0"
              step="0.01"
              value={settings.daily_quota}
              onChange={(e) =>
                onChange({
                  ...settings,
                  daily_quota: parseFloat(e.target.value) || 0,
                })
              }
              className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
            />
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              {t('dailyQuotaDescription' as any)}
            </p>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('singleExecutionLimit' as any)}
            </label>
            <input
              type="number"
              min="0"
              step="0.01"
              value={settings.single_execution_limit}
              onChange={(e) =>
                onChange({
                  ...settings,
                  single_execution_limit: parseFloat(e.target.value) || 0,
                })
              }
              className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
            />
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              {t('singleExecutionLimitDescription' as any)}
            </p>
          </div>
        </div>
      </div>

      <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-4">
          {t('riskLevelQuotas' as any)}
        </h4>

        <div className="space-y-3">
          {(['read', 'write', 'publish'] as const).map((level) => (
            <div key={level}>
              <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                {t(`${level}RiskLevel` as any)}
              </label>
              <input
                type="number"
                min="0"
                step="0.01"
                value={settings.risk_level_quotas[level]}
                onChange={(e) =>
                  onChange({
                    ...settings,
                    risk_level_quotas: {
                      ...settings.risk_level_quotas,
                      [level]: parseFloat(e.target.value) || 0,
                    },
                  })
                }
                className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
              />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
