'use client';

import type { CliAgent } from './types';

interface ApiKeyPaneProps {
  agent: CliAgent;
  value: string;
  showKey: boolean;
  saving: boolean;
  saved: boolean;
  configured: boolean;
  onValueChange: (value: string) => void;
  onToggleShowKey: () => void;
  onSave: () => void;
}

export function ApiKeyPane({
  agent,
  value,
  showKey,
  saving,
  saved,
  configured,
  onValueChange,
  onToggleShowKey,
  onSave,
}: ApiKeyPaneProps) {
  return (
    <>
      <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-3">
        <p className="text-xs font-medium text-blue-700 dark:text-blue-300 mb-2">
          How to get your {agent.label} API Key:
        </p>
        <ol className="list-decimal list-inside space-y-1">
          {agent.guideSteps.map((step, i) => (
            <li
              key={i}
              className="text-xs text-blue-600 dark:text-blue-400"
            >
              {i === 0 ? (
                <a
                  href={agent.guideUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline hover:text-blue-800 dark:hover:text-blue-200"
                >
                  {step}
                </a>
              ) : (
                step
              )}
            </li>
          ))}
        </ol>
      </div>

      <div>
        <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
          {agent.label} API Key
        </label>
        <div className="flex gap-2">
          <div className="relative flex-1">
            <input
              type={showKey ? 'text' : 'password'}
              value={value}
              onChange={(event) => onValueChange(event.target.value)}
              placeholder={agent.placeholder}
              className="w-full px-3 py-2 text-sm border rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-mono"
            />
            <button
              type="button"
              onClick={onToggleShowKey}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 text-xs"
            >
              {showKey ? 'Hide' : 'Show'}
            </button>
          </div>
          <button
            onClick={onSave}
            disabled={saving}
            className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
              saved
                ? 'bg-green-600 text-white'
                : 'bg-blue-600 hover:bg-blue-700 text-white'
            } disabled:opacity-50 disabled:cursor-not-allowed min-w-[70px]`}
          >
            {saving ? '...' : saved ? 'Saved' : 'Save'}
          </button>
        </div>
      </div>

      {configured && (
        <div className="flex items-center gap-1.5 text-xs text-green-600 dark:text-green-400">
          <span className="w-2 h-2 rounded-full bg-green-500" />
          API key configured
        </div>
      )}
    </>
  );
}
