import React from 'react';

export function AdvancedFeaturesPanel(props: {
  loading: boolean;
  disabled: boolean;
  onTrackElements: () => void;
  onWriteRules: () => void;
  onAggregateSeries: () => void;
}) {
  const { loading, disabled, onTrackElements, onWriteRules, onAggregateSeries } = props;

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
      <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">
        Advanced Features
      </h3>
      <div className="space-y-2">
        <button
          onClick={onTrackElements}
          disabled={disabled || loading}
          className="w-full px-4 py-2 text-sm bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-50"
        >
          Track Performance Elements
        </button>
        <button
          onClick={onWriteRules}
          disabled={disabled || loading}
          className="w-full px-4 py-2 text-sm bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50"
        >
          Write Performance Rules
        </button>
        <button
          onClick={onAggregateSeries}
          disabled={loading}
          className="w-full px-4 py-2 text-sm bg-teal-600 text-white rounded hover:bg-teal-700 disabled:opacity-50"
        >
          Series Aggregation Report
        </button>
      </div>
    </div>
  );
}

