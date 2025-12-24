'use client';

import React from 'react';
import { DecisionCardData } from '../DecisionCard';

interface NodeGovernanceRejectedCardProps {
  card: DecisionCardData;
  currentUserId?: string;
  onAction?: (cardId: string, actionType: string) => void;
}

/**
 * Node governance rejected decision card
 * Displays rejection reason and affected playbooks
 */
export function NodeGovernanceRejectedCard({
  card,
  currentUserId,
  onAction,
}: NodeGovernanceRejectedCardProps) {
  const nodeData = card.expandable?.governance_data?.node_governance;

  if (!nodeData) {
    return null;
  }

  const {
    rejection_reason,
    affected_playbooks,
    alternatives,
  } = nodeData;

  const reasonLabels: Record<string, string> = {
    blacklist: 'Playbook is blacklisted',
    risk_label: 'Playbook requires additional permissions',
    throttle: 'Rate limit exceeded',
  };

  return (
    <div className="border rounded-lg p-4 bg-orange-50 dark:bg-orange-900/20 border-orange-200 dark:border-orange-800">
      <div className="flex items-start justify-between mb-3">
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-1">
            {card.title}
          </h3>
          <p className="text-xs text-gray-600 dark:text-gray-400">
            {card.description}
          </p>
        </div>
        <span className="text-xs px-2 py-1 rounded bg-orange-100 dark:bg-orange-900/30 text-orange-800 dark:text-orange-300">
          Node Governance
        </span>
      </div>

      <div className="space-y-3 mb-4">
        <div className="bg-white dark:bg-gray-800 rounded p-3">
          <div className="text-xs font-medium text-gray-900 dark:text-gray-100 mb-2">
            Rejection Reason
          </div>
          <div className="text-xs text-gray-700 dark:text-gray-300">
            {reasonLabels[rejection_reason] || rejection_reason}
          </div>
        </div>

        {affected_playbooks && affected_playbooks.length > 0 && (
          <div className="bg-white dark:bg-gray-800 rounded p-3">
            <div className="text-xs font-medium text-gray-900 dark:text-gray-100 mb-2">
              Affected Playbooks
            </div>
            <div className="flex flex-wrap gap-1">
              {affected_playbooks.map((playbook, index) => (
                <span
                  key={index}
                  className="text-xs px-2 py-1 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded"
                >
                  {playbook}
                </span>
              ))}
            </div>
          </div>
        )}

        {alternatives && alternatives.length > 0 && (
          <div className="bg-blue-50 dark:bg-blue-900/20 rounded p-3 border border-blue-200 dark:border-blue-800">
            <div className="text-xs font-medium text-blue-900 dark:text-blue-100 mb-2">
              Alternative Playbooks
            </div>
            <div className="flex flex-wrap gap-1">
              {alternatives.map((playbook, index) => (
                <button
                  key={index}
                  onClick={() => onAction?.(card.id, `use_alternative:${playbook}`)}
                  className="text-xs px-2 py-1 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded hover:bg-blue-200 dark:hover:bg-blue-900/50 transition-colors"
                >
                  {playbook}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="flex gap-2">
        <button
          onClick={() => onAction?.(card.id, 'review')}
          className="flex-1 px-3 py-2 text-xs font-medium bg-orange-600 dark:bg-orange-700 text-white rounded hover:bg-orange-700 dark:hover:bg-orange-600 transition-colors"
        >
          Review Settings
        </button>
        <button
          onClick={() => onAction?.(card.id, 'reject')}
          className="px-3 py-2 text-xs font-medium bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

