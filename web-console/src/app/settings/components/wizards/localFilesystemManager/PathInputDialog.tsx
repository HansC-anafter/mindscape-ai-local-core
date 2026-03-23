'use client';

import { t } from '@/lib/i18n';

interface PathInputDialogProps {
  error: string | null;
  initialStorageBasePath?: string;
  isWindows: boolean;
  pathInputValue: string;
  selectedDirName: string;
  onCancel: () => void;
  onConfirm: () => void;
  onPathInputValueChange: (value: string) => void;
}

export function PathInputDialog({
  error,
  initialStorageBasePath,
  isWindows,
  pathInputValue,
  selectedDirName,
  onCancel,
  onConfirm,
  onPathInputValueChange,
}: PathInputDialogProps) {
  return (
    <div className="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-[60]">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl p-6 max-w-lg w-full mx-4">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Enter Full Path</h3>
        <div className="mb-4">
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
            Selected directory: <span className="font-medium">&quot;{selectedDirName}&quot;</span>
          </p>
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">Please enter the full absolute path</p>
          <input
            type="text"
            value={pathInputValue}
            onChange={(event) => onPathInputValueChange(event.target.value)}
            onKeyPress={(event) => event.key === 'Enter' && onConfirm()}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-accent/50 dark:focus:ring-blue-400 focus:border-transparent"
            placeholder={
              initialStorageBasePath || (isWindows ? 'C:\\Users\\...\\Documents\\...' : '/Users/.../Documents/...')
            }
            autoFocus
          />
          <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
            Example: {isWindows ? `C:\\Users\\...\\Documents\\${selectedDirName}` : `/Users/.../Documents/${selectedDirName}`}
          </p>
        </div>
        {error && (
          <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
            <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
          </div>
        )}
        <div className="flex justify-end space-x-3">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 bg-white dark:bg-gray-800"
          >
            {t('cancel' as any)}
          </button>
          <button
            onClick={onConfirm}
            className="px-4 py-2 bg-accent dark:bg-blue-700 text-white rounded-md hover:bg-accent/90 dark:hover:bg-blue-600"
          >
            Confirm
          </button>
        </div>
      </div>
    </div>
  );
}
