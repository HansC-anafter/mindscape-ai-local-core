'use client';

import { useT } from '../../../../../lib/i18n';
import type { QuotaUsageSectionProps } from './types';

export function QuotaUsageSection({ quotaInfo }: QuotaUsageSectionProps) {
  const t = useT();
  if (!quotaInfo) {
    return null;
  }

  return (
    <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
      <div className="flex justify-between items-center mb-2">
        <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
          {t('quotaUsage' as any)}
        </span>
        <span className="text-sm text-gray-500 dark:text-gray-400">
          {quotaInfo.used} / {quotaInfo.limit}
        </span>
      </div>
      <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
        <div
          className="bg-gray-600 h-2 rounded-full"
          style={{ width: `${(quotaInfo.used / quotaInfo.limit) * 100}%` }}
        />
      </div>
      {quotaInfo.reset_date && (
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
          {t('resetDate' as any) || 'Reset Date'}: {quotaInfo.reset_date}
        </p>
      )}
    </div>
  );
}
