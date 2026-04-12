import React from 'react';

import type { AnalyzerProgress } from '../types';

export function AnalyzerProgressView(props: { progress: AnalyzerProgress | null }) {
  const { progress } = props;
  const stage = (progress?.stage || '').toString().trim().toLowerCase();

  const statusMessage = (() => {
    if (!progress) return 'Initializing...';
    if (stage === 'submitting') return 'Submitting analysis request to the backend...';
    if (stage === 'recovering_submission') {
      return 'Backend acknowledgement is slow. Checking whether the run was queued...';
    }
    if (progress.status === 'pending') return 'Queued — waiting for previous task to finish...';
    if (progress.status === 'started') return 'Starting analysis...';
    if (progress.status === 'completed') return 'Analysis completed!';
    if (progress.status === 'failed') return 'Analysis failed.';
    if (stage === 'scrolling') return 'Scrolling following list...';
    if (stage === 'visiting_pages' && progress.currentAccount) {
      return `Visiting: ${progress.currentAccount}`;
    }
    if (stage === 'visiting_pages') return 'Analyzing account pages...';
    if (progress.currentAccount) return `Processing: ${progress.currentAccount}`;
    return 'Extracting account list...';
  })();

  return (
    <div className="flex-1 p-6 overflow-y-auto">
      <div className="max-w-2xl mx-auto space-y-4">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mb-4"></div>
          <h3 className="text-lg font-semibold mb-2">Analyzing Following List</h3>
          <p className="text-gray-600 dark:text-gray-400">{statusMessage}</p>
        </div>

        {progress && progress.total > 0 && (
          <div className="space-y-2">
            <div className="flex justify-between text-sm">
              <span>Progress</span>
              <span>
                {progress.current} / {progress.total}
              </span>
            </div>
            <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
              <div
                className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                style={{
                  width: `${(progress.current / progress.total) * 100}%`,
                }}
              ></div>
            </div>
          </div>
        )}

        <div className="mt-4 p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
          <p className="text-sm text-blue-700 dark:text-blue-400">
            Analysis is running in the background. You can close this window and check results later from the execution panel.
          </p>
        </div>
      </div>
    </div>
  );
}
