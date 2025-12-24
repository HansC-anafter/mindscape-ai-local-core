'use client';

import React from 'react';
import { AlertTriangle } from 'lucide-react';

interface CostWarningBannerProps {
  currentUsage: number;
  quota: number;
  estimatedCost?: number;
  period?: 'day' | 'month';
  onViewDetails?: () => void;
}

/**
 * Cost warning banner component
 * Displays cost warnings when usage approaches quota
 */
export function CostWarningBanner({
  currentUsage,
  quota,
  estimatedCost,
  period = 'day',
  onViewDetails,
}: CostWarningBannerProps) {
  const usagePercentage = (currentUsage / quota) * 100;
  const totalWithEstimate = estimatedCost ? currentUsage + estimatedCost : currentUsage;
  const exceedsQuota = totalWithEstimate > quota;
  const warningThreshold = 80;
  const criticalThreshold = 95;

  if (usagePercentage < warningThreshold && !exceedsQuota) {
    return null;
  }

  const severity = exceedsQuota || usagePercentage >= criticalThreshold ? 'critical' : 'warning';
  const bgColor = severity === 'critical'
    ? 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800'
    : 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800';
  const textColor = severity === 'critical'
    ? 'text-red-800 dark:text-red-300'
    : 'text-yellow-800 dark:text-yellow-300';
  const iconColor = severity === 'critical'
    ? 'text-red-600 dark:text-red-400'
    : 'text-yellow-600 dark:text-yellow-400';

  const periodLabel = period === 'day' ? 'today' : 'this month';
  const message = exceedsQuota
    ? `Cost limit exceeded! Current usage: $${currentUsage.toFixed(2)} / $${quota.toFixed(2)} ${periodLabel}`
    : estimatedCost
    ? `Warning: Estimated cost ($${estimatedCost.toFixed(2)}) will exceed quota. Current usage: $${currentUsage.toFixed(2)} / $${quota.toFixed(2)} ${periodLabel}`
    : `Warning: ${usagePercentage.toFixed(1)}% of ${periodLabel}'s quota used ($${currentUsage.toFixed(2)} / $${quota.toFixed(2)})`;

  return (
    <div className={`${bgColor} border rounded-lg p-3 mb-3 flex items-start gap-3`}>
      <AlertTriangle className={`${iconColor} flex-shrink-0 mt-0.5`} size={20} />
      <div className="flex-1 min-w-0">
        <div className={`text-sm font-medium ${textColor} mb-1`}>
          {message}
        </div>
        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2 mt-2">
          <div
            className={`h-2 rounded-full ${
              exceedsQuota ? 'bg-red-500' : 'bg-yellow-500'
            }`}
            style={{ width: `${Math.min(usagePercentage, 100)}%` }}
          />
        </div>
        {onViewDetails && (
          <button
            onClick={onViewDetails}
            className={`text-xs font-medium ${textColor} underline mt-2 hover:opacity-80`}
          >
            View details
          </button>
        )}
      </div>
    </div>
  );
}

