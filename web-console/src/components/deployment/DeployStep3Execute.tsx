'use client';

import React from 'react';
import { DeployRequest } from '@/lib/deployment-api';

interface DeployStep3ExecuteProps {
  config: Partial<DeployRequest>;
  onDeploy: () => void;
  onBack: () => void;
  loading: boolean;
}

export default function DeployStep3Execute({
  config,
  onDeploy,
  onBack,
  loading,
}: DeployStep3ExecuteProps) {
  return (
    <div>
      <h3 className="text-lg font-semibold mb-4">Step 3: Execute Deployment</h3>

      <div className="space-y-4">
        <div className="bg-gray-50 dark:bg-gray-900 p-4 rounded">
          <h4 className="font-medium mb-2">Deployment Summary</h4>
          <ul className="text-sm space-y-1 text-gray-600 dark:text-gray-400">
            <li>Target Path: {config.target_path}</li>
            {config.git_branch && <li>Git Branch: {config.git_branch}</li>}
            {config.commit_message && <li>Commit Message: {config.commit_message}</li>}
            <li>Auto Commit: {config.auto_commit ? 'Yes' : 'No'}</li>
            <li>Auto Push: {config.auto_push ? 'Yes' : 'No'}</li>
          </ul>
        </div>

        <div className="bg-yellow-50 dark:bg-yellow-900 p-4 rounded">
          <p className="text-sm text-yellow-800 dark:text-yellow-200">
            ⚠️ Files will be copied to the target path. Git commands will be generated but not executed automatically unless you enabled auto-commit.
          </p>
        </div>
      </div>

      <div className="mt-6 flex justify-between">
        <button
          onClick={onBack}
          disabled={loading}
          className="px-4 py-2 border border-gray-300 rounded hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50"
        >
          Back
        </button>
        <button
          onClick={onDeploy}
          disabled={loading}
          className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
        >
          {loading ? 'Deploying...' : 'Deploy'}
        </button>
      </div>
    </div>
  );
}

