'use client';

import React, { useState } from 'react';
import { DecisionCardData } from '../DecisionCard';
import { InputDialog } from '../InputDialog';

interface PreflightFailedCardProps {
  card: DecisionCardData;
  currentUserId?: string;
  onAction?: (cardId: string, actionType: string, data?: Record<string, any>) => void;
}

/**
 * Preflight failed governance decision card
 * Displays missing inputs and allows user to provide them
 */
export function PreflightFailedCard({
  card,
  currentUserId,
  onAction,
}: PreflightFailedCardProps) {
  const preflightData = card.expandable?.governance_data?.preflight_failure;
  const [showInputDialog, setShowInputDialog] = useState(false);

  if (!preflightData) {
    return null;
  }

  const {
    missing_inputs,
    missing_credentials,
    environment_issues,
    recommended_alternatives,
  } = preflightData;

  const hasMissingInputs = missing_inputs && missing_inputs.length > 0;
  const hasMissingCredentials = missing_credentials && missing_credentials.length > 0;
  const hasEnvironmentIssues = environment_issues && environment_issues.length > 0;

  const handleProvideInputs = () => {
    if (hasMissingInputs) {
      setShowInputDialog(true);
    }
  };

  const handleInputSubmit = (values: Record<string, string>) => {
    setShowInputDialog(false);
    onAction?.(card.id, 'provide_inputs', values);
  };

  return (
    <>
      <div className="border rounded-lg p-4 bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800">
        <div className="flex items-start justify-between mb-3">
          <div className="flex-1">
            <h3 className="text-sm font-semibold text-primary dark:text-gray-100 mb-1">
              {card.title}
            </h3>
            <p className="text-xs text-secondary dark:text-gray-400">
              {card.description}
            </p>
          </div>
          <span className="text-xs px-2 py-1 rounded bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300">
            Preflight Check
          </span>
        </div>

        <div className="space-y-3 mb-4">
          {hasMissingInputs && (
            <div className="bg-surface-accent dark:bg-gray-800 rounded p-3">
              <div className="text-xs font-medium text-primary dark:text-gray-100 mb-2">
                Missing Required Inputs
              </div>
              <ul className="list-disc list-inside space-y-1">
                {missing_inputs.map((input, index) => (
                  <li key={index} className="text-xs text-primary dark:text-gray-300">
                    {input}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {hasMissingCredentials && (
            <div className="bg-surface-accent dark:bg-gray-800 rounded p-3">
              <div className="text-xs font-medium text-primary dark:text-gray-100 mb-2">
                Missing Credentials
              </div>
              <ul className="list-disc list-inside space-y-1">
                {missing_credentials.map((cred, index) => (
                  <li key={index} className="text-xs text-primary dark:text-gray-300">
                    {cred}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {hasEnvironmentIssues && (
            <div className="bg-surface-accent dark:bg-gray-800 rounded p-3">
              <div className="text-xs font-medium text-primary dark:text-gray-100 mb-2">
                Environment Issues
              </div>
              <ul className="list-disc list-inside space-y-1">
                {environment_issues.map((issue, index) => (
                  <li key={index} className="text-xs text-primary dark:text-gray-300">
                    {issue}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {recommended_alternatives && recommended_alternatives.length > 0 && (
            <div className="bg-blue-50 dark:bg-blue-900/20 rounded p-3 border border-blue-200 dark:border-blue-800">
              <div className="text-xs font-medium text-blue-900 dark:text-blue-100 mb-2">
                Recommended Alternatives
              </div>
              <div className="flex flex-wrap gap-1">
                {recommended_alternatives.map((alt, index) => (
                  <button
                    key={index}
                    onClick={() => onAction?.(card.id, `use_alternative:${alt}`)}
                    className="text-xs px-2 py-1 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded hover:bg-blue-200 dark:hover:bg-blue-900/50 transition-colors"
                  >
                    {alt}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="flex gap-2">
          {hasMissingInputs && (
            <button
              onClick={handleProvideInputs}
              className="flex-1 px-3 py-2 text-xs font-medium bg-yellow-600 dark:bg-yellow-700 text-white rounded hover:bg-yellow-700 dark:hover:bg-yellow-600 transition-colors"
            >
              Provide Missing Inputs
            </button>
          )}
          <button
            onClick={() => onAction?.(card.id, 'reject')}
            className="px-3 py-2 text-xs font-medium bg-surface-secondary dark:bg-gray-700 text-primary dark:text-gray-300 rounded hover:bg-surface-secondary dark:hover:bg-gray-600 transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>

      {showInputDialog && hasMissingInputs && (
        <InputDialog
          title="Provide Missing Inputs"
          fields={missing_inputs.map((input) => ({
            key: input,
            label: input,
            type: 'text',
            required: true,
            placeholder: `Enter ${input}`,
          }))}
          onSubmit={handleInputSubmit}
          onCancel={() => setShowInputDialog(false)}
        />
      )}
    </>
  );
}

