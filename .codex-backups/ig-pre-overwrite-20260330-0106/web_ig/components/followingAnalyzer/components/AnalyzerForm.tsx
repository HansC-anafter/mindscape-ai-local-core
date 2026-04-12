import React from 'react';

export function AnalyzerForm(props: {
  targetUsername: string;
  onTargetUsernameChange: (value: string) => void;

  executionBackend: 'auto' | 'runner';
  onExecutionBackendChange: (value: 'auto' | 'runner') => void;

  visitAccountPages: boolean;
  onVisitAccountPagesChange: (value: boolean) => void;

  maxAccounts: number | null;
  onMaxAccountsChange: (value: number | null) => void;

  userDataDir: string;
  onUserDataDirChange: (value: string) => void;

  runMode: string;
  onRunModeChange: (value: string) => void;

  allowPartialResume: boolean;
  onAllowPartialResumeChange: (value: boolean) => void;

  hasProfileMismatch: boolean;
  error: string | null;

  isExecuting: boolean;
  startDisabled: boolean;
  onStart: () => void;
}) {
  const {
    targetUsername,
    onTargetUsernameChange,
    visitAccountPages,
    onVisitAccountPagesChange,
    maxAccounts,
    onMaxAccountsChange,
    userDataDir,
    onUserDataDirChange,
    runMode,
    onRunModeChange,
    allowPartialResume,
    onAllowPartialResumeChange,
    hasProfileMismatch,
    error,
    isExecuting,
    startDisabled,
    onStart,
  } = props;

  return (
    <div className="flex-1 p-6 overflow-y-auto">
      <div className="max-w-2xl mx-auto space-y-6">
        <div>
          <label className="block text-sm font-medium mb-2">
            Target Username
          </label>
          <input
            type="text"
            value={targetUsername}
            onChange={(e) => onTargetUsernameChange(e.target.value)}
            placeholder="username or https://www.instagram.com/username/"
            className="w-full px-4 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-700"
            disabled={isExecuting}
          />
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            Enter username or full URL (both formats are supported)
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">
            Execution Backend (Hint)
          </label>
          <select
            value={props.executionBackend}
            onChange={(e) => props.onExecutionBackendChange(e.target.value as any)}
            className="w-full px-4 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-700"
            disabled={isExecuting}
          >
            <option value="auto">Auto (backend decides)</option>
            <option value="runner">Runner (prefer)</option>
          </select>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            This is a neutral hint sent to the backend as <code className="bg-gray-100 dark:bg-gray-700 px-1 rounded">execution_backend</code>.
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">
            Run Mode
          </label>
          <select
            value={runMode}
            onChange={(e) => onRunModeChange(e.target.value)}
            className="w-full px-4 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-700"
            disabled={isExecuting}
          >
            <option value="full">Full (scroll + visit)</option>
            <option value="list">List Only (scroll only)</option>
            <option value="visit">Visit Pages (skip scroll, resume from list)</option>
          </select>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            Choose whether to perform a full analysis, only extract the followed list, or only visit pages using an existing list.
          </p>
        </div>

        <div>
          <label className="flex items-center space-x-2 cursor-pointer">
            <input
              type="checkbox"
              checked={visitAccountPages}
              onChange={(e) => onVisitAccountPagesChange(e.target.checked)}
              disabled={isExecuting || runMode === 'list'}
              className="w-4 h-4"
            />
            <span>Visit account pages for statistics</span>
          </label>
        </div>

        {runMode === 'visit' && (
          <div>
            <label className="flex items-center space-x-2 cursor-pointer">
              <input
                type="checkbox"
                checked={allowPartialResume}
                onChange={(e) => onAllowPartialResumeChange(e.target.checked)}
                disabled={isExecuting}
                className="w-4 h-4"
              />
              <span>Allow partial resume (if previous list was incomplete)</span>
            </label>
          </div>
        )}

        <div>
          <label className="block text-sm font-medium mb-2">
            Max Accounts (Optional)
          </label>
          <input
            type="number"
            value={maxAccounts || ''}
            onChange={(e) =>
              onMaxAccountsChange(e.target.value ? parseInt(e.target.value) : null)
            }
            placeholder="Leave empty for all accounts"
            className="w-full px-4 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-700"
            disabled={isExecuting}
            min="1"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">
            Browser Profile Directory (Required for login)
          </label>
          <input
            type="text"
            value={userDataDir}
            onChange={(e) => onUserDataDirChange(e.target.value)}
            placeholder="/app/data/ig-browser-profiles/default"
            className="w-full px-4 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-700"
            disabled={isExecuting}
          />
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            Use <code className="bg-gray-100 dark:bg-gray-700 px-1 rounded">/app/data/ig-browser-profiles/default</code> if you&apos;ve run the login helper script.
          </p>
          <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
            Note: Instagram requires login. Run <code className="bg-gray-100 dark:bg-gray-700 px-1 rounded">python scripts/ig_login_helper.py</code> locally first to create a logged-in profile.
          </p>
          {hasProfileMismatch && (
            <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
              Note: This path differs from the Session panel profile. Status checks may not match.
            </p>
          )}
        </div>

        {error && (
          <div className="p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-red-700 dark:text-red-400">
            {error}
          </div>
        )}

        <button
          onClick={onStart}
          disabled={startDisabled}
          className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Start Analysis
        </button>
      </div>
    </div>
  );
}
