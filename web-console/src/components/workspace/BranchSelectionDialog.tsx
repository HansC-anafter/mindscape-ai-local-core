'use client';

import React, { useState } from 'react';

interface Alternative {
  playbook_code: string;
  confidence: number;
  rationale: string;
  differences?: string[];
}

interface BranchSelectionDialogProps {
  title: string;
  alternatives: Alternative[];
  recommendedBranch?: string;
  onSubmit: (selectedPlaybookCode: string) => void;
  onCancel: () => void;
}

export function BranchSelectionDialog({
  title,
  alternatives,
  recommendedBranch,
  onSubmit,
  onCancel,
}: BranchSelectionDialogProps) {
  const [selected, setSelected] = useState<string>(recommendedBranch || alternatives[0]?.playbook_code || '');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (selected) {
      onSubmit(selected);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
        <div className="p-4 border-b border-gray-200 dark:border-gray-700">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            {title}
          </h3>
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
            请选择其中一个执行方案继续
          </p>
        </div>

        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          <div className="space-y-3">
            {alternatives.map((alt, index) => {
              const isRecommended = alt.playbook_code === recommendedBranch;
              const isSelected = alt.playbook_code === selected;

              return (
                <label
                  key={alt.playbook_code}
                  className={`block p-4 border-2 rounded-lg cursor-pointer transition-all ${
                    isSelected
                      ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
                      : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <input
                      type="radio"
                      name="branch"
                      value={alt.playbook_code}
                      checked={isSelected}
                      onChange={(e) => setSelected(e.target.value)}
                      className="mt-1"
                    />
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-medium text-gray-900 dark:text-gray-100">
                          {alt.playbook_code}
                        </span>
                        {isRecommended && (
                          <span className="text-xs px-2 py-0.5 bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300 rounded">
                            推荐
                          </span>
                        )}
                        <span className="text-xs text-gray-500 dark:text-gray-400">
                          置信度: {(alt.confidence * 100).toFixed(0)}%
                        </span>
                      </div>
                      <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                        {alt.rationale}
                      </p>
                      {alt.differences && alt.differences.length > 0 && (
                        <div className="text-xs text-gray-500 dark:text-gray-400">
                          <span className="font-medium">差异点：</span>
                          {alt.differences.join('、')}
                        </div>
                      )}
                    </div>
                  </div>
                </label>
              );
            })}
          </div>

          <div className="flex items-center justify-end gap-2 pt-4 border-t border-gray-200 dark:border-gray-700">
            <button
              type="button"
              onClick={onCancel}
              className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={!selected}
              className="px-4 py-2 text-sm font-medium text-white bg-blue-600 dark:bg-blue-700 rounded-lg hover:bg-blue-700 dark:hover:bg-blue-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              选择并继续
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

