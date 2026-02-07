'use client';

import React from 'react';
import { CheckCircle, XCircle, AlertCircle } from 'lucide-react';
import { t } from '@/lib/i18n';

interface GovernanceLayerStatus {
  layer: 'cost' | 'node' | 'policy' | 'preflight';
  status: 'passed' | 'failed' | 'warning' | 'pending';
  message?: string;
}

interface GovernanceStatusIndicatorProps {
  layers: GovernanceLayerStatus[];
  onViewDetails?: () => void;
  compact?: boolean;
}

/**
 * Governance status indicator component
 * Displays the status of each governance layer check
 */
export function GovernanceStatusIndicator({
  layers,
  onViewDetails,
  compact = false,
}: GovernanceStatusIndicatorProps) {
  const layerLabels = {
    cost: t('costGovernance' as any) || 'Cost',
    node: t('nodeGovernance' as any) || 'Node',
    policy: t('policyService' as any) || 'Policy',
    preflight: t('preflight' as any) || 'Preflight',
  };

  const layerColors = {
    cost: 'text-red-600 dark:text-red-400',
    node: 'text-orange-600 dark:text-orange-400',
    policy: 'text-purple-600 dark:text-purple-400',
    preflight: 'text-yellow-600 dark:text-yellow-400',
  };

  const getStatusIcon = (status: GovernanceLayerStatus['status']) => {
    switch (status) {
      case 'passed':
        return <CheckCircle className="w-4 h-4 text-green-600 dark:text-green-400" />;
      case 'failed':
        return <XCircle className="w-4 h-4 text-red-600 dark:text-red-400" />;
      case 'warning':
        return <AlertCircle className="w-4 h-4 text-yellow-600 dark:text-yellow-400" />;
      case 'pending':
        return <div className="w-4 h-4 border-2 border-gray-300 dark:border-gray-600 rounded-full animate-pulse" />;
      default:
        return null;
    }
  };

  const getStatusLabel = (status: GovernanceLayerStatus['status']) => {
    switch (status) {
      case 'passed':
        return t('passed' as any) || 'Passed';
      case 'failed':
        return t('failed' as any) || 'Failed';
      case 'warning':
        return t('warning' as any) || 'Warning';
      case 'pending':
        return t('pending' as any) || 'Pending';
      default:
        return '';
    }
  };

  if (compact) {
    const failedCount = layers.filter((l) => l.status === 'failed').length;
    const warningCount = layers.filter((l) => l.status === 'warning').length;
    const allPassed = layers.every((l) => l.status === 'passed');

    if (allPassed && layers.length > 0) {
      return (
        <div className="flex items-center gap-2 text-xs">
          <CheckCircle className="w-4 h-4 text-green-600 dark:text-green-400" />
          <span className="text-gray-600 dark:text-gray-400">
            {t('allGovernanceChecksPassed' as any) || 'All governance checks passed'}
          </span>
        </div>
      );
    }

    if (failedCount > 0 || warningCount > 0) {
      return (
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1">
            {failedCount > 0 && (
              <span className="text-xs font-medium text-red-600 dark:text-red-400">
                {failedCount} {t('failed' as any) || 'failed'}
              </span>
            )}
            {warningCount > 0 && (
              <span className="text-xs font-medium text-yellow-600 dark:text-yellow-400">
                {warningCount} {t('warnings' as any) || 'warnings'}
              </span>
            )}
          </div>
          {onViewDetails && (
            <button
              onClick={onViewDetails}
              className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
            >
              {t('viewDetails' as any) || 'View details'}
            </button>
          )}
        </div>
      );
    }

    return null;
  }

  return (
    <div className="space-y-2">
      <div className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2">
        {t('governanceStatus' as any) || 'Governance Status'}
      </div>
      <div className="space-y-2">
        {layers.map((layer) => (
          <div
            key={layer.layer}
            className="flex items-center justify-between p-2 bg-gray-50 dark:bg-gray-800 rounded border border-gray-200 dark:border-gray-700"
          >
            <div className="flex items-center gap-2 flex-1">
              {getStatusIcon(layer.status)}
              <span className={`text-xs font-medium ${layerColors[layer.layer]}`}>
                {layerLabels[layer.layer]}
              </span>
              {layer.message && (
                <span className="text-xs text-gray-600 dark:text-gray-400 truncate">
                  {layer.message}
                </span>
              )}
            </div>
            <span className="text-xs text-gray-500 dark:text-gray-400">
              {getStatusLabel(layer.status)}
            </span>
          </div>
        ))}
      </div>
      {onViewDetails && (
        <button
          onClick={onViewDetails}
          className="w-full mt-2 px-3 py-1.5 text-xs font-medium bg-blue-600 dark:bg-blue-700 text-white rounded hover:bg-blue-700 dark:hover:bg-blue-600 transition-colors"
        >
          {t('viewAllDetails' as any) || 'View All Details'}
        </button>
      )}
    </div>
  );
}

