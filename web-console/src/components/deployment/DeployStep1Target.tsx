'use client';

import React from 'react';
import { DeployRequest } from '@/lib/deployment-api';

interface DeployStep1TargetProps {
  config: Partial<DeployRequest>;
  onUpdate: (updates: Partial<DeployRequest>) => void;
  onNext: () => void;
}

export default function DeployStep1Target({
  config,
  onUpdate,
  onNext,
}: DeployStep1TargetProps) {
  return (
    <div>
      <h3 className="text-lg font-semibold mb-4">Step 1: Confirm Deployment Target</h3>

      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium mb-2">
            Target Path (site-brand path)
          </label>
          <input
            type="text"
            value={config.target_path || ''}
            onChange={(e) => onUpdate({ target_path: e.target.value })}
            placeholder="/path/to/site-brand"
            className="w-full px-3 py-2 border border-gray-300 rounded dark:bg-gray-700 dark:border-gray-600"
          />
        </div>

        <div className="bg-gray-50 dark:bg-gray-900 p-4 rounded">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Files will be copied from sandbox to the target path. Make sure the path exists and you have write permissions.
          </p>
        </div>
      </div>

      <div className="mt-6 flex justify-end">
        <button
          onClick={onNext}
          disabled={!config.target_path}
          className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
        >
          Next
        </button>
      </div>
    </div>
  );
}

