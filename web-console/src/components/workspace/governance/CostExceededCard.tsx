'use client';

import React from 'react';
import { DecisionCardData } from '../DecisionCard';

interface CostExceededCardProps {
  card: DecisionCardData;
  currentUserId?: string;
  onAction?: (cardId: string, actionType: string) => void;
}

/**
 * Cost exceeded governance decision card
 * Displays cost limit information and downgrade suggestions
 */
export function CostExceededCard({
  card,
  currentUserId,
  onAction,
}: CostExceededCardProps) {
  const costData = card.expandable?.governance_data?.cost_governance;

  if (!costData) {
    return null;
  }

  const {
    estimated_cost,
    quota_limit,
    current_usage,
    downgrade_suggestion,
  } = costData;

  const usagePercentage = (current_usage / quota_limit) * 100;
  const estimatedTotal = current_usage + estimated_cost;
  const exceedsQuota = estimatedTotal > quota_limit;

  const handleDowngrade = () => {
    if (downgrade_suggestion && onAction) {
      onAction(card.id, 'downgrade');
    }
  };

  const handleConfirm = () => {
    if (onAction) {
      onAction(card.id, 'confirm');
    }
  };

  return (
    <div className="border rounded-lg p-4 bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800">
      <div className="flex items-start justify-between mb-3">
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-1">
            {card.title}
          </h3>
          <p className="text-xs text-gray-600 dark:text-gray-400">
            {card.description}
          </p>
        </div>
        <span className="text-xs px-2 py-1 rounded bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300">
          Cost Limit
        </span>
      </div>

      <div className="space-y-3 mb-4">
        <div className="bg-white dark:bg-gray-800 rounded p-3">
          <div className="flex justify-between items-center mb-2">
            <span className="text-xs text-gray-600 dark:text-gray-400">Current Usage</span>
            <span className="text-xs font-medium text-gray-900 dark:text-gray-100">
              ${current_usage.toFixed(2)}
            </span>
          </div>
          <div className="flex justify-between items-center mb-2">
            <span className="text-xs text-gray-600 dark:text-gray-400">Estimated Cost</span>
            <span className="text-xs font-medium text-red-600 dark:text-red-400">
              +${estimated_cost.toFixed(2)}
            </span>
          </div>
          <div className="flex justify-between items-center mb-2">
            <span className="text-xs text-gray-600 dark:text-gray-400">Daily Quota</span>
            <span className="text-xs font-medium text-gray-900 dark:text-gray-100">
              ${quota_limit.toFixed(2)}
            </span>
          </div>
          <div className="mt-2">
            <div className="flex justify-between text-xs mb-1">
              <span className="text-gray-600 dark:text-gray-400">Usage</span>
              <span className={`font-medium ${exceedsQuota ? 'text-red-600 dark:text-red-400' : 'text-gray-900 dark:text-gray-100'}`}>
                {usagePercentage.toFixed(1)}%
              </span>
            </div>
            <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
              <div
                className={`h-2 rounded-full ${exceedsQuota ? 'bg-red-500' : 'bg-blue-500'}`}
                style={{ width: `${Math.min(usagePercentage, 100)}%` }}
              />
            </div>
          </div>
        </div>

        {downgrade_suggestion && (
          <div className="bg-blue-50 dark:bg-blue-900/20 rounded p-3 border border-blue-200 dark:border-blue-800">
            <div className="text-xs font-medium text-blue-900 dark:text-blue-100 mb-1">
              Suggestion
            </div>
            <div className="text-xs text-blue-700 dark:text-blue-300 mb-2">
              Use {downgrade_suggestion.profile} profile to reduce cost to ${downgrade_suggestion.estimated_cost.toFixed(2)}
            </div>
            <button
              onClick={handleDowngrade}
              className="w-full px-3 py-1.5 text-xs font-medium bg-blue-600 dark:bg-blue-700 text-white rounded hover:bg-blue-700 dark:hover:bg-blue-600 transition-colors"
            >
              Use {downgrade_suggestion.profile} Profile
            </button>
          </div>
        )}
      </div>

      <div className="flex gap-2">
        <button
          onClick={handleConfirm}
          className="flex-1 px-3 py-2 text-xs font-medium bg-red-600 dark:bg-red-700 text-white rounded hover:bg-red-700 dark:hover:bg-red-600 transition-colors"
        >
          Proceed Anyway
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

