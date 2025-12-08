'use client';

import React from 'react';
import { DeployResponse } from '@/lib/deployment-api';

interface DeployStep4ResultProps {
  result: DeployResponse | null;
  onClose: () => void;
}

export default function DeployStep4Result({
  result,
  onClose,
}: DeployStep4ResultProps) {
  if (!result) {
    return (
      <div>
        <h3 className="text-lg font-semibold mb-4">Step 4: Deployment Result</h3>
        <p className="text-gray-500">No result available</p>
        <button
          onClick={onClose}
          className="mt-4 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
        >
          Close
        </button>
      </div>
    );
  }

  const isSuccess = result.status === 'success';

  return (
    <div>
      <h3 className="text-lg font-semibold mb-4">Step 4: Deployment Result</h3>

      <div className="space-y-4">
        {isSuccess ? (
          <div className="bg-green-50 dark:bg-green-900 p-4 rounded">
            <p className="text-green-800 dark:text-green-200 font-medium">
              ✅ Deployment successful!
            </p>
          </div>
        ) : (
          <div className="bg-red-50 dark:bg-red-900 p-4 rounded">
            <p className="text-red-800 dark:text-red-200 font-medium">
              ❌ Deployment failed: {result.error}
            </p>
          </div>
        )}

        {isSuccess && result.files_copied && (
          <div>
            <h4 className="font-medium mb-2">Files Copied ({result.files_copied.length})</h4>
            <ul className="text-sm space-y-1 bg-gray-50 dark:bg-gray-900 p-3 rounded max-h-40 overflow-y-auto">
              {result.files_copied.map((file, index) => (
                <li key={index} className="text-gray-600 dark:text-gray-400">
                  {file}
                </li>
              ))}
            </ul>
          </div>
        )}

        {isSuccess && result.git_commands && (
          <div>
            <h4 className="font-medium mb-2">Git Commands</h4>
            <div className="bg-gray-50 dark:bg-gray-900 p-3 rounded">
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                Status: {result.git_commands.executed ? 'Executed' : 'Generated (not executed)'}
              </p>
              {result.git_commands.branch && (
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                  Branch: {result.git_commands.branch}
                </p>
              )}
              <pre className="text-xs bg-gray-800 text-gray-100 p-2 rounded overflow-x-auto">
                {result.git_commands.commands.join('\n')}
              </pre>
            </div>
          </div>
        )}

        {isSuccess && result.vm_commands && (
          <div>
            <h4 className="font-medium mb-2">VM Deployment Commands</h4>
            <div className="bg-gray-50 dark:bg-gray-900 p-3 rounded">
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                Execute these commands on your VM:
              </p>
              <pre className="text-xs bg-gray-800 text-gray-100 p-2 rounded overflow-x-auto">
                {result.vm_commands.join('\n')}
              </pre>
            </div>
          </div>
        )}
      </div>

      <div className="mt-6 flex justify-end">
        <button
          onClick={onClose}
          className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
        >
          Close
        </button>
      </div>
    </div>
  );
}

