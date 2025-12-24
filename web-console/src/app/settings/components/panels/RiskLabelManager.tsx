'use client';

import React, { useState } from 'react';
import { t } from '../../../../lib/i18n';

interface RiskLabelManagerProps {
  riskLabels: Record<string, string[]>;
  onChange: (riskLabels: Record<string, string[]>) => void;
}

const RISK_LABEL_OPTIONS = [
  'requires_repo_access',
  'requires_api_key',
  'requires_network_access',
  'modifies_filesystem',
  'high_cost',
  'sensitive_data',
];

export function RiskLabelManager({
  riskLabels,
  onChange,
}: RiskLabelManagerProps) {
  const [selectedPlaybook, setSelectedPlaybook] = useState('');
  const [newPlaybook, setNewPlaybook] = useState('');

  const handleAddPlaybook = () => {
    if (newPlaybook.trim() && !riskLabels[newPlaybook.trim()]) {
      onChange({
        ...riskLabels,
        [newPlaybook.trim()]: [],
      });
      setNewPlaybook('');
    }
  };

  const handleToggleLabel = (playbook: string, label: string) => {
    const currentLabels = riskLabels[playbook] || [];
    const newLabels = currentLabels.includes(label)
      ? currentLabels.filter((l) => l !== label)
      : [...currentLabels, label];
    onChange({
      ...riskLabels,
      [playbook]: newLabels,
    });
  };

  const handleRemovePlaybook = (playbook: string) => {
    const newLabels = { ...riskLabels };
    delete newLabels[playbook];
    onChange(newLabels);
  };

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
      <div className="mb-3">
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-1">
          {t('riskLabels')}
        </h4>
        <p className="text-xs text-gray-600 dark:text-gray-400">
          {t('riskLabelsDescription')}
        </p>
      </div>

      <div className="flex gap-2 mb-4">
        <input
          type="text"
          value={newPlaybook}
          onChange={(e) => setNewPlaybook(e.target.value)}
          onKeyPress={(e) => e.key === 'Enter' && handleAddPlaybook()}
          placeholder={t('enterPlaybookCode')}
          className="flex-1 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
        />
        <button
          type="button"
          onClick={handleAddPlaybook}
          className="px-3 py-2 text-sm bg-accent dark:bg-blue-700 text-white rounded hover:bg-accent/90 dark:hover:bg-blue-600 transition-colors"
        >
          {t('add')}
        </button>
      </div>

      {Object.keys(riskLabels).length > 0 ? (
        <div className="space-y-3">
          {Object.entries(riskLabels).map(([playbook, labels]) => (
            <div
              key={playbook}
              className="border border-gray-200 dark:border-gray-700 rounded p-3"
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  {playbook}
                </span>
                <button
                  type="button"
                  onClick={() => handleRemovePlaybook(playbook)}
                  className="text-xs text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300"
                >
                  {t('remove')}
                </button>
              </div>
              <div className="flex flex-wrap gap-2">
                {RISK_LABEL_OPTIONS.map((label) => (
                  <label
                    key={label}
                    className="flex items-center gap-1 px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded text-xs cursor-pointer hover:bg-gray-200 dark:hover:bg-gray-600"
                  >
                    <input
                      type="checkbox"
                      checked={labels.includes(label)}
                      onChange={() => handleToggleLabel(playbook, label)}
                      className="rounded"
                    />
                    <span className="text-gray-700 dark:text-gray-300">{label}</span>
                  </label>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-xs text-gray-500 dark:text-gray-400 italic">
          {t('noRiskLabelsConfigured')}
        </p>
      )}
    </div>
  );
}

