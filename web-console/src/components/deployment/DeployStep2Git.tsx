'use client';

import React from 'react';
import { DeployRequest } from '@/lib/deployment-api';

interface DeployStep2GitProps {
  config: Partial<DeployRequest>;
  onUpdate: (updates: Partial<DeployRequest>) => void;
  onNext: () => void;
  onBack: () => void;
}

export default function DeployStep2Git({
  config,
  onUpdate,
  onNext,
  onBack,
}: DeployStep2GitProps) {
  return (
    <div>
      <h3 className="text-lg font-semibold mb-4">Step 2: Git Configuration</h3>

      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium mb-2">
            Git Branch
          </label>
          <input
            type="text"
            value={config.git_branch || ''}
            onChange={(e) => onUpdate({ git_branch: e.target.value })}
            placeholder="feature/deploy-{project_id}"
            className="w-full px-3 py-2 border border-gray-300 rounded dark:bg-gray-700 dark:border-gray-600"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">
            Commit Message
          </label>
          <input
            type="text"
            value={config.commit_message || ''}
            onChange={(e) => onUpdate({ commit_message: e.target.value })}
            placeholder="feat(site): deploy {project_name} to production"
            className="w-full px-3 py-2 border border-gray-300 rounded dark:bg-gray-700 dark:border-gray-600"
          />
        </div>

        <div className="space-y-2">
          <label className="flex items-center">
            <input
              type="checkbox"
              checked={config.auto_commit || false}
              onChange={(e) => onUpdate({ auto_commit: e.target.checked })}
              className="mr-2"
            />
            <span className="text-sm">Auto commit after copying files</span>
          </label>

          <label className="flex items-center">
            <input
              type="checkbox"
              checked={config.auto_push || false}
              onChange={(e) => onUpdate({ auto_push: e.target.checked })}
              className="mr-2"
            />
            <span className="text-sm">Auto push after commit</span>
          </label>
        </div>
      </div>

      <div className="mt-6 flex justify-between">
        <button
          onClick={onBack}
          className="px-4 py-2 border border-gray-300 rounded hover:bg-gray-50 dark:hover:bg-gray-700"
        >
          Back
        </button>
        <button
          onClick={onNext}
          className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
        >
          Next
        </button>
      </div>
    </div>
  );
}

