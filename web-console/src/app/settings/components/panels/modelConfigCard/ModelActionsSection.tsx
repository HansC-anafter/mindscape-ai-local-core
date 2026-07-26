'use client';

import { useT } from '../../../../../lib/i18n';
import type { ModelActionsSectionProps } from './types';

function formatBytes(bytes: number) {
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1)} GB`;
  if (bytes >= 1e6) return `${(bytes / 1e6).toFixed(0)} MB`;
  if (bytes >= 1e3) return `${(bytes / 1e3).toFixed(0)} KB`;
  return `${bytes} B`;
}

export function ModelActionsSection({
  model,
  testing,
  pulling,
  pullProgress,
  pullStatus,
  pullMessage,
  pullTotalBytes,
  pullDownloadedBytes,
  pullState,
  testResult,
  onTestConnection,
  onPullModel,
  onCancelPull,
}: ModelActionsSectionProps) {
  const t = useT();
  return (
    <div>
      <div className="flex gap-3">
        <button
          onClick={onTestConnection}
          disabled={testing || pulling}
          className="flex-1 px-4 py-2 bg-gray-600 dark:bg-gray-700 text-white rounded-md hover:bg-gray-700 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {testing ? t('testing' as any) : t('testConnection' as any)}
        </button>
        {['ollama', 'huggingface'].includes(model.provider) && (
          <button
            onClick={onPullModel}
            disabled={testing || pulling}
            className="flex-1 px-4 py-2 bg-accent dark:bg-blue-600 text-white rounded-md hover:bg-accent/90 dark:hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {pulling ? (
              <>
                <svg className="animate-spin h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                {pullProgress > 0 ? `${pullProgress}%` : 'Downloading...'}
              </>
            ) : pullStatus === 'completed' ? (
              <>
                Download complete
              </>
            ) : pullStatus === 'failed' ? (
              <>
                Download failed
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
                Download Model
              </>
            )}
          </button>
        )}
      </div>

      {pulling && (
        <div className="mt-3">
          <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2.5 overflow-hidden">
            <div
              className="h-2.5 rounded-full transition-all duration-500 ease-out"
              style={{
                width: `${pullProgress}%`,
                background: pullStatus === 'failed'
                  ? '#ef4444'
                  : pullStatus === 'completed'
                    ? '#22c55e'
                    : 'linear-gradient(90deg, #3b82f6, #8b5cf6)',
              }}
            />
          </div>
          <div className="flex justify-between items-center mt-1">
            <span className="text-xs text-gray-500 dark:text-gray-400 truncate max-w-[60%]">
              {pullMessage}
            </span>
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-600 dark:text-gray-300 font-medium whitespace-nowrap">
                {pullTotalBytes > 0
                  ? `${formatBytes(pullDownloadedBytes)} / ${formatBytes(pullTotalBytes)}`
                  : pullProgress > 0
                    ? `${pullProgress}%`
                    : 'Preparing...'}
              </span>
              {onCancelPull && pullState?.taskId && (
                <button
                  onClick={() => onCancelPull(pullState.taskId)}
                  className="text-xs text-red-500 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300 font-medium px-1.5 py-0.5 rounded hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                  title="Cancel download"
                >
                  Cancel
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {testResult && (
        <div className={`mt-2 p-2 rounded text-sm ${testResult.success
            ? 'bg-green-50 dark:bg-green-900/20 text-green-800 dark:text-green-300'
            : 'bg-red-50 dark:bg-red-900/20 text-red-800 dark:text-red-300'
          }`}>
          {testResult.message}
        </div>
      )}
    </div>
  );
}
