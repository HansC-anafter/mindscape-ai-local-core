'use client';

import React from 'react';
import { DecisionCardData } from '../DecisionCard';

interface PolicyViolationCardProps {
  card: DecisionCardData;
  currentUserId?: string;
  onAction?: (cardId: string, actionType: string) => void;
}

/**
 * Policy violation governance decision card
 * Displays policy violation details and permission request options
 */
export function PolicyViolationCard({
  card,
  currentUserId,
  onAction,
}: PolicyViolationCardProps) {
  const policyData = card.expandable?.governance_data?.policy_violation;

  if (!policyData) {
    return null;
  }

  const {
    violation_type,
    policy_id,
    violation_items,
    request_permission_url,
  } = policyData;

  const violationLabels: Record<string, string> = {
    role: 'Insufficient role permissions',
    data_domain: 'Data domain access not allowed',
    pii: 'PII handling not permitted',
  };

  return (
    <div className="border rounded-lg p-4 bg-purple-50 dark:bg-purple-900/20 border-purple-200 dark:border-purple-800">
      <div className="flex items-start justify-between mb-3">
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-1">
            {card.title}
          </h3>
          <p className="text-xs text-gray-600 dark:text-gray-400">
            {card.description}
          </p>
        </div>
        <span className="text-xs px-2 py-1 rounded bg-purple-100 dark:bg-purple-900/30 text-purple-800 dark:text-purple-300">
          Policy Violation
        </span>
      </div>

      <div className="space-y-3 mb-4">
        <div className="bg-white dark:bg-gray-800 rounded p-3">
          <div className="text-xs font-medium text-gray-900 dark:text-gray-100 mb-2">
            Violation Type
          </div>
          <div className="text-xs text-gray-700 dark:text-gray-300">
            {violationLabels[violation_type] || violation_type}
          </div>
          {policy_id && (
            <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              Policy ID: {policy_id}
            </div>
          )}
        </div>

        {violation_items && violation_items.length > 0 && (
          <div className="bg-white dark:bg-gray-800 rounded p-3">
            <div className="text-xs font-medium text-gray-900 dark:text-gray-100 mb-2">
              Violation Items
            </div>
            <ul className="list-disc list-inside space-y-1">
              {violation_items.map((item, index) => (
                <li key={index} className="text-xs text-gray-700 dark:text-gray-300">
                  {item}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <div className="flex gap-2">
        {request_permission_url ? (
          <a
            href={request_permission_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex-1 px-3 py-2 text-xs font-medium bg-purple-600 dark:bg-purple-700 text-white rounded hover:bg-purple-700 dark:hover:bg-purple-600 transition-colors text-center"
          >
            Request Permission
          </a>
        ) : (
          <button
            onClick={() => onAction?.(card.id, 'request_permission')}
            className="flex-1 px-3 py-2 text-xs font-medium bg-purple-600 dark:bg-purple-700 text-white rounded hover:bg-purple-700 dark:hover:bg-purple-600 transition-colors"
          >
            Request Permission
          </button>
        )}
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

