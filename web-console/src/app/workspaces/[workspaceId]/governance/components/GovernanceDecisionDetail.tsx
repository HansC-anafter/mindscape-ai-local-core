'use client';

import React from 'react';
import { X } from 'lucide-react';
import { t } from '@/lib/i18n';

interface GovernanceDecision {
  decision_id: string;
  timestamp: string;
  layer: 'cost' | 'node' | 'policy' | 'preflight';
  approved: boolean;
  reason?: string;
  playbook_code?: string;
  metadata?: {
    estimated_cost?: number;
    quota_limit?: number;
    rejection_reason?: string;
    violation_type?: string;
    missing_inputs?: string[];
  };
}

interface GovernanceDecisionDetailProps {
  decision: GovernanceDecision;
  onClose: () => void;
}

export function GovernanceDecisionDetail({
  decision,
  onClose,
}: GovernanceDecisionDetailProps) {
  const layerLabels = {
    cost: t('costGovernance' as any) || 'Cost Governance',
    node: t('nodeGovernance' as any) || 'Node Governance',
    policy: t('policyService' as any) || 'Policy Service',
    preflight: t('preflight' as any) || 'Preflight',
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-gray-800 rounded-lg max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <div className="sticky top-0 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 p-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            {t('decisionDetails' as any) || 'Decision Details'}
          </h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
          >
            <X size={20} />
          </button>
        </div>

        <div className="p-6 space-y-4">
          <div>
            <div className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
              {t('decisionId' as any) || 'Decision ID'}
            </div>
            <div className="text-sm text-gray-900 dark:text-gray-100 font-mono">
              {decision.decision_id}
            </div>
          </div>

          <div>
            <div className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
              {t('timestamp' as any) || 'Timestamp'}
            </div>
            <div className="text-sm text-gray-900 dark:text-gray-100">
              {new Date(decision.timestamp).toLocaleString()}
            </div>
          </div>

          <div>
            <div className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
              {t('layer' as any) || 'Layer'}
            </div>
            <div className="text-sm text-gray-900 dark:text-gray-100">
              {layerLabels[decision.layer]}
            </div>
          </div>

          <div>
            <div className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
              {t('status' as any) || 'Status'}
            </div>
            <div
              className={`inline-block px-2 py-1 text-xs font-medium rounded ${
                decision.approved
                  ? 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300'
                  : 'bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300'
              }`}
            >
              {decision.approved ? t('approved' as any) || 'Approved' : t('rejected' as any) || 'Rejected'}
            </div>
          </div>

          {decision.reason && (
            <div>
              <div className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
                {t('reason' as any) || 'Reason'}
              </div>
              <div className="text-sm text-gray-900 dark:text-gray-100">{decision.reason}</div>
            </div>
          )}

          {decision.playbook_code && (
            <div>
              <div className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
                {t('playbookCode' as any) || 'Playbook Code'}
              </div>
              <div className="text-sm text-gray-900 dark:text-gray-100 font-mono">
                {decision.playbook_code}
              </div>
            </div>
          )}

          {decision.metadata && Object.keys(decision.metadata).length > 0 && (
            <div>
              <div className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">
                {t('metadata' as any) || 'Metadata'}
              </div>
              <div className="bg-gray-50 dark:bg-gray-900 rounded p-3 space-y-2">
                {decision.metadata.estimated_cost !== undefined && (
                  <div className="flex justify-between">
                    <span className="text-xs text-gray-600 dark:text-gray-400">
                      {t('estimatedCost' as any) || 'Estimated Cost'}
                    </span>
                    <span className="text-xs text-gray-900 dark:text-gray-100">
                      ${decision.metadata.estimated_cost.toFixed(2)}
                    </span>
                  </div>
                )}
                {decision.metadata.quota_limit !== undefined && (
                  <div className="flex justify-between">
                    <span className="text-xs text-gray-600 dark:text-gray-400">
                      {t('quotaLimit' as any) || 'Quota Limit'}
                    </span>
                    <span className="text-xs text-gray-900 dark:text-gray-100">
                      ${decision.metadata.quota_limit.toFixed(2)}
                    </span>
                  </div>
                )}
                {decision.metadata.rejection_reason && (
                  <div>
                    <span className="text-xs text-gray-600 dark:text-gray-400">
                      {t('rejectionReason' as any) || 'Rejection Reason'}
                    </span>
                    <span className="text-xs text-gray-900 dark:text-gray-100 ml-2">
                      {decision.metadata.rejection_reason}
                    </span>
                  </div>
                )}
                {decision.metadata.violation_type && (
                  <div>
                    <span className="text-xs text-gray-600 dark:text-gray-400">
                      {t('violationType' as any) || 'Violation Type'}
                    </span>
                    <span className="text-xs text-gray-900 dark:text-gray-100 ml-2">
                      {decision.metadata.violation_type}
                    </span>
                  </div>
                )}
                {decision.metadata.missing_inputs && decision.metadata.missing_inputs.length > 0 && (
                  <div>
                    <span className="text-xs text-gray-600 dark:text-gray-400">
                      {t('missingInputs' as any) || 'Missing Inputs'}
                    </span>
                    <div className="mt-1">
                      {decision.metadata.missing_inputs.map((input, index) => (
                        <span
                          key={index}
                          className="inline-block px-2 py-1 text-xs bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300 rounded mr-1 mb-1"
                        >
                          {input}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="sticky bottom-0 bg-gray-50 dark:bg-gray-900 border-t border-gray-200 dark:border-gray-700 p-4 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
          >
            {t('close' as any) || 'Close'}
          </button>
        </div>
      </div>
    </div>
  );
}

